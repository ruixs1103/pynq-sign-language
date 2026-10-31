// skin_morph.cpp  —— Vitis HLS
//
// 肤色分割 + 形态学 IP，等价于 PS 端的：
//   cvtColor(BGR2YCrCb) -> inRange(Cr/Cb 双阈值)
//   -> morphologyEx(OPEN, 5x5 ELLIPSE) -> morphologyEx(CLOSE, 5x5 ELLIPSE)
//
// 接口：
//   输入 AXI4-Stream 32bit：1 像素/字，低 24 位 = B,G,R（B 在最低字节）
//   输出 AXI4-Stream 32bit：1 像素/字，低 8 位 = 二值 mask(0/255)
//   AXI4-Lite：rows/cols/四个阈值，板上可直接调阈值
//
// 实现要点：
//   1) 不依赖 hls::Window/LineBuffer 模板（各版本行为有差异），
//      改用 4 个行缓冲 + 5x5 窗口寄存器，行为完全可控
//   2) 5x5 椭圆核 = 5x5 去掉 4 个角（与 OpenCV MORPH_ELLIPSE 一致）
//   3) erode 边界填 255、dilate 边界填 0（与 OpenCV 的 borderValue 一致）
//   4) 4 级流水（E,D,D,E）用 DATAFLOW 并行，吞吐 1 像素/周期

#include <ap_axi_sdata.h>
#include <ap_int.h>
#include <hls_stream.h>

#ifndef MAX_COLS
#define MAX_COLS 1280          // 支持的最大图像宽度（cols 必须 <= MAX_COLS-6）
#endif

typedef ap_axiu<32, 1, 1, 1> axis_t;
typedef ap_uint<8> pix8_t;

static const pix8_t PAD_ERODE = 255;
static const pix8_t PAD_DILATE = 0;

// ---------------------------------------------------------------------------
// BGR -> YCrCb -> 二值 mask
// 只算 Cr/Cb（Y 用不到），定点系数 x256：
//   Cr = 128R - 107G -  21B
//   Cb = -43R -  85G + 128B
// ---------------------------------------------------------------------------
static void bgr_to_mask(hls::stream<axis_t>& in, hls::stream<pix8_t>& out,
                        int rows, int cols,
                        pix8_t cr_lo, pix8_t cr_hi,
                        pix8_t cb_lo, pix8_t cb_hi) {
    for (int i = 0; i < rows * cols; i++) {
#pragma HLS PIPELINE II = 1
        axis_t v = in.read();
        ap_int<16> b = (ap_int<16>)(ap_uint<8>)(v.data & 0xFF);
        ap_int<16> g = (ap_int<16>)(ap_uint<8>)((v.data >> 8) & 0xFF);
        ap_int<16> r = (ap_int<16>)(ap_uint<8>)((v.data >> 16) & 0xFF);

        ap_int<16> cr = 128 + ((128 * r - 107 * g - 21 * b) >> 8);
        ap_int<16> cb = 128 + ((-43 * r - 85 * g + 128 * b) >> 8);

        pix8_t m = 0;
        if (cr >= (ap_int<16>)cr_lo && cr <= (ap_int<16>)cr_hi &&
            cb >= (ap_int<16>)cb_lo && cb <= (ap_int<16>)cb_hi)
            m = 255;
        out.write(m);
    }
}

// ---------------------------------------------------------------------------
// 单级 5x5 形态学（椭圆核）。IS_ERODE=true 取窗口最小值，否则取最大值。
//
// 扫描顺序：遍历 padding 坐标 (py,px)，其对应源坐标为 (py-4, px-4)。
// 数据在链路里延迟 4 行，窗口右下列为当前像素，因此输出的中心
// 是 padding (py-2,px-2) -> 源 (py-6,px-6)，输出条件 py>=6 && px>=6。
// ---------------------------------------------------------------------------
template <bool IS_ERODE>
static void morph_stage(hls::stream<pix8_t>& in, hls::stream<pix8_t>& out,
                        int rows, int cols) {
    pix8_t lb0[MAX_COLS], lb1[MAX_COLS], lb2[MAX_COLS], lb3[MAX_COLS];
#pragma HLS BIND_STORAGE variable = lb0 type = RAM_T2P impl = BRAM
#pragma HLS BIND_STORAGE variable = lb1 type = RAM_T2P impl = BRAM
#pragma HLS BIND_STORAGE variable = lb2 type = RAM_T2P impl = BRAM
#pragma HLS BIND_STORAGE variable = lb3 type = RAM_T2P impl = BRAM

    pix8_t w[5][5];
#pragma HLS ARRAY_PARTITION variable = w complete dim = 0

    const pix8_t PAD = IS_ERODE ? PAD_ERODE : PAD_DILATE;

    for (int py = 0; py < rows + 6; py++) {
        for (int px = 0; px < cols + 6; px++) {
#pragma HLS PIPELINE II = 1
            // 1) 读 4 个行缓冲（先读后写，避免同地址读写冲突）
            pix8_t v0 = lb0[px];          // 1 行延迟
            pix8_t v1 = lb1[px];          // 2 行延迟
            pix8_t v2 = lb2[px];          // 3 行延迟
            pix8_t v3 = lb3[px];          // 4 行延迟

            // 2) 延迟链推进，新像素进 lb0
            pix8_t cur;
            int sy = py - 4, sx = px - 4;
            if (sy >= 0 && sy < rows && sx >= 0 && sx < cols)
                cur = in.read();
            else
                cur = PAD;
            lb0[px] = cur;
            lb1[px] = v0;
            lb2[px] = v1;
            lb3[px] = v2;

            // 3) 窗口列左移，新列插到最右（列 4 = 最新）
            for (int i = 0; i < 5; i++) {
#pragma HLS UNROLL
                for (int j = 0; j < 4; j++) {
#pragma HLS UNROLL
                    w[i][j] = w[i][j + 1];
                }
            }
            w[0][4] = v3;                 // 行 0 = 最旧
            w[1][4] = v2;
            w[2][4] = v1;
            w[3][4] = v0;
            w[4][4] = cur;                // 行 4 = 最新

            // 4) 窗口满 5x5 后输出（滞后 2 行 2 列）
            if (py >= 6 && px >= 6) {
                pix8_t mn = 255, mx = 0;
                for (int i = 0; i < 5; i++) {
#pragma HLS UNROLL
                    for (int j = 0; j < 5; j++) {
#pragma HLS UNROLL
                        // 5x5 椭圆核：去掉四个角
                        bool corner = ((i == 0 || i == 4) && (j == 0 || j == 4));
                        if (!corner) {
                            pix8_t v = w[i][j];
                            mn = (v < mn) ? v : mn;
                            mx = (v > mx) ? v : mx;
                        }
                    }
                }
                out.write(IS_ERODE ? mn : mx);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// mask 像素流 -> AXI4-Stream（1 像素/字，低 8 位有效）
// ---------------------------------------------------------------------------
static void mask_to_axis(hls::stream<pix8_t>& in, hls::stream<axis_t>& out,
                         int npix) {
    for (int i = 0; i < npix; i++) {
#pragma HLS PIPELINE II = 1
        axis_t v;
        v.data = (ap_uint<32>)in.read();
        v.keep = 0xF;
        v.strb = 0xF;
        v.last = (i == npix - 1) ? 1 : 0;
        v.user = 0;
        v.id = 0;
        v.dest = 0;
        out.write(v);
    }
}

// ---------------------------------------------------------------------------
// 顶层：阈值 -> 开运算(E,D) -> 闭运算(D,E)
// ---------------------------------------------------------------------------
void skin_morph(hls::stream<axis_t>& in, hls::stream<axis_t>& out,
                int rows, int cols,
                unsigned char cr_lo, unsigned char cr_hi,
                unsigned char cb_lo, unsigned char cb_hi) {
#pragma HLS INTERFACE axis port = in
#pragma HLS INTERFACE axis port = out
#pragma HLS INTERFACE s_axilite port = rows bundle = CTRL
#pragma HLS INTERFACE s_axilite port = cols bundle = CTRL
#pragma HLS INTERFACE s_axilite port = cr_lo bundle = CTRL
#pragma HLS INTERFACE s_axilite port = cr_hi bundle = CTRL
#pragma HLS INTERFACE s_axilite port = cb_lo bundle = CTRL
#pragma HLS INTERFACE s_axilite port = cb_hi bundle = CTRL
#pragma HLS INTERFACE s_axilite port = return bundle = CTRL
#pragma HLS INTERFACE ap_ctrl_hs port = return

    hls::stream<pix8_t> s0("s0"), s1("s1"), s2("s2"), s3("s3"), s4("s4");
#pragma HLS STREAM variable = s0 depth = 4096
#pragma HLS STREAM variable = s1 depth = 4096
#pragma HLS STREAM variable = s2 depth = 4096
#pragma HLS STREAM variable = s3 depth = 4096
#pragma HLS STREAM variable = s4 depth = 4096

#pragma HLS DATAFLOW
    bgr_to_mask(in, s0, rows, cols, cr_lo, cr_hi, cb_lo, cb_hi);
    morph_stage<true>(s0, s1, rows, cols);    // OPEN:  erode
    morph_stage<false>(s1, s2, rows, cols);   // OPEN:  dilate
    morph_stage<false>(s2, s3, rows, cols);   // CLOSE: dilate
    morph_stage<true>(s3, s4, rows, cols);    // CLOSE: erode
    mask_to_axis(s4, out, rows * cols);
}

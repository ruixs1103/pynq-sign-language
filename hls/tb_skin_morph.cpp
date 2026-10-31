// tb_skin_morph.cpp —— C 仿真测试台
//
// 读 in.raw(BGR 字节流) + params.txt，跑 skin_morph，写 out.raw(mask 字节流)。
// 可以直接用 g++ 编译运行（不需要 Vitis HLS），用来在综合前验证逻辑正确性：
//   g++ -I<HLS_INCLUDE> tb_skin_morph.cpp skin_morph.cpp -o tb.exe

#include <ap_axi_sdata.h>
#include <ap_int.h>
#include <hls_stream.h>
#include <cstdio>
#include <cstdlib>
#include <string>

typedef ap_axiu<32, 1, 1, 1> axis_t;

// 与 skin_morph.cpp 分开编译，这里只声明原型
void skin_morph(hls::stream<axis_t>& in, hls::stream<axis_t>& out,
                int rows, int cols,
                unsigned char cr_lo, unsigned char cr_hi,
                unsigned char cb_lo, unsigned char cb_hi);

int main(int argc, char** argv) {
    // Vitis HLS 的 csim_design 会把可执行文件放到工程子目录里运行，
    // 相对路径找不到数据文件。用环境变量 HLS_DATA_DIR 指定数据目录，
    // 未设置时退回当前目录（g++ 直接跑的场景）。
    const char* env = getenv("HLS_DATA_DIR");
    std::string dir = env ? std::string(env) : std::string(".");
    std::string params_path = argc > 1 ? std::string(argv[1]) : dir + "/params.txt";
    std::string in_path = dir + "/in.raw";
    std::string out_path = dir + "/out.raw";

    FILE* pf = fopen(params_path.c_str(), "r");
    if (!pf) {
        printf("[ERR] 读不到 %s\n", params_path.c_str());
        return 1;
    }
    int rows, cols, crlo, crhi, cblo, cbhi;
    if (fscanf(pf, "%d %d %d %d %d %d",
               &rows, &cols, &crlo, &crhi, &cblo, &cbhi) != 6) {
        printf("[ERR] params.txt 格式应为: rows cols cr_lo cr_hi cb_lo cb_hi\n");
        return 1;
    }
    fclose(pf);
    if (cols > 1280 - 6) {
        printf("[ERR] cols=%d 超过 MAX_COLS-6\n", cols);
        return 1;
    }

    int npix = rows * cols;
    unsigned char* img = (unsigned char*)malloc((size_t)npix * 3);
    FILE* fi = fopen(in_path.c_str(), "rb");
    if (!fi) {
        printf("[ERR] 读不到 %s\n", in_path.c_str());
        return 1;
    }
    fread(img, 1, (size_t)npix * 3, fi);
    fclose(fi);

    hls::stream<axis_t> in("in"), out("out");
    for (int i = 0; i < npix; i++) {
        axis_t v;
        v.data = ((ap_uint<32>)img[i * 3]) |
                 ((ap_uint<32>)img[i * 3 + 1] << 8) |
                 ((ap_uint<32>)img[i * 3 + 2] << 16);
        v.keep = 0xF;
        v.strb = 0xF;
        v.last = (i == npix - 1) ? 1 : 0;
        v.user = 0;
        v.id = 0;
        v.dest = 0;
        in.write(v);
    }

    skin_morph(in, out, rows, cols,
               (unsigned char)crlo, (unsigned char)crhi,
               (unsigned char)cblo, (unsigned char)cbhi);

    unsigned char* m = (unsigned char*)malloc((size_t)npix);
    int n = 0;
    while (!out.empty() && n < npix) {
        axis_t v = out.read();
        m[n++] = (unsigned char)(v.data & 0xFF);
    }
    if (n != npix) {
        printf("[ERR] 输出 %d 像素, 期望 %d\n", n, npix);
        return 1;
    }

    FILE* fo = fopen(out_path.c_str(), "wb");
    fwrite(m, 1, (size_t)npix, fo);
    fclose(fo);
    printf("[OK] %dx%d -> out.raw (%d 像素)\n", rows, cols, npix);
    return 0;
}

# run_cosim.tcl —— C/RTL 协同仿真（不上板的最后一道功能验证）
#
# 作用：把综合出来的 Verilog 用仿真器跑一遍，逐输出比对 C 模型与 RTL。
# csim_design 只证明 C 代码对，csynth_design 只做综合，
# 只有 cosim_design 能证明"生成的电路"和"C 代码"行为一致——
# 尤其是 AXI-Stream 的握手（TVALID/TREADY 死锁只有它能发现，
# 上板的表现是 DMA 卡死、最难定位）。
#
# 用小分辨率激励（cosim_small/，80x60）跑，否则 640x480 的 RTL 仿真
# 要几小时；握手和流水行为与小尺寸完全一致。
#
# 用独立工程名 skin_morph_cosim，避免动到主工程 skin_morph
# （复用已存在工程且不带 -reset 会触发器件库错误，这是 2026.1 的坑）。
#
# 用法：
#   cd C:/Users/LENOVO/Desktop/FPGA/sign/hls
#   D:/Vivado2026.1/2026.1/Vitis/bin/loader.bat -exec vitis_hls -f run_cosim.tcl

# HLS 靠 XILINX_VIVADO 找器件库
if {![info exists ::env(XILINX_VIVADO)]} {
    if {[info exists ::env(XILINX_VITIS)]} {
        set ::env(XILINX_VIVADO) [file normalize [file join $::env(XILINX_VITIS) .. Vivado]]
    } else {
        set ::env(XILINX_VIVADO) "D:/Vivado2026.1/2026.1/Vivado"
    }
}
set ::env(HLS_DATA_DIR) [file normalize "./cosim_small"]
puts "ENV: XILINX_VIVADO=$::env(XILINX_VIVADO)"
puts "ENV: HLS_DATA_DIR=$::env(HLS_DATA_DIR)"

if {![file exists "./cosim_small/in.raw"]} {
    puts "ERROR: 缺少 cosim_small/in.raw"
    return -code error "no stimulus"
}

open_project -reset skin_morph_cosim
set_top skin_morph
add_files skin_morph.cpp
add_files -tb tb_skin_morph.cpp

open_solution -reset solution1
set_part "xc7z020clg400-1"
create_clock -period 10.0 -name default

puts "=== 1/3 C 仿真（小激励）==="
csim_design
puts "=== 2/3 综合 ==="
csynth_design
puts "=== 3/3 C/RTL 协同仿真 ==="
cosim_design -rtl verilog
puts "=== 结束，看上面是否有 PASS ==="
quit

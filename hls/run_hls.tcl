# run_hls.tcl —— Vitis HLS 综合脚本
#
# 用法（Vitis HLS 命令行）:
#   vitis_hls -f run_hls.tcl
# 或 Vitis HLS GUI 里：Source -> run_hls.tcl
#
# 目标器件 PYNQ-Z2 (xc7z020clg400-1)，时钟 100MHz。

set proj_name skin_morph
set top       skin_morph
set srcs      [list skin_morph.cpp]
set tb_srcs   [list tb_skin_morph.cpp]
set part      "xc7z020clg400-1"
set clk       10.0

# 下面两个环境变量必须在 open_project / set_part 之前设置：
# 1) XILINX_VIVADO —— HLS 靠它定位器件库。没设会报
#    "failed to find any device libraries / Part is not supported"。
#    优先沿用已有值，其次从 XILINX_VITIS 推导，都没有时用标准并肩安装路径。
# 2) HLS_DATA_DIR —— csim_design 会把可执行文件放到工程子目录里运行，
#    相对路径读不到 in.raw / params.txt，这里把绝对路径传给 testbench。
if {![info exists ::env(XILINX_VIVADO)]} {
    if {[info exists ::env(XILINX_VITIS)]} {
        set ::env(XILINX_VIVADO) [file normalize [file join $::env(XILINX_VITIS) .. Vivado]]
    } else {
        set ::env(XILINX_VIVADO) "D:/Vivado2026.1/2026.1/Vivado"
    }
}
set ::env(HLS_DATA_DIR) [file normalize "."]
puts "ENV: XILINX_VIVADO=$::env(XILINX_VIVADO)"
puts "ENV: HLS_DATA_DIR=$::env(HLS_DATA_DIR)"

open_project -reset ${proj_name}
set_top ${top}
foreach s ${srcs} { add_files ${s} }
foreach s ${tb_srcs} { add_files -tb ${s} }

open_solution -reset "solution1"
set_part ${part}
create_clock -period ${clk} -name default

# C 仿真：用 Vitis 自带的编译器先验证逻辑正确性。
# 不需要外部 g++，只要 hls/ 下有 in.raw 与 params.txt
# （由 python pl_sim_check.py 生成）。
# 这一步通过后再综合，避免综合几十分钟才发现行缓冲错位。
if {[file exists "in.raw"] && [file exists "params.txt"]} {
    puts "=== 开始 C 仿真（验证逻辑）==="
    csim_design
} else {
    puts "WARN: 缺少 in.raw / params.txt，跳过 C 仿真"
    puts "        先执行: python pl_sim_check.py"
}

# 流水线 + 接口综合
csynth_design

# 可选：C/RTL 协同仿真
# cosim_design

# 导出 IP（供 Vivado IP Integrator 使用）
# 2026.1 的 export_design 不支持 -name / -display_name，只用下面这些选项
export_design -format ip_catalog -rtl verilog -description "skin segmentation + morphology" -vendor "pynq" -library "hls" -version "1.0"

puts "=== 综合完成，检查 latency/interval 是否为 1 像素/周期 ==="
quit

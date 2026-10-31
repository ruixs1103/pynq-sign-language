# ===========================================================================
#  build_bd.tcl —— 搭建 PYNQ-Z2 overlay（全手工连线）
#
#  为什么全手工：没装 PYNQ-Z2 板卡文件时 PS 无法应用板卡预设，
#  Connection Automation 会在 AXI DMA 上报
#  "Failed to extract configurable options / No valid slave interface"。
#
#  为什么用 SmartConnect：
#    1) PS 的 M_AXI_GP0 是 AXI3，而 DMA/skin_morph 的控制口是 AXI4LITE，
#       协议不同不能直接连（BD 41-1285），中间必须做协议转换；
#    2) 本机的 axi_interconnect IP 不可用，SmartConnect 可以替代，
#       一个 IP 同时完成 AXI3->AXI4LITE 转换和 1 路进 2 路出的分发。
#
#  用法（Vivado Tcl Console）：
#    cd C:/Users/LENOVO/Desktop/FPGA/sign/hls
#    source build_bd.tcl
#
#  前置：已跑过 vitis_hls -f run_hls.tcl
# ===========================================================================

set proj_dir  [file normalize "../vivado_proj"]
set proj_name "sign_pl"
set part      "xc7z020clg400-1"

proc first_ipdef {pat} {
    set l [get_ipdefs -filter "NAME =~ $pat"]
    if {[llength $l] == 0} { return "" }
    return [lindex $l 0]
}

# ---------------------------------------------------------------------------
# 1) 工程
# ---------------------------------------------------------------------------
create_project -force ${proj_name} ${proj_dir} -part ${part}
set boards [get_board_parts -filter "NAME =~ *pynq-z2*"]
if {[llength $boards] > 0} {
    set_property board_part [lindex $boards 0] [current_project]
    puts "INFO: 使用板卡 [lindex $boards 0]"
} else {
    puts "WARN: 无 PYNQ-Z2 板卡文件，用裸器件并按 PYNQ-Z2 手工配置 PS"
}

# ---------------------------------------------------------------------------
# 2) IP 仓库
# ---------------------------------------------------------------------------
set ip_dir ""
foreach c [list [file normalize "./skin_morph/solution1/impl"] \
                [file normalize "./skin_morph/solution1/impl/ip"]] {
    if {[file isdirectory $c]} { set ip_dir $c; break }
}
if {$ip_dir eq ""} {
    puts "ERROR: 找不到 HLS 导出的 IP，先跑 vitis_hls -f run_hls.tcl"
    return -code error "HLS IP missing"
}
set_property ip_repo_paths [list $ip_dir] [current_project]
update_ip_catalog
puts "INFO: IP 仓库 $ip_dir"

# ---------------------------------------------------------------------------
# 3) IP
# ---------------------------------------------------------------------------
create_bd_design "design_1"

set ps_v   [first_ipdef "*processing_system7*"]
set dma_v  [first_ipdef "*axi_dma*"]
set skin_v [first_ipdef "*skin_morph*"]
set smc_v  [first_ipdef "*smartconnect*"]
set psr_v  [first_ipdef "*proc_sys_reset*"]
set xlc_v  [first_ipdef "*xlconstant*"]
foreach {n v} [list PS $ps_v DMA $dma_v SKIN $skin_v SMC $smc_v] {
    if {$v eq ""} {
        puts "ERROR: 缺少 IP $n"
        return -code error "IP missing: $n"
    }
    puts "INFO: $n = $v"
}

create_bd_cell -type ip -vlnv $ps_v ps7
# PYNQ-Z2 实际配置：512MB DDR3、GP0 控制口、HP0/HP1 给 DMA、
# FCLK_CLK0=100MHz（EN_CLK0_PORT 必须开，否则 PL 侧没有时钟）
set_property -dict [list \
    CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41K256M16 RE-125} \
    CONFIG.PCW_USE_M_AXI_GP0      {1} \
    CONFIG.PCW_USE_S_AXI_HP0      {1} \
    CONFIG.PCW_USE_S_AXI_HP1      {1} \
    CONFIG.PCW_EN_CLK0_PORT       {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100.000000}] [get_bd_cells ps7]

# MIO Bank 电压：PYNQ-Z2 是 Bank0=3.3V、Bank1=1.8V。
# 2026.1 的参数名是 PCW_PRESET_BANKn_VOLTAGE，旧名 PCW_IO_VOLTAGE_BANKn 已被移除——
# 用旧名只会得到一条 [BD 41-1276] 警告，配置静默丢失（这就是之前电压没生效的原因）。
# 取值要带 "LVCMOS" 前缀；外面套 catch，万一写法不符也只警告、不影响其余配置。
if {[catch {
    set_property -dict [list CONFIG.PCW_PRESET_BANK0_VOLTAGE {LVCMOS 3.3V} \
                             CONFIG.PCW_PRESET_BANK1_VOLTAGE {LVCMOS 1.8V}] [get_bd_cells ps7]
} e]} {
    puts "WARN: MIO Bank 电压设置失败（不影响其余配置）: $e"
}

# SmartConnect：1 路 S00（接 PS 的 GP0），2 路 M00/M01（DMA 与 skin_morph）
create_bd_cell -type ip -vlnv $smc_v axi_smc
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}] [get_bd_cells axi_smc]

create_bd_cell -type ip -vlnv $dma_v axi_dma_0
set_property -dict [list CONFIG.c_include_sg {0}] [get_bd_cells axi_dma_0]

create_bd_cell -type ip -vlnv $skin_v skin_morph_0

# 同步复位发生器：PS 的 FCLK_RESET0_N 相对 PL 时钟是异步的，直接给外设会报
# [BD 41-1348] "is connected to asynchronous reset source"。
# 用 proc_sys_reset 转成与 FCLK_CLK0 同步释放的 peripheral_aresetn。
# IP 缺失时自动回退（功能照跑，只是保留那条告警）。
if {$psr_v ne ""} {
    create_bd_cell -type ip -vlnv $psr_v rst_gen
    if {$xlc_v ne ""} {
        create_bd_cell -type ip -vlnv $xlc_v const_1
        set_property -dict [list CONFIG.CONST_VAL {1} CONFIG.CONST_WIDTH {1}] [get_bd_cells const_1]
    }
} else {
    puts "WARN: 无 proc_sys_reset IP，将沿用异步复位"
}

# 数据通路同样要协议转换：DMA 的 MM2S/S2MM 是 AXI4，
# Zynq-7000 的 HP 口是 AXI3，直连会报 BD 41-1285。
create_bd_cell -type ip -vlnv $smc_v axi_smc_hp
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {2}] [get_bd_cells axi_smc_hp]

# ---------------------------------------------------------------------------
# 4) PS 外部端口
# ---------------------------------------------------------------------------
make_bd_intf_pins_external [get_bd_intf_pins ps7/DDR]
make_bd_pins_external      [get_bd_pins ps7/FIXED_IO]

# ---------------------------------------------------------------------------
# 5) 时钟与复位（全部来自 FCLK_CLK0 / FCLK_RESET0_N）
# ---------------------------------------------------------------------------
set clk [get_bd_pins ps7/FCLK_CLK0]
set rst [get_bd_pins ps7/FCLK_RESET0_N]

# 由同步复位发生器产生外设复位；没有该 IP 时直接沿用 PS 的异步复位
if {$psr_v ne ""} {
    connect_bd_net $clk [get_bd_pins rst_gen/slowest_sync_clk]
    connect_bd_net $rst [get_bd_pins rst_gen/ext_reset_in]
    if {[llength [get_bd_pins -quiet rst_gen/aux_reset_in]]} {
        connect_bd_net $rst [get_bd_pins rst_gen/aux_reset_in]
    }
    if {$xlc_v ne "" && [llength [get_bd_pins -quiet rst_gen/dcm_locked]]} {
        connect_bd_net [get_bd_pins const_1/dout] [get_bd_pins rst_gen/dcm_locked]
    }
    set rstn [get_bd_pins rst_gen/peripheral_aresetn]
    puts "INFO: 外设复位使用同步 peripheral_aresetn"
} else {
    set rstn $rst
}

connect_bd_net $clk [get_bd_pins ps7/M_AXI_GP0_ACLK]
connect_bd_net $clk [get_bd_pins ps7/S_AXI_HP0_ACLK]
connect_bd_net $clk [get_bd_pins ps7/S_AXI_HP1_ACLK]

# SmartConnect：只连存在的时钟/复位引脚（不同版本引脚名略有差异）
foreach p {aclk S00_ACLK M00_ACLK M01_ACLK} {
    if {[llength [get_bd_pins -quiet axi_smc/$p]]} {
        connect_bd_net $clk [get_bd_pins axi_smc/$p]
    }
}
foreach p {aresetn S00_ARESETN M00_ARESETN M01_ARESETN} {
    if {[llength [get_bd_pins -quiet axi_smc/$p]]} {
        connect_bd_net $rstn [get_bd_pins axi_smc/$p]
    }
}

foreach p {aclk S00_ACLK S01_ACLK M00_ACLK M01_ACLK} {
    if {[llength [get_bd_pins -quiet axi_smc_hp/$p]]} {
        connect_bd_net $clk [get_bd_pins axi_smc_hp/$p]
    }
}
foreach p {aresetn S00_ARESETN S01_ARESETN M00_ARESETN M01_ARESETN} {
    if {[llength [get_bd_pins -quiet axi_smc_hp/$p]]} {
        connect_bd_net $rstn [get_bd_pins axi_smc_hp/$p]
    }
}

connect_bd_net $clk [get_bd_pins axi_dma_0/s_axi_lite_aclk]
connect_bd_net $clk [get_bd_pins axi_dma_0/m_axi_mm2s_aclk]
connect_bd_net $clk [get_bd_pins axi_dma_0/m_axi_s2mm_aclk]
connect_bd_net $rstn [get_bd_pins axi_dma_0/axi_resetn]

connect_bd_net $clk [get_bd_pins skin_morph_0/ap_clk]
connect_bd_net $rstn [get_bd_pins skin_morph_0/ap_rst_n]

# ---------------------------------------------------------------------------
# 6) AXI 总线
#    控制：GP0 -> SmartConnect -> (M00)DMA 的 S_AXI_LITE / (M01)skin_morph 的 s_axi_CTRL
#    数据：DMA 读通道 -> HP0；写通道 -> HP1（各占一个 HP 口，避免抢同一个 slave）
# ---------------------------------------------------------------------------
connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] \
                    [get_bd_intf_pins axi_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_smc/M00_AXI] \
                    [get_bd_intf_pins axi_dma_0/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins axi_smc/M01_AXI] \
                    [get_bd_intf_pins skin_morph_0/s_axi_CTRL]

connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_MM2S] \
                    [get_bd_intf_pins axi_smc_hp/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_S2MM] \
                    [get_bd_intf_pins axi_smc_hp/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_smc_hp/M00_AXI] \
                    [get_bd_intf_pins ps7/S_AXI_HP0]
connect_bd_intf_net [get_bd_intf_pins axi_smc_hp/M01_AXI] \
                    [get_bd_intf_pins ps7/S_AXI_HP1]

# ---------------------------------------------------------------------------
# 7) 数据流：DMA -> skin_morph -> DMA
# ---------------------------------------------------------------------------
# HLS 给流接口加的后缀是 _r，实测接口名为 in_r / out_r（不是 in / out）
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S] \
                    [get_bd_intf_pins skin_morph_0/in_r]
connect_bd_intf_net [get_bd_intf_pins skin_morph_0/out_r] \
                    [get_bd_intf_pins axi_dma_0/S_AXIS_S2MM]

# ---------------------------------------------------------------------------
# 8) 地址分配 + 校验
# ---------------------------------------------------------------------------
assign_bd_address
if {[catch {validate_bd_design} err]} {
    puts "ERROR: 设计校验失败: $err"
    return -code error "validate failed"
}
save_bd_design
puts "INFO: BD 校验通过"

# 快速验证模式：设环境变量 SKIP_IMPL=1 只做 BD 搭建与校验（约 2 分钟），
# 确认连线没问题后再跑完整实现（10-30 分钟）。
if {[info exists ::env(SKIP_IMPL)] && $::env(SKIP_IMPL) ne "" && $::env(SKIP_IMPL) ne "0"} {
    puts "INFO: SKIP_IMPL=1，跳过综合实现"
    quit
}

# ---------------------------------------------------------------------------
# 9) 生成 bitstream
# ---------------------------------------------------------------------------
make_wrapper -files [get_files ${proj_dir}/${proj_name}.srcs/sources_1/bd/design_1/design_1.bd] -top
add_files -norecurse ${proj_dir}/${proj_name}.srcs/sources_1/bd/design_1/hdl/design_1_wrapper.v
update_compile_order -fileset sources_1

puts "INFO: 开始综合实现，约 10-30 分钟..."
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1

# ---------------------------------------------------------------------------
# 10) 输出 .bit / .hwh（PYNQ 要求同名同目录）
# ---------------------------------------------------------------------------
set bit [lindex [glob -nocomplain ${proj_dir}/${proj_name}.runs/impl_1/design_1_wrapper.bit] 0]
# 2026.1 里 hwh 生成在 <proj>.gen 下，不是 <proj>.srcs
set hwh [lindex [glob -nocomplain ${proj_dir}/${proj_name}.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh] 0]
if {$hwh eq ""} {
    set hwh [lindex [glob -nocomplain ${proj_dir}/${proj_name}.srcs/sources_1/bd/design_1/hw_handoff/design_1.hwh] 0]
}
if {$bit ne ""} {
    file copy -force $bit [file normalize "../skin_morph.bit"]
    puts "OK: 已输出 ../skin_morph.bit"
} else {
    puts "ERROR: 未生成 .bit"
}
if {$hwh ne ""} {
    file copy -force $hwh [file normalize "../skin_morph.hwh"]
    puts "OK: 已输出 ../skin_morph.hwh"
} else {
    puts "ERROR: 未生成 .hwh"
}
puts "DONE: 把 skin_morph.bit 和 skin_morph.hwh 一起拷到板上 ~/sign/"

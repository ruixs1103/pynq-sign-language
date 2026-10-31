# 诊断：PS 的 MIO/Bank 电压参数真实名称（2026.1 里 PCW_IO_VOLTAGE_BANK0 已不存在）
create_project -force diag4 ../vivado_diag -part xc7z020clg400-1
create_bd_design "d"
set v [lindex [get_ipdefs -filter "NAME =~ *processing_system7*"] 0]
puts "PS VLNV = $v"
create_bd_cell -type ip -vlnv $v ps7

puts "--- 含 VOLTAGE / BANK / MIO 的参数 ---"
foreach p [list_property [get_bd_cells ps7]] {
    if {[regexp -nocase {VOLTAGE|BANK|MIO} $p]} { puts "PARAM: $p" }
}
puts "--- 当前 DDR / 时钟相关 ---"
foreach p [list_property [get_bd_cells ps7]] {
    if {[regexp -nocase {DDR_PARTNO|EN_CLK0|FPGA0_PERIPHERAL|USE_M_AXI_GP|USE_S_AXI_HP} $p]} {
        catch { puts "PARAM: $p = [get_property $p [get_bd_cells ps7]]" }
    }
}
close_project

# Patch AXI DMA transfer length width for the sign preprocessing overlay.
#
# Why:
#   PYNQ reported DMA max transfer size around 16383 bytes, which is too small
#   for the image_preprocess PL path:
#     input  = 360 * 360 * 3 = 388800 bytes
#     output = 360 * 360     = 129600 bytes
#
# What this changes:
#   axi_dma_0 CONFIG.c_sg_length_width -> 26
#
# Usage from Windows PowerShell:
#   cd D:\PYNQ\projects\sign-language-pynq\fpga\sign_language_hw_2026_1
#   vivado -mode batch -source patch_dma_length_2026_1.tcl

set script_dir [file dirname [file normalize [info script]]]
set project_path [file join $script_dir "sign_language_hw_2026_1.xpr"]

if {![file exists $project_path]} {
    error "Vivado project not found: $project_path"
}

if {[current_project -quiet] eq ""} {
    open_project $project_path
} else {
    puts "INFO: Using already-open project: [current_project]"
}

set bd_file [get_files -quiet */system.bd]
if {$bd_file eq ""} {
    set bd_file [file join $script_dir "sign_language_hw_2026_1.srcs" "sources_1" "bd" "system" "system.bd"]
}

open_bd_design $bd_file

set dma [get_bd_cells -quiet axi_dma_0]
if {$dma eq ""} {
    error "Cannot find BD cell axi_dma_0"
}

puts "INFO: Current AXI DMA properties:"
report_property $dma CONFIG.c_include_sg CONFIG.c_sg_length_width

set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_sg_length_width {26} \
] $dma

puts "INFO: Patched AXI DMA properties:"
report_property $dma CONFIG.c_include_sg CONFIG.c_sg_length_width

validate_bd_design
save_bd_design

puts "INFO: DMA length width patch complete. Re-run synthesis/implementation and export bit/hwh."

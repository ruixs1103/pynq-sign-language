# Build and export the sign preprocessing overlay after Vivado BD changes.
#
# Usage from Windows PowerShell:
#   cd D:\PYNQ\projects\sign-language-pynq\fpga\sign_language_hw_2026_1
#   vivado -mode batch -source build_and_export_overlay_2026_1.tcl
#
# Output:
#   ../../board/overlays/sign_preprocess_2026_1/sign_preprocess_2026_1.bit
#   ../../board/overlays/sign_preprocess_2026_1/sign_preprocess_2026_1.hwh

set script_dir [file dirname [file normalize [info script]]]
set project_path [file join $script_dir "sign_language_hw_2026_1.xpr"]
set overlay_dir [file normalize [file join $script_dir ".." ".." "board" "overlays" "sign_preprocess_2026_1"]]

if {![file exists $project_path]} {
    error "Vivado project not found: $project_path"
}

if {[current_project -quiet] eq ""} {
    open_project $project_path
} else {
    puts "INFO: Using already-open project: [current_project]"
}

set bd_file [get_files -quiet */system.bd]
if {$bd_file ne ""} {
    open_bd_design $bd_file
    set dma [get_bd_cells -quiet axi_dma_0]
    if {$dma eq ""} {
        error "Cannot find BD cell axi_dma_0"
    }
    set dma_len [get_property CONFIG.c_sg_length_width $dma]
    puts "INFO: axi_dma_0 CONFIG.c_sg_length_width = $dma_len"
    if {$dma_len < 26} {
        error "axi_dma_0 c_sg_length_width is $dma_len, expected 26. Run patch_dma_length_2026_1.tcl first."
    }
    validate_bd_design
    save_bd_design
}

reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1

if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
    error "synth_1 did not complete"
}

reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1

if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    error "impl_1 did not complete"
}

file mkdir $overlay_dir

set bit_candidates [glob -nocomplain -types f [file join $script_dir "sign_language_hw_2026_1.runs" "impl_1" "*.bit"]]
if {[llength $bit_candidates] == 0} {
    error "No bitstream found under impl_1"
}
set bit_src [lindex $bit_candidates 0]

set hwh_candidates [glob -nocomplain -types f [file join $script_dir "sign_language_hw_2026_1.gen" "sources_1" "bd" "system" "hw_handoff" "*.hwh"]]
if {[llength $hwh_candidates] == 0} {
    error "No HWH found under system/hw_handoff"
}
set hwh_src [lindex $hwh_candidates 0]

file copy -force $bit_src [file join $overlay_dir "sign_preprocess_2026_1.bit"]
file copy -force $hwh_src [file join $overlay_dir "sign_preprocess_2026_1.hwh"]

puts "INFO: Exported overlay files:"
puts "  [file join $overlay_dir sign_preprocess_2026_1.bit]"
puts "  [file join $overlay_dir sign_preprocess_2026_1.hwh]"
puts "INFO: Source bit: $bit_src"
puts "INFO: Source hwh: $hwh_src"

if {[current_project -quiet] ne ""} {
    puts "INFO: Build/export complete."
}

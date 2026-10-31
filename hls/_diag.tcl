create_project -force diag3 ../vivado_diag -part xc7z020clg400-1
set_property ip_repo_paths [list [file normalize "./skin_morph/solution1/impl"]] [current_project]
update_ip_catalog
create_bd_design "d"
set v [lindex [get_ipdefs -filter "NAME =~ *skin_morph*"] 0]
puts "VLNV = $v"
create_bd_cell -type ip -vlnv $v sm
puts "--- INTF PINS ---"
foreach p [get_bd_intf_pins -of_objects [get_bd_cells sm]] { puts "INTF: $p" }
puts "--- PINS ---"
foreach p [get_bd_pins -of_objects [get_bd_cells sm]] { puts "PIN: $p" }
close_project

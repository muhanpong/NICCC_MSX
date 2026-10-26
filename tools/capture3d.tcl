# capture3d.tcl -- per displayed frame: log time, frame count and page; DUMP=1 dumps the
# shown SCREEN 8 page (256 x 212 bytes). env: OUTD TAG DUR, DUMP, MAXF
set auto_save_settings false
set throttle off
proc rd16 {a} { expr {[debug read memory $a] + 256*[debug read memory [expr {$a+1}]]} }
set ::log [open "$::env(OUTD)/$::env(TAG).log" w]
set ::lastf -1
set ::dump [expr {[info exists ::env(DUMP)] && $::env(DUMP)}]
set ::maxf 1801
if {[info exists ::env(MAXF)]} { set ::maxf $::env(MAXF) }
proc tick {} {
  set f [rd16 0xE202]
  if {$f != $::lastf && $f < 60000} {
    set ::lastf $f
    set page [expr {([debug read {VDP regs} 2] >> 5) & 1}]
    puts $::log "[format %.6f [machine_info time]] $f $page"
    flush $::log
    if {$::dump && $f >= 1 && $f <= $::maxf} {
      set fh [open [format "$::env(OUTD)/$::env(TAG)_u%05d.vram" $f] wb]
      puts -nonewline $fh [debug read_block VRAM [expr {$page * 0x10000}] 54272]
      close $fh
    }
    if {$f >= $::maxf} { close $::log; exit 0 }
  }
  after frame tick
}
after time 3 { after frame tick }
after time $::env(DUR) { close $::log; exit 0 }

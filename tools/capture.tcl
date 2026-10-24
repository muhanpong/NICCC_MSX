# capture.tcl -- per displayed update: dump the shown page, log stream frame.
# env: OUTD TAG DUR, DUMP=1 to write VRAM dumps, LOOPSMAX
set auto_save_settings false
set throttle off
proc rd16 {a} { expr {[debug read memory $a] + 256*[debug read memory [expr {$a+1}]]} }
set ::log [open "$::env(OUTD)/$::env(TAG).log" w]
set ::lastf -1
set ::dump [expr {[info exists ::env(DUMP)] && $::env(DUMP)}]
set ::loopsmax 1
if {[info exists ::env(LOOPSMAX)]} { set ::loopsmax $::env(LOOPSMAX) }
proc tick {} {
  set f [rd16 0xE204]; set s [rd16 0xE206]; set l [rd16 0xE208]
  if {$f != $::lastf && $f < 60000} {
    set ::lastf $f
    set page [expr {([debug read {VDP regs} 2] >> 5) & 3}]
    puts $::log "[format %.6f [machine_info time]] $f $s $l $page"
    if {$::dump && $f >= 1 && $l <= 1 && $f <= 1900} {
      set fh [open [format "$::env(OUTD)/$::env(TAG)_s%04d_u%05d.vram" $s $f] wb]
      puts -nonewline $fh [debug read_block VRAM [expr {$page * 0x8000}] 27136]
      close $fh
    }
  }
  if {$l >= $::loopsmax && $l < 1000} { close $::log; exit 0 }
  after frame tick
}
after time 3 { after frame tick }
after time $::env(DUR) { close $::log; exit 0 }

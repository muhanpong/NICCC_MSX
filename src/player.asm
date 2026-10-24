; ST-NICCC 2000 polygon stream on MSX turbo R + V9968 + Geo3D (V1 protocol).
; R800, SCREEN 5 double buffered, V9968 98h-9Ch, Geo3D 9Dh/9Fh.
; Native ASCII16X ROM: bank writes go to 6000h (bank register 0, page
; 4000h-7FFFh; the 12-bit bank number is {addr[11:8], data}; every bank of
; this 4 MiB ROM is below 256, so addr[11:8] = 0).
; Setup sequence adapted from kanon-ai V9968_Geo3D_SampleDemo (MIT).
.module niccc
.area ROM (ABS)
.org 0x4000
.ascii "AB"
.dw boot,0,0,0
.org 0x4010
.ascii "ASCII16X"
.org 0x4080
boot:
 di
 ld sp,#0xF300
 ld hl,#0x4100
 ld de,#0xE800
 ld bc,#0x0800
 ldir
 jp start

PAGE    = 0xE200
BANK    = 0xE201
PTR     = 0xE202
FRAMES  = 0xE204      ; displayed updates (debug / measurement)
SFRAME  = 0xE206      ; stream frame number on display
LOOPS   = 0xE208
CUR     = 0xE20A      ; stream frame number being drawn
FLAGS   = 0xE20C
NF      = 0xE20D
FBLEN   = 0xE20E
PALPEND = 0xE210
CMD     = 0xE220
PALBUF  = 0xE240      ; 48 bytes

.include "config.inc"

.org 0xE800
start:
 di
 ld sp,#0xF300
 ld a,(0x002D)
 cp #3
 jr c,cpu_ready
 ld a,#0x81
 call 0x0180
 di
cpu_ready:
 xor a
 ld (PAGE),a
 ld (PALPEND),a
 ld hl,#0
 ld (FRAMES),hl
 ld (SFRAME),hl
 ld (LOOPS),hl
 ld (CUR),hl
 out (0x9C),a
 ld hl,#regs
regloop:
 ld b,(hl)
 inc hl
 ld a,b
 cp #255
 jr z,regdone
 ld a,(hl)
 inc hl
 call wreg
 jr regloop
regdone:
 ; EPAL palette: all black until the stream sets it
 xor a
 ld b,#16
 call wreg
 ld b,#48
 xor a
palclr:
 out (0x9A),a
 djnz palclr
 ; Geo3D: identity pose, TZ = 256, camera block
 xor a
 out (0x9D),a
 ld hl,#pose
 ld bc,#0x189F
 otir
 ld a,#0x18
 out (0x9D),a
 ld hl,#camera
 ld bc,#0x0C9F
 otir
 ; clear both pages completely once (rows 0..255)
 xor a
 ld (CMD+3),a
 ld (CMD+2),a
 ld (CMD+6),a
 ld a,#1
 ld (CMD+7),a
 xor a
 call hmmv
 ld a,#1
 ld (CMD+3),a
 xor a
 call hmmv
 call waitce
 ld a,#0x40
 ld b,#1
 call wreg
restart:
 ld a,#FIRSTBANK
 ld (BANK),a
 ld hl,#0x4000
 ld (PTR),hl
 ld hl,#0
 ld (CUR),hl

main:
 ld a,(BANK)
 ld (0x6000),a
 ld hl,(PTR)
 ld a,(hl)
 cp #0xFD
 jr nz,not_end
 ld hl,(LOOPS)
 inc hl
 ld (LOOPS),hl
 jr restart
not_end:
 cp #0xFE
 jr nz,frame
 ld a,(BANK)
 inc a
 ld (BANK),a
 ld hl,#0x4000
 ld (PTR),hl
 jr main
frame:
 ld (FLAGS),a
 inc hl
 and #2
 jr z,no_pal
 ld de,#PALBUF
 ld bc,#48
 ldir
 ld a,#1
 ld (PALPEND),a
no_pal:
 ld (PTR),hl
 ; ---- draw into the hidden page
 ld a,(PAGE)
 xor #1
 ld (PAGE),a
 ld a,(FLAGS)
 and #1
 jr z,no_clear
 ; HMMV rows 6..205 of the hidden page, colour 0
 ld a,#YOFF
 ld (CMD+2),a
 ld a,(PAGE)
 ld (CMD+3),a
 ld a,#200
 ld (CMD+6),a
 xor a
 ld (CMD+7),a
 call hmmv
no_clear:
 call waitce
 ld a,#0x46
 out (0x9D),a
 xor a
 out (0x9F),a
 ld a,(PAGE)
 out (0x9F),a
 ld hl,(PTR)
 ld a,(hl)
 inc hl
 ld a,(hl)                ; NF
 dec hl
 or a
 jr z,no_run
 call load_geometry       ; HL -> header (NV, NF, VBLEN, FBLEN, data); returns HL past it
 ld (PTR),hl
 ld a,#0x48
 out (0x9D),a
 ld a,#3
 out (0x9F),a
geo_wait:
 in a,(0x9D)
 and #1
 jr nz,geo_wait
 jr ran
no_run:
 ld de,#6                 ; empty frame: header only (NV = NF = 0)
 add hl,de
 ld (PTR),hl
ran:
 call waitce
 ; ---- flip at the next vertical blank; palette in the same blank
 call vblank
 ld a,(PAGE)
 rrca
 rrca
 rrca
 or #31
 ld b,#2
 call wreg
 ld a,(PALPEND)
 or a
 jr z,flip_done
 xor a
 ld (PALPEND),a
 ld b,#16
 call wreg
 ld hl,#PALBUF
 ld bc,#0x309A
 otir
flip_done:
 ld hl,(CUR)
 ld (SFRAME),hl
 inc hl
 ld (CUR),hl
 ld hl,(FRAMES)
 inc hl
 ld (FRAMES),hl
 jp main

; HL -> NV, NF, VBLEN, FBLEN, vertex data, face data.  Returns HL past it.
load_geometry:
 ld a,#0x40
 out (0x9D),a
 xor a
 out (0x9F),a
 out (0x9F),a
 ld a,(hl)
 out (0x9F),a
 xor a
 out (0x9F),a
 ld a,#15
 out (0x9F),a
 xor a
 out (0x9F),a
 inc hl
 ld a,(hl)
 ld (NF),a
 inc hl
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 inc hl
 ld (FBLEN),bc
 ld a,#0x50
 out (0x9D),a
 call stream
 ld a,#0x58
 out (0x9D),a
 xor a
 out (0x9F),a
 ld a,(NF)
 out (0x9F),a
 ld a,#0x52
 out (0x9D),a
 ld de,(FBLEN)
 call stream
 ret

stream:
 ld c,#0x9F
 ld a,d
 or a
 jr z,st_tail
st_loop:
 ld b,#0
 otir
 dec a
 jr nz,st_loop
st_tail:
 ld a,e
 or a
 ret z
 ld b,e
 otir
 ret

; HMMV, colour byte A; CMD+2/3 = DY, CMD+6/7 = NY, NX = 256
hmmv:
 ld (CMD+8),a
 call waitce
 xor a
 ld (CMD),a
 ld (CMD+1),a
 ld (CMD+4),a
 ld (CMD+9),a
 ld a,#1
 ld (CMD+5),a
 ld a,#0xC0
 ld (CMD+10),a
 ld a,#36
 ld b,#17
 call wreg
 ld hl,#CMD
 ld bc,#0x0B9B
 otir
 ret

wreg:
 out (0x99),a
 ld a,b
 or #0x80
 out (0x99),a
 ret
status2:
 ld a,#2
 ld b,#15
 call wreg
 in a,(0x99)
 ret
waitce:
 call status2
 and #1
 jr nz,waitce
 ret
vblank:
 call status2
 and #0x40
 jr nz,vblank
vbnext:
 call status2
 and #0x40
 jr z,vbnext
 ret
regs:
 .db 0,6,1,0,2,31,7,0,8,10,9,128,21,0,20,0x11,51,0,52,0,53,0,54,0,55,255,56,0,57,255,58,7,255
pose:
 .dw 16384,0,0, 0,16384,0, 0,0,16384, 0,0,256
camera:
 .dw 256,128,YOFF+100,1,256,212

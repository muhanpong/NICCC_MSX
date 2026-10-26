; NICCC3D: PICONICCC's 3D reconstruction of ST-NICCC 2000 rendered live by Geo3D
; on an MSX with V9968 (SCREEN 8 + EPAL) and Geo3D at 9Dh/9Fh.
; The player only interprets an op stream (tools/build3d.py has the format); every
; decision about the picture is made offline. Native ASCII16X ROM, bank register 0
; at 6000h, page 4000h-7FFFh; the stream starts in bank 1.
.module niccc3d
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

BANK    = 0xE200
PAGE    = 0xE201      ; page on display (0/1); the frame is drawn into the other
FRAMES  = 0xE202      ; frames shown (debug / measurement)

.org 0xE800
start:
 di
 ld sp,#0xF300
 ld a,(0x002D)
 cp #3
 jr c,cpu_ready
 ld a,#0x81           ; turbo R: R800 ROM mode
 call 0x0180
 di
cpu_ready:
 xor a
 out (0x9C),a         ; unlock the V9968 extension registers
 ld hl,#0
 ld (FRAMES),hl
restart:
 ld a,#1
 ld (BANK),a
 ld (0x6000),a
 xor a
 ld (PAGE),a
 ld hl,#0x4000
next:
 ld a,(hl)
 inc hl
 cp #0x01
 jr z,op01
 cp #0x02
 jr z,op02
 cp #0x04
 jr z,op04
 cp #0x05
 jr z,op05
 cp #0x03
 jp z,op03
 cp #0x06
 jp z,op06
 cp #0x07
 jp z,op07
 cp #0xFE
 jp z,opbank
 jp restart           ; FDh (or anything unknown): from the top

; 01 idx n data[n]: Geo3D index, n bytes to the data port
op01:
 ld a,(hl)
 inc hl
 out (0x9D),a
 ld b,(hl)
 inc hl
 ld c,#0x9F
 otir
 jr next

; 02: RUN filled faces, wait until the engine is idle
op02:
 ld a,#0x48
 out (0x9D),a
 ld a,#0x03
 out (0x9F),a
g3wait:
 in a,(0x9D)
 rra
 jr c,g3wait
 jr next

; 05 idx lo hi data[len]
op05:
 ld a,(hl)
 inc hl
 out (0x9D),a
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,#0x9F
 ld a,d
 or a
 jr z,op05t
op05l:
 ld b,#0
 otir
 dec d
 jr nz,op05l
op05t:
 ld a,e
 or a
 jr z,next
 ld b,e
 otir
 jr next

; 04: end of frame: show the page just drawn at the next vertical blank
op04:
 call waitce
 call vblank
 ld a,(PAGE)
 xor #1
 ld (PAGE),a
 ld a,#0x1F
 jr z,op04p
 ld a,#0x3F
op04p:
 ld b,#2
 call wreg
 push hl
 ld hl,(FRAMES)
 inc hl
 ld (FRAMES),hl
 pop hl
 jp next

; 03 r36..r46: HMMV
op03:
 call waitce
 ld a,#36
 ld b,#17
 call wreg
 ld bc,#0x0B9B
 otir
 jp next

; 06 idx n data[n]: palette from entry idx
op06:
 ld a,(hl)
 inc hl
 ld b,#16
 call wreg
 ld b,(hl)
 inc hl
 ld c,#0x9A
 otir
 jp next

; 07 reg val
op07:
 ld b,(hl)
 inc hl
 ld a,(hl)
 inc hl
 call wreg
 jp next

opbank:
 ld a,(BANK)
 inc a
 ld (BANK),a
 ld (0x6000),a
 ld hl,#0x4000
 jp next

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

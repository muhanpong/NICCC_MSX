#!/bin/bash
# run_emu.sh TAG ROM SCRIPT.tcl  -- headless openMSX geo3d fork, FS-A1ST_V9968
#   OPENMSX_GEO3D=<dir with openMSX/ (built), settings.xml, user/, home/>  OUTD=<output dir, default ./emu>
D=${OPENMSX_GEO3D:?set OPENMSX_GEO3D to the openMSX Geo3D fork setup}
B=$D/openMSX/derived/x86_64-linux-opt-3rd
OUTD=${OUTD:-$PWD/emu}
mkdir -p $OUTD
export SDL_VIDEODRIVER=offscreen SDL_AUDIODRIVER=dummy
export OPENMSX_SYSTEM_DATA=$B/bindist/install/share OPENMSX_USER_DATA=$D/user OPENMSX_HOME=$D/home
tag=$1; rom=$2; script=$3; shift 3
cd $OUTD
TAG=$tag OUTD=$OUTD timeout ${TLIM:-1800} $B/bin/openmsx -setting $D/settings.xml \
  -machine Panasonic_FS-A1ST_V9968 -ext geo3d -cart "$rom" -romtype ${ROMTYPE:-ASCII16-X} -script "$script" "$@" > $OUTD/$tag.out 2> $OUTD/$tag.err
echo "rc=$?"

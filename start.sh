#!/bin/sh
# fldigi on the RSPdx. Bridge in this terminal (type rspdx commands here); it starts fldigi.
# Ctrl-C quits fldigi cleanly, then rspdx; closing fldigi's window does the same.
cd "$(dirname "$0")"
./fldigi-setup.sh || exit 1
exec ./fldbridge.py 7.074 usb -a a -g 35 3 --vol 0.5 --fldigi "$@"	# extra args pass through, e.g. -v

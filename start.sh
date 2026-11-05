#!/bin/sh
# fldigi on the RSPdx: bridge in this terminal (type rspdx commands here), fldigi once the bridge's sink exists.
# Ctrl-C stops the bridge; fldigi stays up without rig or audio until you close it.
cd "$(dirname "$0")"
./fldigi-setup.sh || exit 1

(	# fldigi records from the sink's monitor: no pavucontrol
	until pactl list short sinks | grep -q "	sigid	"; do sleep 0.2; done
	PULSE_SOURCE=sigid.monitor exec fldigi
) >/dev/null 2>&1 &

exec ./fldbridge.py 7.074 usb -a a -g 35 3 --vol 0.5 "$@"	# extra args pass through, e.g. -v

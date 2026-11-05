#!/bin/sh
# fldigi settings for fldbridge: flrig rig control on 127.0.0.1:12345, PulseAudio audio.
# Run with fldigi closed (it rewrites its config on exit). Usage: ./fldigi-setup.sh [config dir]
set -e
dir=${1:-$HOME/.fldigi}
xml=$dir/fldigi_def.xml

pgrep -x fldigi >/dev/null && { echo "close fldigi first"; exit 1; }
[ -f "$xml" ] || { echo "$xml not found; run fldigi once to create it"; exit 1; }
cp "$xml" "$xml.bak"

set_tag() {	# set_tag TAG VALUE
	grep -q "<$1>" "$xml" || { echo "tag $1 not in $xml"; exit 1; }
	sed -i "s#<$1>[^<]*</$1>#<$1>$2</$1>#" "$xml"
	echo "$1 = $2"
}

set_tag AUDIOIO 2	# 2 = PulseAudio
set_tag CLIENT_TO_FLRIG 1	# rig control through flrig's XML-RPC
set_tag FLRIG_IP_ADDRESS 127.0.0.1
set_tag FLRIG_IP_PORT 12345	# fldbridge's default (-p)
set_tag FLRIG_AUTO_ENABLE 0	# don't launch the real flrig

echo "saved; previous config in $xml.bak"

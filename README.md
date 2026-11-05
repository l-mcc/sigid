# sigid

Find and group HF signals by type from RSPdx I/Q: detect, measure, cluster, then name the clusters.
Early days: design notes first, code as it firms up.

## Requirements

- `rspdx` from the radio repo, built and installed:
  `make -f rspdx.make && sudo make -f rspdx.make install`
- PulseAudio or PipeWire (`pactl`, `pacat`)
- fldigi, for RSID labeling

## fldbridge.py

Lets fldigi listen through the RSPdx. It runs `rspdx -n`, pretends to be flrig over XML-RPC so fldigi can read and set frequency and mode, and plays rspdx's Digital out (UDP 7355) into a PulseAudio null sink fldigi records from.

```
./fldbridge.py 7.074 usb -a b -g 35 3 --vol 0.5
```
`-a` antenna, `-g` IF reduction and LNA state, `--vol` speaker (`-m` mutes), `-v` logs every flrig call. Without them rspdx starts on antenna A, IF 50, LNA 5, volume 0.10. While it runs, rspdx commands typed in the terminal go straight through: `ant c`, `g 30 2`, `v 0.8`.

fldigi, once:
- Configure > Rig Control > flrig: enable, address 127.0.0.1, port 12345
- Configure > Audio > Devices: PulseAudio, capture = Monitor of sigid

Receive only: PTT always reads 0. Only one program can own the RSPdx (close shack first) or listen on UDP 7355 (close decode.py).

Unhandled flrig calls are logged once as `unhandled rig.xxx(...)`; that list is what to implement next.

## License

Not chosen yet.

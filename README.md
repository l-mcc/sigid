# sigid

Find and group HF signals by type from RSPdx I/Q: detect, measure, cluster, then name the clusters.
Early days: design notes first, code as it firms up.

## Requirements

- `rspdx` from the radio repo, built and installed:
  `make -f rspdx.make && sudo make -f rspdx.make install`
- PulseAudio or PipeWire (`pactl`, `pacat`)
- fldigi, for RSID labeling

## fldigi on the RSPdx

```
./start.sh        # close fldigi and shack first; extra args go to fldbridge, e.g. -v
```
`start.sh` sets fldigi's config (`fldigi-setup.sh`), runs the bridge in this terminal, and starts fldigi once the bridge's audio sink exists. Ctrl-C stops the bridge and rspdx; fldigi stays up until you close it. Edit the `fldbridge.py` line in `start.sh` for frequency, antenna and gain.

**fldbridge.py** runs `rspdx -n`, pretends to be flrig over XML-RPC (127.0.0.1:12345) so fldigi can read and set frequency and mode, and plays rspdx's Digital out (UDP 7355) into a PulseAudio null sink, `sigid`.
```
./fldbridge.py 7.074 usb -a a -g 35 3 --vol 0.5
```
- `-a` antenna, `-g` IF reduction and LNA state, `--vol` speaker (`-m` mutes). Without them rspdx starts on antenna A, IF 50, LNA 5, volume 0.10.
- rspdx commands typed in the terminal go straight through: `ant c`, `g 30 2`, `v 0.8`.
- Logs your changes in fldigi (`fldigi: rig.set_vfo(...)`), rspdx notices, and flrig calls it doesn't handle (once each). `-v` adds fldigi's constant polling, `-vv` the raw XML-RPC.
- Receive only: PTT always reads 0.
- Only one program can own the RSPdx (close shack) or listen on UDP 7355 (close decode.py).

**fldigi-setup.sh** (run with fldigi closed; keeps a `.bak`) sets flrig rig control at 127.0.0.1:12345 and PulseAudio audio in `~/.fldigi/fldigi_def.xml`. **start.sh** launches fldigi with `PULSE_SOURCE=sigid.monitor`, so it records from the bridge without pavucontrol.

RSID: turn on RxID in fldigi, and in Configure > IDs > RsID let it search the whole passband. FT8 never sends RSID; look around 7.070-7.080 and 7.035-7.040 (PSK, Olivia, NBEMS).

## License

Not chosen yet.

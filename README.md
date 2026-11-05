# sigid

Find and group HF signals by type from RSPdx I/Q: detect, measure, cluster, then name the clusters.
Early days: design notes first, code as it firms up.

## Requirements

- `rspdx` from the radio repo, built and installed:
  `make -f rspdx.make && sudo make -f rspdx.make install`
- PulseAudio or PipeWire (`pactl`, `pacat`)
- fldigi, for RSID labeling

## sigid.py (milestone 1: detection)

```
./sigid.py 7.150 -a a -g 35 3      # runs rspdx -w 7.150 raw; waterfall at http://localhost:8700/
./sigid.py 7.150 -r x.cf32         # same, also recording the I/Q (about 4 MB/s)
./sigid.py 7.150 -i x.cf32         # replay a recording, no radio
```
Takes all of 40m at once (500 kS/s around the LO, 10 kHz above the dial). Every 15 s on the UTC clock it prints one line per signal found (center, bandwidth, start-end within the block, peak SNR) and writes `blocks/<UTC>.png`: the block's spectrogram with a red box per detection, to compare with the waterfall. rspdx commands typed in the terminal go to rspdx (`ant a`, `g 30 2`, `v 0`). Ctrl-C stops both.

How it detects: 65536-point FFTs (7.6 Hz bins, 131 ms frames), a 3x3 average, a noise floor per frequency (median over the block, then a low percentile across 5 kHz so steady carriers don't raise it), and each moment measured against the whole band at that moment, so static crashes and fence pulses don't count as signals (the `bursts` figure is how many seconds of the block they covered). Cells 6 dB over the floor are signal; gaps under 1 s or 30 Hz are bridged; a detection must reach 10 dB somewhere. All of these are options (`./sigid.py -h`). Known limits: FT8 stations closer than ~30 Hz merge into one detection, and bandwidths read about 40 Hz wide on narrow signals.

Needs `pip install -r requirements.txt` (numpy, scipy, matplotlib).

## fldigi on the RSPdx

```
./start.sh        # close fldigi and shack first; extra args go to fldbridge, e.g. -v
```
`start.sh` sets fldigi's config (`fldigi-setup.sh`) and runs the bridge in this terminal with `--fldigi`, so the bridge starts fldigi too. Ctrl-C asks fldigi to quit (XML-RPC `fldigi.terminate`, saving like File > Exit; killed only if it hasn't quit after 10 s), then stops rspdx. Closing fldigi's window does the same. Edit the `fldbridge.py` line in `start.sh` for frequency, antenna and gain.

**fldbridge.py** runs `rspdx -n`, pretends to be flrig over XML-RPC (127.0.0.1:12345) so fldigi can read and set frequency and mode, and plays rspdx's Digital out (UDP 7355) into a PulseAudio null sink, `sigid`.
```
./fldbridge.py 7.074 usb -a a -g 35 3 --vol 0.5
```
- `-a` antenna, `-g` IF reduction and LNA state, `--vol` speaker (`-m` mutes). Without them rspdx starts on antenna A, IF 50, LNA 5, volume 0.10.
- `-f`/`--fldigi` starts fldigi with `PULSE_SOURCE=sigid.monitor` and ties their lifetimes together, as above.
- rspdx commands typed in the terminal go straight through: `ant c`, `g 30 2`, `v 0.8`.
- Logs your changes in fldigi (`fldigi: rig.set_vfo(...)`), rspdx notices, and flrig calls it doesn't handle (once each). `-v` adds fldigi's constant polling, `-vv` the raw XML-RPC.
- Receive only: PTT always reads 0.
- Only one program can own the RSPdx (close shack) or listen on UDP 7355 (close decode.py).

**fldigi-setup.sh** (run with fldigi closed; keeps a `.bak`) sets flrig rig control at 127.0.0.1:12345 and PulseAudio audio in `~/.fldigi/fldigi_def.xml`. With `--fldigi`, fldigi records from the bridge without pavucontrol.

RSID: turn on RxID in fldigi, and in Configure > IDs > RsID let it search the whole passband. FT8 never sends RSID; look around 7.070-7.080 and 7.035-7.040 (PSK, Olivia, NBEMS).

## License

Not chosen yet.

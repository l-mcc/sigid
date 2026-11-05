# sigid

Find and group HF signals by type from RSPdx I/Q: detect, measure, cluster, then name the clusters.
Early days: design notes first, code as it firms up.

## Requirements

- `rspdx` from the radio repo, built and installed:
  `make -f rspdx.make && sudo make -f rspdx.make install`
- PulseAudio or PipeWire (`pactl`, `pacat`)
- fldigi, for RSID labeling

## sigid.py (milestone 1: detection; 2: labels)

```
./sigid.py 7.150 -a a -g 35 3      # runs rspdx -w 7.150 raw; waterfall at http://localhost:8700/
./sigid.py 7.150 -r x.cf32         # same, also recording the I/Q (about 4 MB/s)
./sigid.py 7.150 -i x.cf32         # replay a recording, no radio; PNGs named x_00000.png, x_00015.png...
```
Takes all of 40m at once (500 kS/s around the LO, 10 kHz above the dial). Every 15 s on the UTC clock it prints one line per signal found (center, bandwidth, start-end within the block, peak SNR) and writes `blocks/<UTC>.png`: the block's spectrogram with a red box per detection, to compare with the waterfall. rspdx commands typed in the terminal go to rspdx (`ant a`, `g 30 2`, `v 0`). Ctrl-C stops both.

How it detects: 65536-point FFTs (7.6 Hz bins, 131 ms frames), a 3x3 average, a noise floor per frequency (median over the block, then a low percentile across 5 kHz so steady carriers don't raise it), and each moment measured against the whole band at that moment, so static crashes and fence pulses don't count as signals (the `bursts` figure is how many seconds of the block they covered). Cells 6 dB over the floor are signal. Pieces less than 1 s or 300 Hz apart are one signal, so a voice (syllables, pitch harmonics) or an AM broadcast's sidebands count once. A detection must reach 10 dB somewhere; bandwidth is the span holding 99% of its power. ±100 Hz around the LO is ignored (the RSPdx's center spike). All of these are options (`./sigid.py -h`).

Each detection is then cut out of the I/Q as its own narrow stream (one FFT of the block, a short inverse FFT per detection) and measured every 10 ms:
- `span`: the whole box in Hz (`bw` is the 99%-power width)
- `env`: how far its strength swings, dB between the quieter and louder quarters of the time: ~1-2 for steady signals (carriers, FSK, PSK), 3+ for speech, large for CW keying
- `syl`: share of that swinging at syllable rate (1.5-8 Hz): ~0.2-0.3 without rhythm, 0.5+ for speech

Labels, checked in this order (`VOICE`, `CW`, `CARRIER` in sigid.py):
- `voice`: `bw` >= 200 Hz, `env` >= 3 dB, `syl` >= 0.4 (SSB phone, AM broadcasts)
- `cw`: `bw` < 200 Hz, `env` >= 8 dB, `syl` >= 0.3 (AM carriers swing 5-7 dB from their sidebands; PSK31 has little rhythm)
- `carrier`: `bw` <= 50 Hz, `env` < 3 dB, at least 3 s (a lone FT8 reads ~70 Hz)

The block line counts each kind; only unlabeled detections are listed (`--all` lists everything). PNG boxes: voice orange, cw magenta, carrier white, unlabeled red. Thresholds come from synthetic signals and one 40m recording; detections under 1 s are too short to measure and stay unlabeled.

Known limits: signals closer than ~300 Hz (FT8 stations, a CW pileup) merge into one detection.

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

#!/usr/bin/env python3
# sigid: find signals in a band of RSPdx I/Q. Milestone 1: capture and detection only.
# Live: ./sigid.py 7.150 runs `rspdx -w 7.150 raw` (waterfall at http://localhost:8700/); rspdx commands typed here go to it.
# Replay: ./sigid.py 7.150 -i x.cf32 (record one with -r x.cf32 while live).
import argparse, collections, datetime, logging, math, os, shutil, signal, subprocess, sys, threading, time
import numpy as np
import scipy.fft
from scipy import ndimage

log = logging.getLogger("sigid")

class Reader:	# drains cf32 from rspdx or a file on its own thread so the RSPdx never stalls; sample i was taken at t0 + i / rate
	def __init__(s, f, rate, live, record=None):
		s.f, s.rate, s.live, s.rec = f, rate, live, record
		s.chunks, s.base, s.end = collections.deque(), 0, 0	# chunks hold samples [base, end)
		s.t0, s.eof = None, False
		s.cv = threading.Condition()
		threading.Thread(target=s.run, daemon=True).start()

	def run(s):
		rest = b""
		while b := s.f.read1(1 << 20):
			b = rest + b
			k = len(b) // 8 * 8	# whole complex64 samples only
			x, rest = np.frombuffer(b[:k], np.complex64), b[k:]
			if s.rec:
				s.rec.write(b[:k])
			with s.cv:
				if s.t0 is None:
					s.t0 = time.time() - len(x) / s.rate if s.live else 0.0
				s.chunks.append(x)
				s.end += len(x)
				s.cv.notify()
		with s.cv:
			s.eof = True
			s.cv.notify()

	def take(s, start, n):	# samples [start, start + n), waiting for them; None at end of input
		with s.cv:
			s.cv.wait_for(lambda: s.end >= start + n or s.eof)
			if s.end < start + n:
				return None
			while s.chunks and s.base + len(s.chunks[0]) <= start:	# done with these
				s.base += len(s.chunks.popleft())
			backlog = (s.end - start - n) / s.rate
			x = np.concatenate(s.chunks)[start - s.base:start - s.base + n]
		if backlog > 30:
			log.warning(f"falling behind: {backlog:.0f} s of I/Q waiting")
		return x

class Rspdx:	# rspdx -w <mhz> raw as a child: I/Q on its stdout, commands on its stdin
	def __init__(s, mhz, setup):
		exe = shutil.which("rspdx") or sys.exit("rspdx not found on PATH; build and install it from the radio repo")
		s.p = subprocess.Popen([exe, "-w", f"{mhz:.6f}", "raw"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
			start_new_session=True)	# Ctrl-C reaches only sigid, which closes rspdx itself
		for c in setup:
			s.send(c)
		threading.Thread(target=s.typed, daemon=True).start()

	def send(s, line):
		try:
			s.p.stdin.write(line.encode() + b"\n")
			s.p.stdin.flush()
		except (BrokenPipeError, ValueError):
			pass

	def typed(s):	# lines typed in this terminal go to rspdx: ant a, g 35 3, v 0
		for line in sys.stdin:
			if line.strip():
				s.send(line.strip())

	def close(s):
		if s.p.poll() is None:
			s.send("q")	# without -n, rspdx ignores EOF on stdin
			try:
				s.p.wait(5)
			except subprocess.TimeoutExpired:
				s.p.terminate()

def close(m, size):	# binary closing by a rectangle as 1-D max/min filters (fast); outside counts as filled so block edges aren't eaten
	m = m.astype(np.uint8)
	for ax, n in enumerate(size):
		m = ndimage.maximum_filter1d(m, n, axis=ax, mode="constant", cval=0)
	for ax, n in enumerate(size):
		m = ndimage.minimum_filter1d(m, n, axis=ax, mode="constant", cval=1)
	return m.astype(bool)

def detect(x, lo_hz, a):	# -> freqs (Hz), SNR (dB, frames x bins) and detections
	nfft = a.nfft
	frames = len(x) // nfft
	w = np.hanning(nfft).astype(np.float32)
	X = scipy.fft.fftshift(scipy.fft.fft(x[:frames * nfft].reshape(frames, nfft) * w, axis=1, workers=-1), axes=1)
	f = lo_hz + (np.arange(nfft) - nfft // 2) * a.rate / nfft
	keep = (f >= a.band[0] * 1e6) & (f <= a.band[1] * 1e6)
	f, p = f[keep], np.abs(X[:, keep]) ** 2
	p = ndimage.uniform_filter(p, size=3)	# 3x3 average: lone noise cells rarely clear the threshold
	db = 10 * np.log10(p + 1e-30)
	floor_bins = max(3, int(a.floor_hz * nfft / a.rate))
	floor = ndimage.percentile_filter(np.median(db, axis=0), 20, size=floor_bins)	# low percentile across freq: steady carriers don't raise it
	snr = db - floor
	burst = np.median(snr, axis=1)	# each frame's level across the band: static crashes and fence pulses raise every frequency at once
	snr -= burst[:, None]	# so measure signals against their own moment, not the block's average
	snr[:, np.abs(f - lo_hz) < a.dc_hz] = 0	# the RSPdx's own spike at the LO
	frame_s, bin_hz = nfft / a.rate, a.rate / nfft
	join = (round(a.gap / frame_s) | 1, round(a.join_hz / bin_hz) | 1)	# odd sizes keep the closing centered
	mask = close(snr > a.thresh, join)	# one signal across short gaps: CW spaces, fading, syllables, voice harmonics
	lab, _ = ndimage.label(mask, structure=np.ones((3, 3)))
	dets = []
	for i, sl in enumerate(ndimage.find_objects(lab), 1):
		cells = lab[sl] == i
		s = snr[sl]
		if cells.sum() < a.min_cells or s[cells].max() < a.peak:	# small, or never clearly above the floor: noise
			continue
		ts, fs = sl
		wgt = np.where(cells & (s > a.thresh), 10 ** (s / 10), 0).sum(axis=0)	# power per bin, signal cells only (not bridged gaps)
		c = np.cumsum(wgt) / wgt.sum()
		k0, k1 = np.searchsorted(c, 0.005), np.searchsorted(c, 0.995)	# 99% of the power lies between these bins
		dets.append(dict(
			f=float(np.average(f[fs], weights=wgt)),
			lo=float(f[fs][k0] - bin_hz / 2), hi=float(f[fs][min(k1, len(c) - 1)] + bin_hz / 2),
			t0=ts.start * frame_s, t1=ts.stop * frame_s,
			snr=float(s[cells].max())))
	return f, snr, float(np.median(floor)), (burst > a.thresh / 2).sum() * frame_s, sorted(dets, key=lambda d: d["f"])

def save_png(path, f, snr, dets, title, block_s, pool=8):
	import matplotlib
	matplotlib.use("Agg")
	import matplotlib.pyplot as plt
	from matplotlib.patches import Rectangle
	n = snr.shape[1] // pool * pool	# max over groups of bins: narrow signals stay visible at ~100 Hz/pixel
	img = snr[:, :n].reshape(snr.shape[0], -1, pool).max(axis=2)
	fig, ax = plt.subplots(figsize=(20, 5), dpi=150)
	ax.imshow(np.clip(img, 0, 30), aspect="auto", cmap="viridis", interpolation="nearest",
		extent=[f[0] / 1e6, f[n - 1] / 1e6, block_s, 0])
	for d in dets:
		ax.add_patch(Rectangle((d["lo"] / 1e6, d["t0"]), (d["hi"] - d["lo"]) / 1e6, d["t1"] - d["t0"], fill=False, ec="red", lw=0.6))
	ax.set_xlabel("MHz")
	ax.set_ylabel("s")
	ax.set_title(title)
	fig.tight_layout()
	fig.savefig(path)
	plt.close(fig)

class Help(argparse.ArgumentDefaultsHelpFormatter):	# -h shows defaults, except for options that are off unless given
	def _get_help_string(s, action):
		return action.help if action.default in (None, False) else super()._get_help_string(action)

def interrupt(*_):	# SIGTERM takes the Ctrl-C path
	raise KeyboardInterrupt

def main():
	ap = argparse.ArgumentParser(description="sigid milestone 1: detect signals in a band of RSPdx I/Q", formatter_class=Help)
	ap.add_argument("mhz", nargs="?", type=float, default=7.150, help="dial MHz given to rspdx; the LO is --offset above it")
	ap.add_argument("-i", "--input", help="replay a .cf32 file instead of running rspdx")
	ap.add_argument("-r", "--record", help="also save the live I/Q to this .cf32 file")
	ap.add_argument("--band", nargs=2, type=float, default=[7.0, 7.3], metavar=("LO", "HI"), help="MHz to search")
	ap.add_argument("--rate", type=float, default=500000, help="rspdx raw sample rate, S/s (SSB modes)")
	ap.add_argument("--offset", type=float, default=10000, help="rspdx LO above the dial, Hz")
	ap.add_argument("--block", type=float, default=15, help="seconds per block, aligned to UTC when live")
	ap.add_argument("--nfft", type=int, default=65536, help="FFT size: 7.6 Hz bins, 131 ms frames at 500 kS/s")
	ap.add_argument("--thresh", type=float, default=6, help="dB over the floor to count as signal")
	ap.add_argument("--peak", type=float, default=10, help="dB over the floor a detection must reach somewhere")
	ap.add_argument("--floor-hz", type=float, default=5000, help="width the noise floor is taken over")
	ap.add_argument("--gap", type=float, default=1.0, help="seconds of silence bridged within one signal")
	ap.add_argument("--join-hz", type=float, default=300, help="Hz of gap bridged within one signal (voice harmonics)")
	ap.add_argument("--dc-hz", type=float, default=100, help="ignore this close to the LO (the RSPdx's center spike)")
	ap.add_argument("--min-cells", type=int, default=8, help="smallest detection, in time x frequency cells")
	ap.add_argument("--png", default="blocks", help="directory for block PNGs ('' for none)")
	ap.add_argument("-a", "--ant", choices="abc", help="antenna port (rspdx starts on a)")
	ap.add_argument("-g", "--gain", nargs=2, type=int, metavar=("IF", "LNA"), help="IF reduction 20-59, LNA state (rspdx starts at 50 5)")
	ap.add_argument("--vol", type=float, help="rspdx speaker volume 0-2 (rspdx starts at 0.10)")
	ap.add_argument("-v", "--verbose", action="store_true", help="debug logging")
	a = ap.parse_args()
	logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(message)s")
	signal.signal(signal.SIGTERM, interrupt)
	signal.signal(signal.SIGINT, interrupt)

	lo_hz = a.mhz * 1e6 + a.offset
	live = not a.input
	rx = None
	if live:
		setup = []	# rspdx commands sent at startup
		if a.ant: setup.append(f"ant {a.ant}")
		if a.gain: setup.append(f"g {a.gain[0]} {a.gain[1]}")
		if a.vol is not None: setup.append(f"v {a.vol}")
		rx = Rspdx(a.mhz, setup)
		src = rx.p.stdout
	else:
		src = open(a.input, "rb")
	rec = open(a.record, "wb") if a.record and live else None
	r = Reader(src, a.rate, live, rec)
	if a.png:
		os.makedirs(a.png, exist_ok=True)
	n = int(a.block * a.rate)
	try:
		with r.cv:
			r.cv.wait_for(lambda: r.t0 is not None or r.eof)
		if r.t0 is None:
			sys.exit("no I/Q")
		tb = math.ceil(r.t0 / a.block) * a.block if live else 0.0	# first block starts on a UTC boundary
		start = round((tb - r.t0) * a.rate)
		log.info(f"LO {lo_hz / 1e6:.6f} MHz, {a.rate / 1e3:.0f} kS/s, band {a.band[0]}-{a.band[1]} MHz, {a.block:g} s blocks"
			+ (f", first at {datetime.datetime.fromtimestamp(tb, datetime.timezone.utc):%H:%M:%S} UTC" if live else ""))
		while (x := r.take(start, n)) is not None:
			t = time.perf_counter()
			f, snr, floor, noisy, dets = detect(x, lo_hz, a)
			stamp = datetime.datetime.fromtimestamp(tb, datetime.timezone.utc) if live else None
			label = f"{stamp:%H:%M:%S}" if live else f"+{tb:.0f}s"
			log.info(f"{label}  {len(dets)} signals  floor {floor:.1f} dB  bursts {noisy:.1f} s  ({time.perf_counter() - t:.1f} s to process)")
			for d in dets:
				log.info(f"  {d['f'] / 1e6:10.6f}  bw {d['hi'] - d['lo']:7.0f} Hz  {d['t0']:5.1f}-{d['t1']:4.1f} s  snr {d['snr']:5.1f} dB")
			if a.png:
				name = f"{stamp:%Y%m%d_%H%M%S}" if live else f"{os.path.splitext(os.path.basename(a.input))[0]}_{tb:05.0f}"
				save_png(os.path.join(a.png, name + ".png"), f, snr, dets, f"{label}  {len(dets)} signals", a.block)
			start += n
			tb += a.block
		log.info("input ended")
	except KeyboardInterrupt:
		pass
	finally:
		signal.signal(signal.SIGTERM, signal.SIG_IGN)
		signal.signal(signal.SIGINT, signal.SIG_IGN)
		if rx:
			rx.close()
		if rec:
			rec.close()

if __name__ == "__main__":
	main()

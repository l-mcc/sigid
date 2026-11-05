#!/usr/bin/env python3
# fldbridge: fldigi <-> rspdx. Pretends to be flrig (XML-RPC) and feeds rspdx's Digital out into a PulseAudio null sink.
# fldigi: Rig Control > flrig, 127.0.0.1:12345; Audio > PulseAudio, capture = "Monitor of sigid".
import argparse, json, logging, os, shutil, signal, socket, subprocess, sys, threading
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler

log = logging.getLogger("fldbridge")
RSPDX = shutil.which("rspdx") or sys.exit("rspdx not found on PATH; build and install it from the radio repo")
MODES = {"lsb": "LSB", "usb": "USB", "am": "AM", "wbfm": "WFM"}	# rspdx name: name fldigi sees

class Rx:	# rspdx -n as a child: commands on stdin, JSON lines on stdout
	def __init__(s, mhz, mode, setup):
		s.mhz, s.mode, s.closing = mhz, mode, False
		s.p = subprocess.Popen([RSPDX, "-n", f"{mhz:.6f}", mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
			start_new_session=True)	# Ctrl-C reaches only the bridge, which closes rspdx itself
		threading.Thread(target=s.read, daemon=True).start()
		for c in ["digi 1", "bw 3"] + setup:
			s.send(c)
		threading.Thread(target=s.typed, daemon=True).start()

	def send(s, line):
		s.p.stdin.write(line + "\n")
		s.p.stdin.flush()

	def read(s):
		for line in s.p.stdout:
			try:
				m = json.loads(line)
			except ValueError:
				continue
			if m.get("type") == "state":
				s.mhz, s.mode = m["state"]["mhz"], m["state"]["mode"].lower()
			elif m.get("type") == "notice":
				log.info(f"rspdx: {m['msg']}")
		if not s.closing:
			log.error(f"rspdx exited ({s.p.wait()})")
			os.kill(os.getpid(), signal.SIGTERM)

	def typed(s):	# lines typed in this terminal go straight to rspdx: ant b, g 35 3, v 0.5
		for line in sys.stdin:
			if line.strip():
				s.send(line.strip())

	def tune(s, hz):
		s.mhz = hz / 1e6	# optimistic; the next state line confirms it
		s.send(f"f {s.mhz:.6f}")

	def set_mode(s, m):
		s.mode = m
		s.send(f"m {m}")

	def close(s):
		s.closing = True
		if s.p.poll() is None:
			s.p.stdin.close()	# EOF: rspdx shuts down cleanly
			try:
				s.p.wait(5)
			except subprocess.TimeoutExpired:
				s.p.kill()

class Flrig:	# the slice of flrig's API fldigi uses; unknown methods are logged once and answered 0
	def __init__(s, rx):
		s.rx, s.unknown = rx, set()

	def _dispatch(s, method, params):
		name = method.replace(".", "_")
		f = None if name.startswith("_") else getattr(s, name, None)
		if f is None:
			if method not in s.unknown:
				s.unknown.add(method)
				log.info(f"unhandled {method}{tuple(params)}")
			return 0
		try:
			r = f(*params)
		except Exception:
			log.exception(f"{method}{tuple(params)}")
			raise
		log.debug(f"{method}{tuple(params)} -> {r!r}")
		return r

	def main_get_version(s): return "1.4.7"
	def rig_get_xcvr(s): return "RSPdx"
	def rig_get_info(s): return f"R:RSPdx\nT:R\nFA:{round(s.rx.mhz * 1e6)}\nM:{MODES[s.rx.mode]}\n"
	def rig_get_vfo(s): return str(round(s.rx.mhz * 1e6))
	def rig_get_AB(s): return "A"
	def rig_get_mode(s): return MODES[s.rx.mode]
	def rig_get_modes(s): return list(MODES.values())
	def rig_get_sideband(s): return "L" if s.rx.mode == "lsb" else "U"
	def rig_get_bw(s): return ["3000", ""]
	def rig_get_bws(s): return [["Bandwidth", "3000"]]
	def rig_get_ptt(s): return 0
	def rig_set_ptt(s, v): return 0	# receive only
	def rig_get_smeter(s): return 0

	def rig_set_vfo(s, hz):
		s.rx.tune(float(hz))
		return 0
	rig_set_verify_vfo = rig_set_vfo

	def rig_set_mode(s, name):
		m = {v: k for k, v in MODES.items()}.get(str(name).upper())
		if m:
			s.rx.set_mode(m)
		return 0
	rig_set_verify_mode = rig_set_mode

class AnyPath(SimpleXMLRPCRequestHandler):
	rpc_paths = ()	# accept POSTs to any path, not just / and /RPC2

class Sink:	# PulseAudio null sink fed from rspdx's Digital out (UDP, 48 kHz s16le mono)
	def __init__(s, name, port):
		s.mod = subprocess.check_output(["pactl", "load-module", "module-null-sink", f"sink_name={name}",
			f"sink_properties=device.description={name}"], text=True).strip()
		s.cat = subprocess.Popen(["pacat", "--playback", "--raw", "-d", name, "--format=s16le", "--rate=48000", "--channels=1"], stdin=subprocess.PIPE, bufsize=0,
			start_new_session=True)
		s.sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			s.sk.bind(("127.0.0.1", port))
		except OSError as e:
			s.close()
			sys.exit(f"udp {port}: {e.strerror} (decode.py or direwolf already listening?)")
		threading.Thread(target=s.pump, daemon=True).start()

	def pump(s):
		while True:
			try:
				s.cat.stdin.write(s.sk.recv(4096))
			except (OSError, ValueError):
				return

	def close(s):
		s.sk.close()
		s.cat.terminate()
		subprocess.run(["pactl", "unload-module", s.mod])

def interrupt(*_):	# SIGTERM (or rspdx dying) takes the Ctrl-C exit path
	raise KeyboardInterrupt

def main():
	ap = argparse.ArgumentParser(description="fldigi <-> rspdx bridge (acts as flrig)")
	ap.add_argument("mhz", nargs="?", type=float, default=7.074)
	ap.add_argument("mode", nargs="?", default="usb", choices=MODES)
	ap.add_argument("-p", "--port", type=int, default=12345, help="XML-RPC port fldigi connects to (flrig's default)")
	ap.add_argument("-u", "--udp", type=int, default=7355, help="rspdx Digital out port")
	ap.add_argument("-s", "--sink", default="sigid", help="null sink name; fldigi records its monitor")
	ap.add_argument("-a", "--ant", choices="abc", help="antenna port")
	ap.add_argument("-g", "--gain", nargs=2, type=int, metavar=("IF", "LNA"), help="IF reduction 20-59, LNA state; rspdx starts at 50 5")
	ap.add_argument("--vol", type=float, help="speaker volume 0-2; Digital out is taken before it")
	ap.add_argument("-m", "--mute", action="store_true", help="speaker volume 0")
	ap.add_argument("-v", "--verbose", action="store_true")
	a = ap.parse_args()
	logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

	signal.signal(signal.SIGTERM, interrupt)
	signal.signal(signal.SIGINT, interrupt)	# even if started with SIGINT ignored
	sink = Sink(a.sink, a.udp)
	setup = []	# rspdx commands sent at startup
	if a.ant: setup.append(f"ant {a.ant}")
	if a.gain: setup.append(f"g {a.gain[0]} {a.gain[1]}")
	if a.mute or a.vol is not None: setup.append(f"v {0 if a.mute else a.vol}")
	rx = Rx(a.mhz, a.mode, setup)
	srv = SimpleXMLRPCServer(("127.0.0.1", a.port), AnyPath, allow_none=False, logRequests=a.verbose)
	srv.register_instance(Flrig(rx))
	log.info(f"{a.mhz:.6f} MHz {a.mode}, flrig on 127.0.0.1:{a.port}, audio on sink '{a.sink}'")
	try:
		srv.serve_forever()
	except KeyboardInterrupt:
		pass
	finally:
		signal.signal(signal.SIGTERM, signal.SIG_IGN)	# a second TERM mustn't cut cleanup short
		srv.server_close()
		rx.close()
		sink.close()

if __name__ == "__main__":
	main()

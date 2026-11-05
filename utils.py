#!/usr/bin/env python3
import sys
import os
import time
import socket
import platform
import re
import subprocess
import logging
from pathlib import Path

'''------------------------------------------------------------------------
	make exception string
------------------------------------------------------------------------'''

def mkexs(e):
	exc_type, exc_obj, exc_tb = sys.exc_info()
	fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
	s = '%s, %s, %s\n' % (exc_type, fname, exc_tb.tb_lineno)
	s += repr(e)
	return s
# mkexs

'''-------------------------------------------------------------------
-------------------------------------------------------------------'''

def is_vscode():
	vscode = False
	if 'debugpy' in sys.modules:
		vscode = True
		return True

	x = os.getenv('VSCODE_IPC_HOOK_CLI')
	if x is not None:
		vscode = True
	x = os.getenv('VSCODE_GIT_IPC_HANDLE')
	if x is not None:
		vscode = True
	return vscode
# is_vscode


'''-------------------------------------------------------------------'''

def flush(logg):
	for h in logg.handlers:
		h.flush()
# flush

'''-------------------------------------------------------------------'''

def blank(logger):
	logger.info("", extra={"blank": True})
# blank

'''-------------------------------------------------------------------
-------------------------------------------------------------------'''

class LogFormatter(logging.Formatter):
	def format(self, record):
		if getattr(record, "blank", False):
			return ""
		return super().format(record)
# class

'''-------------------------------------------------------------------
-------------------------------------------------------------------'''

def setup_logging( name: str = 'x', logfile: str | Path = 'x.log', level: int = logging.INFO, console: bool = True,) -> logging.Logger:
	import logging.handlers

	logger = logging.getLogger(name)

	# Idempotent: calling twice won't double up handlers
	if logger.handlers:
		return logger

	logger.setLevel(level)
	logger.propagate = False   # don't also bubble to root -> no duplicates

	for noisy in ("urllib3", "requests", "asyncio"):
		logging.getLogger(noisy).setLevel(logging.WARNING)

	# fmt = logging.Formatter(
	# 	fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
	# 	datefmt="%Y-%m-%d %H:%M:%S",
	# )
	fmt = LogFormatter(
		fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
		datefmt="%Y-%m-%d %H:%M:%S",
	)
	# Rotating file handler: 5 files x 5 MB, keeps history without manual cleanup
	fh = logging.handlers.RotatingFileHandler(
		logfile, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
	)
	fh.setFormatter(fmt)
	logger.addHandler(fh)

	if console:
		ch = logging.StreamHandler(sys.stderr)
		ch.setFormatter(fmt)
		logger.addHandler(ch)

	return logger
# setup_logging

'''-------------------------------------------------------------------

-------------------------------------------------------------------'''


def setup(_dir=None):
	bp = 0

	if _dir is not None:
		os.chdir(_dir)

	if os.name == 'nt':
		mytz = pytz.timezone('US/Eastern')
		pytz.utc.localize(datetime.utcnow(), is_dst=None).astimezone(mytz)
	else:
		time.strftime('%X %x %Z')
		os.environ['TZ'] = 'US/Eastern'
		time.tzset()

	vscode = is_vscode()

	x = os.getenv('RUN_BY_CRON')				# None
	if x is None:
		cron = False
	else:
		cron = True

	hn = socket.gethostname()
	if vscode:
		# os.system('cls' if os.name == 'nt' else 'clear')
		pass

	if _dir is not None:
		os.chdir(_dir)
	cwd = os.getcwd()

	machine = platform.machine()						# 'aarch64'
	return hn, cron, cwd, vscode, machine
# setup

'''-------------------------------------------------------------------
-------------------------------------------------------------------'''

def set_vscode_terminal_font_size(sz):

	fname = '.vscode/settings.json'
	new = f'"terminal.integrated.fontSize": {sz}'

	with open(fname, 'r') as f:
		s = f.read()

	if new in s:
		return


	shutil.copyfile(fname, f'{fname}.backup')

	s2 = re.sub(
					r'"terminal\.integrated\.fontSize"\s*:\s*\d+',
					new,
					s,
					count=1,
				)

	# if n == 0:
	# 	s2 = re.sub	(
	# 						r'\}\s*$',
	# 						',\n  ' + new + '\n}',
	# 						s
	# 					)

	with open(fname, 'w') as f:
		f.write(s2)
	return
# set_vscode_terminal_font_size

'''-------------------------------------------------------------------
-------------------------------------------------------------------'''

def set_vscode_editor_font_size(sz):
	fname = '.vscode/settings.json'
	new = f'"editor.fontSize": {sz}'
	with open(fname, 'r') as f:
		s = f.read()
	if new in s:
		return
	shutil.copyfile(fname, f'{fname}.backup')

	s2 = re.sub(
					r'"editor\.fontSize"\s*:\s*\d+',
					new,
					s,
					count=1,
				)
	with open(fname, 'w') as f:
		f.write(s2)
	return
# set_vscode_editor_font_size

'''------------------------------------------------------------------
 stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True
	result = subprocess.run(cnd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
------------------------------------------------------------------'''


def run(cmd, shl=False):
	rc = 0
	shls = ['*', '|', '/', '>', '<', '||', '&&', 'nohup',]
	for s in shls:
		if s in cmd:
			shl = True
			break
	'''
		possible alternative:
		shls = ['\\|', '>', '<', '>>', '&&', '\\|\\|', '&', ';', '2>']
		for s in shls:
			if re.search(r'\b' + s + r'\b', cmd):
				shl = True
				break
	'''

	if not shl:
		# cmd = cmd.split()
		cmd = shlex.split(cmd)


	try:
		s = subprocess.check_output(
			cmd,
			stderr=subprocess.STDOUT,
			shell=shl,
			universal_newlines=True
		)
	except subprocess.CalledProcessError as e:
		s = e.output
		rc = e.returncode
	except Exception as e:
		rc = 1
		s = f'utils.run: {str(e)}'
	return rc, s.strip()
# run


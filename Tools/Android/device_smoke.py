#!/usr/bin/env python3
"""Install/launch an existing APK on a selected physical phone; never equates process start with gameplay success."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--apk', type=Path, required=True)
p.add_argument('--adb', default='adb')
p.add_argument('--serial', required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
if not a.apk.is_file():
    p.error('APK does not exist')
a.output.mkdir(parents=True, exist_ok=True)
def adb(*parts, check=True):
    return subprocess.run([a.adb, '-s', a.serial, *parts], capture_output=True, text=True, check=check, timeout=180)
assert adb('get-state').stdout.strip() == 'device', 'Unlock phone and authorize USB debugging first'
model = adb('shell', 'getprop', 'ro.product.model').stdout.strip()
android = adb('shell', 'getprop', 'ro.build.version.release').stdout.strip()
abi = adb('shell', 'getprop', 'ro.product.cpu.abilist').stdout.strip()
assert 'arm64-v8a' in abi, 'ARM64 phone required'
install = adb('install', '-r', str(a.apk.resolve()))
(a.output / 'install.txt').write_text(install.stdout + install.stderr)
assert 'Success' in install.stdout, 'Install not confirmed'
activity = adb('shell', 'cmd', 'package', 'resolve-activity', '--brief', 'org.odyssey.judge').stdout.strip().splitlines()[-1]
assert '/' in activity and activity.startswith('org.odyssey.judge/'), activity
adb('shell', 'am', 'force-stop', 'org.odyssey.judge')
started = time.monotonic()
launch = adb('shell', 'am', 'start', '-W', '-n', activity)
(a.output / 'launch.txt').write_text(launch.stdout + launch.stderr)
# An activity-manager launch is only a startup signal; inspect the screen and play manually.
pid = adb('shell', 'pidof', 'org.odyssey.judge', check=False).stdout.strip()
(a.output / 'memory.txt').write_text(adb('shell', 'dumpsys', 'meminfo', 'org.odyssey.judge', check=False).stdout)
(a.output / 'logcat.txt').write_text(adb('logcat', '-d', '-t', '3000', check=False).stdout)
receipt = {'phone': model, 'android': android, 'apk_sha256': hashlib.file_digest(a.apk.open('rb'), 'sha256').hexdigest(),
           'install': 'Success', 'activity_start_status_ok': 'Status: ok' in launch.stdout,
           'process_running_at_check': bool(pid), 'adb_launch_elapsed_seconds': round(time.monotonic() - started, 3),
           'menu': 'MANUAL_TEST_REQUIRED', 'solar_transit': 'MANUAL_TEST_REQUIRED',
           'earth_moon_mars': 'MANUAL_TEST_REQUIRED', 'earth_command': 'MANUAL_TEST_REQUIRED',
           'touch_resume_orientation': 'MANUAL_TEST_REQUIRED', 'measured_fps': None, 'peak_memory_mb': None}
(a.output / 'device-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))

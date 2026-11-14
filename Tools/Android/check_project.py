#!/usr/bin/env python3
"""CPU-only branch/config/content checks. Does not start Unreal or claim gameplay validation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = 'e102d34a9e115ce8871162431c2314d53d67154e'


def check():
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    if branch and branch != 'feature/android-judge-build':
        raise RuntimeError('Use feature/android-judge-build only')
    project = json.loads((ROOT / 'Odyssey.uproject').read_text())
    assert project['TargetPlatforms'] == ['Mac', 'Windows', 'Android']
    # Protect desktop settings and all source art/maps byte-for-byte against the approved base.
    protected = ['Config/DefaultEngine.ini', 'Config/DefaultGame.ini', 'Config/DefaultInput.ini',
                 'Content', 'ArtSource']
    changes = subprocess.check_output(['git', 'diff', '--name-only', BASE, '--', *protected], cwd=ROOT, text=True)
    assert not changes.strip(), f'Desktop content/config changed: {changes}'
    android = ROOT / 'Config/Android'
    engine = (android / 'AndroidEngine.ini').read_text()
    for setting in ['bBuildForArm64=True', 'bSupportsVulkan=True', 'bSupportsVulkanSM5=False',
                    'bPackageDataInsideApk=True', 'TargetSDKVersion=36', 'bEnablePlugin=False']:
        assert setting in engine, setting
    game = (android / 'AndroidGame.ini').read_text()
    assert 'bAndroidJudgeOffline=True' in game and 'bAutoStartSession=False' in game
    maps = ['Space/Maps/L_Odyssey_SolarTransit.umap', 'Earth/EarthCommand/Maps/L_EarthCommand_Slice.umap']
    sizes = {}
    for name in maps:
        asset = ROOT / 'Content' / name
        assert asset.is_file(), name
        assert not asset.read_bytes()[:64].startswith(b'version https://git-lfs'), f'LFS pointer: {name}'
        sizes[name] = asset.stat().st_size
    subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
    return {'result': 'passed', 'scope': 'static config/content checks only', 'maps': sizes,
            'desktop_content_unchanged': True, 'unreal_compiled': False, 'apk_built': False,
            'device_tested': False, 'fps_measured': False}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

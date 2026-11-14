#!/usr/bin/env python3
"""Native Unreal Android build on a provisioned Windows/Linux builder; NEVER on this Mac."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]


def run(argv, **kwargs):
    subprocess.run([str(a) for a in argv], check=True, cwd=ROOT, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-actions', type=int, default=2)
    parser.add_argument('--desktop-regression', action='store_true', help='Run existing editor regression suites on the remote builder after creating the APK; station tests need a backend')
    args = parser.parse_args()
    # Enforce the user's 8 GB Mac restriction before any Unreal/toolchain executable is invoked.
    if platform.system() not in ('Windows', 'Linux') or platform.machine().lower() not in ('amd64', 'x86_64'):
        sys.exit('REFUSED: use a provisioned Windows/Linux x86_64 Unreal builder. No local Mac Unreal build is permitted.')
    if sys.version_info < (3, 11):
        sys.exit('Use Python 3.11 or newer on the remote builder.')
    if args.max_actions < 1 or args.max_actions > 8:
        sys.exit('--max-actions must be 1..8')
    from check_project import check
    check()
    engine = args.engine.resolve()
    version = json.loads((engine / 'Engine/Build/Build.version').read_text())
    if (version['MajorVersion'], version['MinorVersion'], version['PatchVersion']) != (5, 8, 4):
        sys.exit('This recipe requires the matching UE 5.8.4 native engine build.')
    sdk_spec = json.loads((engine / 'Engine/Config/Android/Android_SDK.json').read_text())
    sdk = Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or '')
    if not sdk.is_absolute():
        sys.exit('Set ANDROID_HOME on the remote builder; SDK paths are never stored in the project.')
    for relative in ['platforms/' + sdk_spec['platforms'], 'build-tools/' + sdk_spec['build-tools'],
                     'ndk/' + sdk_spec['ndk'], 'cmake/' + sdk_spec['cmake']]:
        if not (sdk / relative).is_dir():
            sys.exit('Missing engine-selected Android package: ' + relative)
    os.environ['ANDROID_HOME'] = str(sdk)
    os.environ['ANDROID_SDK_ROOT'] = str(sdk)
    os.environ['NDKROOT'] = str(sdk / 'ndk' / sdk_spec['ndk'])
    os.environ['NDK_ROOT'] = os.environ['NDKROOT']
    ndk_properties = (sdk / 'ndk' / sdk_spec['ndk'] / 'source.properties').read_text()
    if sdk_spec['ndk'] not in ndk_properties:
        sys.exit('NDK package version does not match Unreal Android_SDK.json')
    if not os.environ.get('JAVA_HOME'):
        sys.exit('Set JAVA_HOME for the remote builder and pass Unreal Turnkey SDK verification.')
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        sys.exit('Use an empty output directory to avoid mixing old and new artifacts.')
    output.mkdir(parents=True, exist_ok=True)
    for asset in (ROOT / 'Content').rglob('*'):
        if asset.suffix in ('.uasset', '.umap'):
            with asset.open('rb') as stream:
                if stream.read(64).startswith(b'version https://git-lfs'):
                    sys.exit('Unresolved Git LFS asset: ' + str(asset.relative_to(ROOT)))
    if shutil.disk_usage(ROOT).free < 80 * 1024**3:
        sys.exit('Remote builder needs at least 80 GiB free for Android/editor intermediates and shader cooking.')
    windows = platform.system() == 'Windows'
    host = 'Win64' if windows else 'Linux'
    batch = engine / 'Engine/Build/BatchFiles'
    build = batch / ('Build.bat' if windows else 'Linux/Build.sh')
    uat = batch / ('RunUAT.bat' if windows else 'RunUAT.sh')
    def engine_run(script, options):
        command = [script, *options]
        # Windows .bat execution through cmd is required; do not interpolate shell commands on Unix.
        if windows:
            command = ['cmd.exe', '/d', '/c', *command]
        run(command)
    project = ROOT / 'Odyssey.uproject'
    engine_run(uat, ['Turnkey', '-command=VerifySdk', '-platform=Android', '-project=' + str(project), '-utf8output'])
    engine_run(build, ['OdysseyEditor', host, 'Development', '-Project=' + str(project),
                       '-WaitMutex', '-MaxParallelActions=' + str(args.max_actions)])
    engine_run(uat, ['BuildCookRun', '-project=' + str(project), '-noP4', '-utf8output', '-unattended',
                     '-platform=Android', '-cookflavor=ASTC', '-target=Odyssey', '-clientconfig=Development',
                     '-build', '-cook', '-stage', '-pak', '-iostore', '-package', '-archive',
                     '-archivedirectory=' + str(output / 'Package'),
                     '-map=/Game/Space/Maps/L_Odyssey_SolarTransit+/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice',
                     '-UbtArgs=-MaxParallelActions=' + str(args.max_actions)])
    candidates = list((output / 'Package').rglob('*.apk'))
    if len(candidates) != 1:
        sys.exit(f'Expected one Development ASTC APK, found {len(candidates)}; inspect packaging output.')
    if list((output / 'Package').rglob('*.obb')):
        sys.exit('External OBB data found. Investigate content size before offering a single-file judge APK.')
    apk = output / 'ODYSSEY-Judge-Android-v1.apk'
    shutil.copy2(candidates[0], apk)
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        assert 'AndroidManifest.xml' in names
        # UEDeployAndroid embeds its ZIP-format OBB as assets/main.obb.png in a single APK.
        # Direct pak/IoStore payloads are also accepted; an external OBB is rejected above.
        content = [n for n in names if n.startswith('assets/') and n.endswith(('.pak', '.ucas'))]
        if 'assets/main.obb.png' in names:
            with archive.open('assets/main.obb.png') as embedded:
                with zipfile.ZipFile(embedded) as data:
                    content.extend(n for n in data.namelist() if n.endswith(('.pak', '.ucas')))
        assert content, 'Missing embedded game content'
        assert any(n.startswith('lib/arm64-v8a/') and n.endswith('.so') for n in names), 'Missing ARM64 game library'
        assert not any(n.startswith(('lib/x86/', 'lib/x86_64/', 'lib/armeabi-v7a/')) for n in names), 'Unexpected non-ARM64 ABI'
        for name in names:
            if name.startswith('lib/arm64-v8a/') and name.endswith('.so'):
                with archive.open(name) as stream:
                    header = stream.read(20)
                assert header[:4] == b'\x7fELF' and header[4] == 2 and int.from_bytes(header[18:20], 'little') == 183, name
    tools = sdk / 'build-tools' / sdk_spec['build-tools']
    signer = tools / ('apksigner.bat' if windows else 'apksigner')
    aapt = tools / ('aapt.exe' if windows else 'aapt')
    with (output / 'apk-signature.txt').open('w') as log:
        engine_run_with_log = ['cmd.exe', '/d', '/c', signer] if windows else [signer]
        run([*engine_run_with_log, 'verify', '--verbose', '--print-certs', apk], stdout=log, stderr=subprocess.STDOUT)
    with (output / 'apk-badging.txt').open('w') as log:
        run([aapt, 'dump', 'badging', apk], stdout=log, stderr=subprocess.STDOUT)
    badging = (output / 'apk-badging.txt').read_text()
    assert "name='org.odyssey.judge'" in badging and "'arm64-v8a'" in badging
    sha = hashlib.file_digest(apk.open('rb'), 'sha256').hexdigest()
    (output / 'ODYSSEY-Judge-Android-v1.sha256.txt').write_text(sha + '  ' + apk.name + '\n')
    receipt = {'created_utc': datetime.now(timezone.utc).isoformat(), 'commit': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'unreal': version,
        'android_packages_actually_used': sdk_spec, 'configuration': 'Development', 'renderer': 'Vulkan mobile forward / ASTC',
        'architecture': 'arm64-v8a', 'apk': apk.name, 'size_bytes': apk.stat().st_size, 'sha256': sha,
        'signature_verified': True, 'desktop_automation': 'not_run', 'installed_on_phone': False,
        'gameplay_on_android': 'UNTESTED', 'measured_fps': None, 'peak_memory_mb': None}
    (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    shutil.copy2(ROOT / 'Docs/ANDROID_JUDGE_INSTALL.md', output)
    if args.desktop_regression:
        try:
            editor = engine / ('Engine/Binaries/Win64/UnrealEditor-Cmd.exe' if windows else 'Engine/Binaries/Linux/UnrealEditor-Cmd')
            # Relevant desktop regression checks execute on the builder only, using the existing flow/slice tests.
            run([editor, project, '-unattended', '-NullRHI', '-nosplash', '-nosound',
                 '-ExecCmds=Automation RunTests Odyssey.Space.Flow+Odyssey.Slice.Engineering',
                 '-TestExit=Automation Test Queue Empty', '-ReportExportPath=' + str(output / 'DesktopAutomation'),
                 '-abslog=' + str(output / 'desktop-automation.log')])
            # The exported automation report must prove both suites ran and had no failures.
            report_path = output / 'DesktopAutomation/index.json'
            if not report_path.is_file():
                sys.exit('Automation report missing; do not infer test success from an editor exit code.')
            report = json.loads(report_path.read_text(encoding='utf-8-sig'))
            tests = report.get('tests', [])
            for prefix in ('Odyssey.Space.Flow', 'Odyssey.Slice.Engineering'):
                matches = [t for t in tests if t.get('fullTestPath', '').startswith(prefix)]
                if not matches or any(t.get('state') != 'Success' for t in matches):
                    sys.exit('Required desktop regression suite did not pass: ' + prefix)
            if report.get('failed', 0) or report.get('notRun', 0):
                sys.exit('Desktop automation has failed or unexecuted tests.')
            receipt['desktop_automation'] = 'passed'
        except (subprocess.CalledProcessError, SystemExit, AssertionError, OSError, ValueError) as error:
            receipt['desktop_automation'] = 'failed_or_unverified'
            (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
            raise SystemExit('APK candidate preserved, but desktop regression did not pass: ' + str(error))
        (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))

if __name__ == '__main__':
    main()

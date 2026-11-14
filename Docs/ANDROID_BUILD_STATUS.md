# Android judge candidate — NOT an APK release

Work is confined to `feature/android-judge-build`, based on `feature/odyssey-space-experience` at `e102d34a9e115ce8871162431c2314d53d67154e`.

## Verified so far

- Inspected installed Unreal **5.8.4** source/toolchain configuration without launching Unreal.
- Engine `Engine/Config/Android/Android_SDK.json` selects **Android API 36**, **Build Tools 36.0.0**, **NDK r27c / 27.2.12479018**, **CMake 3.22.1**.
- Local NDK metadata matches 27.2.12479018; Java 17.0.20.1 is installed. Complete Android SDK/build-tools/sdkmanager are missing locally. None was used to compile an APK.
- Installed official Google SDK Platform Tools **37.0.1** in the task workspace, without a global install. `adb devices -l`: **no connected device**.
- GitHub repository runner inventory: **zero self-hosted runners**. Repository artifact inventory: **zero artifacts** at inspection.
- CPU protocol suite: **26/26 cases, 959 checks passed** locally.
- CPU project/config checks passed; desktop default config, source art and content/maps remain unchanged against the base commit.
- Python helpers parse; the build helper refuses macOS before invoking Unreal.

## Implemented, pending Unreal compilation and device validation

Android-only platform config adds ARM64, Vulkan mobile forward, ASTC recipe, two startup/travel maps and an embedded-data Development APK target. Lumen, VSM, Nanite and volumetrics are disabled only on Android. UE's existing mobile rect-light-to-spotlight path remains available. The 30 FPS limit and 384 MB texture pool are initial budgets, not measured performance. Android World/Skybox mip caps are 2048; source images and UI groups are preserved. Nanite fallback mesh quality, actual cooked texture residency, mobile material/shader fidelity and GPU compatibility still require Unreal/device inspection. No fallback mesh has been rebuilt or certified.

Native UMG controls use safe zones, independent movement/look touch capture, existing movement/interaction actions, destination selection, launch, camera, descent and return to orbit. Android uses a dedicated touch HUD; the desktop HUD and animated logo remain intact. Small-screen layout, cutouts, simultaneous touches, resume, orientation and all gameplay are **untested on hardware**.

No real `odyssey.game.v1` production game backend was verified. The live web frontend is not evidence of a reachable game backend. Android judge config therefore explicitly disables backend session startup and retries. The station uses its existing PlayerStart and local doors/equipment presentations; backend-mediated incident decisions remain unavailable. No fake backend success, campaign state or scientific outcome is generated. Desktop backend integration remains intact.

Explicit plugin descriptor inspection is recorded in `ANDROID_PLUGIN_AUDIT.json`; descriptor compatibility is not an Android runtime test. Existing editor plugins retain Editor target restrictions. AndroidFileServer is denied on Android and its network settings are disabled. No new plugin or runtime package dependency was added.

## Build on a provisioned Windows/Linux x86_64 machine

Do not run Unreal, cook shaders, or rebuild the engine on the 8 GB Mac. Supply a licensed matching native UE 5.8.4 installation on a builder with at least 80 GiB free and preferably 32+ GB RAM. The macOS editor binary cannot serve as a native Windows/Linux editor/cooker.

```sh
git clone --single-branch --branch feature/android-judge-build https://github.com/geniusa2009-stack/odyssey.git
git -C odyssey lfs pull
cd odyssey
```

Set `ANDROID_HOME` and `JAVA_HOME` on that builder. Use its official SDK Manager with the exact packages selected by the installed engine:

```sh
sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0" "ndk;27.2.12479018" "cmake;3.22.1"
```

Review/accept SDK licenses using the official SDK tools. Do not commit SDK paths or signing material. Check native-engine and Android prerequisites through the helper's Unreal Turnkey `VerifySdk` step; a failed SDK verification stops the build.

Linux example (replace the engine path):

```sh
python3 Tools/Android/build_judge.py --engine /path/to/UE-5.8.4 --output Artifacts/AndroidJudge
```

Windows PowerShell example:

```powershell
python Tools/Android/build_judge.py --engine 'D:\UE-5.8.4' --output Artifacts/AndroidJudge
```

The helper first compiles the native project editor on the builder, then runs Android Development BuildCookRun for the two maps. It validates APK ARM64 ELF libraries, embedded data, package identity and signature; it refuses an external OBB package. It then emits the APK, SHA-256, actual size, packaging logs/metadata and an explicitly untested-device receipt. Default Unreal Development signing stays local; private keys/passwords must never enter git or artifacts.

For existing desktop regression suites, add `--desktop-regression` on a builder with a reachable development backend. The helper runs `Odyssey.Space.Flow` and `Odyssey.Slice.Engineering` and checks the exported test report. These Unreal suites have **not** been executed in this Android task; protocol/static checks are not substitutes.

Alternatively register a private, non-Mac GitHub runner with label `odyssey-ue-5.8.4-android`, set repository variable `ODYSSEY_ANDROID_ENGINE_ROOT`, and configure its Android/Java environment. Run **Android judge candidate** manually on this branch with `build_android=true` and the matching Windows/Linux choice. Heavy jobs never run automatically on push. Do not execute untrusted pull requests on this runner.

## Physical phone checkpoint

After the APK exists, connect and authorize a phone, then:

```sh
python3 Tools/Android/device_smoke.py --apk Artifacts/AndroidJudge/ODYSSEY-Judge-Android-v1.apk --serial PHONE_SERIAL --output Artifacts/DeviceSmoke
```

This only proves installation/activity startup/process presence where its results say so. Visually verify logo/menu, Solar Transit, Earth/Moon/Mars travel, Earth Command, movement/look, equipment, cutouts, resume and rotation. Record the phone/Android version, actual startup-to-menu time, sustained frame times/FPS, memory and thermals. A process start is not a successful main-menu checkpoint. Commit and push the first verified install-to-menu milestone immediately; do not create a release/verified commit before that happens.

## Outstanding delivery

**No APK, APK size, APK SHA-256, successful install, Android menu/gameplay result, FPS or peak memory measurement exists yet.** The blocking prerequisite is a usable non-Mac UE Android build machine/runner. No Android builder has been provisioned, purchased or started. Once an APK exists, back it up with its checksum and receipt to an authorized artifact location before judging. This source candidate is not a release.

## Tooling report

- Existing: UE 5.8.4 source/config and built Mac editor metadata (inspected only; Epic license); project UMG/Slate, Enhanced Input and runtime plugins (existing engine dependencies); Git/Git LFS; Python 3; Clang native protocol tests.
- Installed: Google Android SDK Platform Tools 37.0.1 from `https://dl.google.com/android/repository/platform-tools-latest-darwin.zip`, for ADB device detection only. SDK license/third-party notices are included in its package. It is a local development tool, not a shipped game dependency.
- No newly enabled or installed Unreal plugin. AndroidFileServer is excluded from this Android target, while desktop defaults remain available.
- Build signing keys, SDK/NDK/JDK, ADB, editor tooling, captures, test receipts and source-art folders do not belong in the judge APK. CI artifacts should contain only intended APK/checksum/receipts, never signing keystores or credentials. Do not ship this untested Development candidate as a production release.

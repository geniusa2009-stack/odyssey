# ODYSSEY — install on an Android phone (judges)

**You need:**
- an Android phone with a 64-bit (ARM64) processor, Vulkan graphics and Android 8.0 or newer (most phones from 2019 onwards);
- about 1 GB of free storage;
- no account, internet connection or extra download.

## Install
1. Copy `ODYSSEY-Judge-Android-v1.apk` to the phone, or download it there.
2. Open the file. If Android asks, allow **Install unknown apps** for the app you opened it with (Files, Chrome or Drive).
3. Tap **Install**, then **Open**.

To install from a computer instead, use `adb install ODYSSEY-Judge-Android-v1.apk`.

To check the file, its SHA-256 should match `ODYSSEY-Judge-Android-v1.sha256.txt`.

## Play
- Hold the phone in landscape. The first launch prepares graphics for a short moment, then the ODYSSEY logo plays. Tap to skip it.
- **Main menu:** tap **Begin Mission** to go down to the Earth Command station, or **Solar Transit** to fly between Earth, the Moon and Mars.
- **Solar Transit:** tap a destination in the planner, then **LAUNCH**. **CAMERA** changes the view, **DESCEND** (at Earth) enters the station, and **MENU** returns to the menu.
- **Earth Command station:**
  - The left stick moves you, and dragging on the right side of the screen looks around.
  - **USE** appears next to a console. While a panel is open, **NEXT** and **BACK** work its controls.
  - **ORBIT** (top right) or the Android back gesture returns to space.

This judge build runs fully offline. The station can be explored, but actions that need the live ODYSSEY mission server show *"Live station link required — offline demo"*.

"""Station display and signage textures (Mission Control, Training) for ODYSSEY.

Renders diegetic screen content and signs with Pillow, using the Roboto / Droid Sans Mono fonts that
ship with Unreal Engine (Engine/Content/Slate/Fonts, Apache 2.0). Outputs PNGs to ../Textures.

    python generate_station_textures.py [--ue ~/TitanEngine/UE-5.8.4]
"""
import argparse
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Textures")
ION, ION_DIM = (97, 190, 210), (40, 95, 112)
WHITE, MUTED = (232, 236, 238), (142, 151, 160)
AMBER, RED = (214, 154, 53), (184, 71, 67)
BG, PANEL = (8, 14, 20), (16, 24, 32)


class Fonts:
    def __init__(self, ue):
        d = os.path.join(os.path.expanduser(ue), "Engine", "Content", "Slate", "Fonts")
        self.d = d

    def get(self, name, size):
        return ImageFont.truetype(os.path.join(self.d, name), size)

    def bold(self, s): return self.get("Roboto-Bold.ttf", s)
    def reg(self, s): return self.get("Roboto-Regular.ttf", s)
    def light(self, s): return self.get("Roboto-Light.ttf", s)
    def mono(self, s): return self.get("DroidSansMono.ttf", s)


def tracked(draw, xy, text, font, fill, tracking=0.0, anchor_right=False):
    """Text with letter spacing (tracking in px)."""
    x, y = xy
    widths = [draw.textlength(c, font=font) for c in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)
    if anchor_right:
        x -= total
    for c, w in zip(text, widths):
        draw.text((x, y), c, font=font, fill=fill)
        x += w + tracking
    return total


def grid(draw, w, h, step, color):
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=color, width=1)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=color, width=1)


def chrome(draw, w, h, title, sub, F):
    draw.rectangle([0, 0, w, 54], fill=PANEL)
    draw.rectangle([0, 54, w, 56], fill=ION_DIM)
    # brand mark
    cx, cy, r = 34, 27, 14
    draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], outline=ION, width=3)
    draw.polygon([(cx, cy - 6), (cx + 6, cy), (cx, cy + 6), (cx - 6, cy)], fill=ION)
    tracked(draw, (62, 13), title, F.bold(24), WHITE, 3)
    tracked(draw, (w - 24, 18), sub, F.mono(16), MUTED, 2, anchor_right=True)


def glow(img, radius=6, amount=0.55):
    g = img.filter(ImageFilter.GaussianBlur(radius))
    return Image.blend(img, Image.composite(g, img, g.convert("L")), amount)


def main_display(F):
    w, h = 2048, 768
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    grid(d, w, h, 64, (14, 22, 30))
    chrome(d, w, h, "EARTH COMMAND  /  MISSION OPERATIONS", "ODYSSEY DEEP SPACE PROGRAM   UTC 14:22:08", F)
    # orbital map: Earth, lunar orbit, Mars transfer
    ex, ey = 520, 420
    d.ellipse([ex - 300, ey - 300, ex + 300, ey + 300], outline=(30, 60, 72), width=2)
    d.ellipse([ex - 190, ey - 190, ex + 190, ey + 190], outline=ION_DIM, width=2)
    d.ellipse([ex - 54, ey - 54, ex + 54, ey + 54], fill=(26, 70, 110), outline=ION, width=3)
    d.arc([ex - 54, ey - 54, ex + 54, ey + 54], 200, 330, fill=(70, 140, 90), width=10)
    mx, my = ex + int(190 * math.cos(-0.7)), ey + int(190 * math.sin(-0.7))
    d.ellipse([mx - 14, my - 14, mx + 14, my + 14], fill=(170, 172, 176))
    tracked(d, (mx + 22, my - 10), "LUNA", F.mono(18), MUTED, 2)
    tracked(d, (ex - 34, ey + 64), "EARTH", F.mono(18), WHITE, 2)
    # transfer arcs
    d.arc([ex - 330, ey - 260, ex + 470, ey + 300], 290, 352, fill=AMBER, width=3)
    for t in range(0, 360, 14):
        a = math.radians(t)
        d.point((ex + 300 * math.cos(a), ey + 300 * math.sin(a)), fill=ION_DIM)
    tracked(d, (ex + 330, ey - 300), "MARS TRANSFER  /  207 D", F.mono(18), AMBER, 2)
    # spacecraft marker
    sx, sy = ex + int(190 * math.cos(0.9)), ey + int(190 * math.sin(0.9))
    d.polygon([(sx, sy - 9), (sx + 9, sy), (sx, sy + 9), (sx - 9, sy)], fill=WHITE)
    tracked(d, (sx + 14, sy + 4), "OTV-1 MERIDIAN", F.mono(16), WHITE, 2)
    # telemetry column
    x0 = 1120
    tracked(d, (x0, 96), "STATION SYSTEMS", F.bold(24), WHITE, 3)
    rows = [("POWER BUS A", 0.92, ION), ("POWER BUS B", 0.88, ION), ("THERMAL LOOP", 0.74, ION), ("AIR HANDLING", 0.81, ION),
            ("WATER RECOVERY", 0.66, ION), ("COMMS UPLINK", 0.97, ION), ("STATION BATTERY", 0.58, AMBER)]
    y = 150
    for name, v, c in rows:
        tracked(d, (x0, y), name, F.mono(18), MUTED, 2)
        d.rectangle([x0 + 300, y + 6, x0 + 760, y + 16], fill=(22, 32, 42))
        d.rectangle([x0 + 300, y + 6, x0 + 300 + int(460 * v), y + 16], fill=c)
        tracked(d, (x0 + 860, y), f"{int(v * 100):3d} %", F.mono(18), WHITE, 1, anchor_right=True)
        y += 46
    # timeline
    d.rectangle([x0, 520, x0 + 860, 522], fill=ION_DIM)
    for i, (t, label) in enumerate([(0.05, "T-02:00 CREW BRIEF"), (0.32, "T-00:40 TRAINING SIM"), (0.6, "T+00:00 TLI WINDOW"), (0.8, "T+03:02 LUNA ARRIVAL")]):
        px = x0 + int(860 * t)
        d.rectangle([px - 2, 512, px + 2, 530], fill=WHITE if i == 2 else ION)
        tracked(d, (px - 8, 540 + (i % 2) * 28), label, F.mono(15), WHITE if i == 2 else MUTED, 1)
    tracked(d, (x0, 640), "NEXT WINDOW  TLI  /  T-00:47:12", F.bold(30), ION, 3)
    tracked(d, (x0, 690), "CREW 4  /  OTV-1 MERIDIAN  /  GO FOR TRAINING", F.mono(18), MUTED, 2)
    return glow(img)


def systems_display(F, title, sub, rows, footer):
    w, h = 1024, 640
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    grid(d, w, h, 48, (13, 20, 28))
    chrome(d, w, h, title, sub, F)
    y = 96
    for name, value, frac, c in rows:
        tracked(d, (32, y), name, F.mono(18), MUTED, 2)
        tracked(d, (w - 32, y), value, F.bold(22), WHITE, 2, anchor_right=True)
        d.rectangle([32, y + 34, w - 32, y + 40], fill=(22, 32, 42))
        d.rectangle([32, y + 34, 32 + int((w - 64) * frac), y + 40], fill=c)
        y += 72
    # waveform
    pts = [(32 + i * 4, h - 120 + int(26 * math.sin(i * 0.21) * math.sin(i * 0.037 + 1.3))) for i in range(0, (w - 64) // 4)]
    d.line(pts, fill=ION, width=2)
    tracked(d, (32, h - 60), footer, F.mono(17), ION, 2)
    return glow(img, 4, 0.4)


def sign(F, text, sub, w=1024, h=256, color=WHITE):
    img = Image.new("RGB", (w, h), (24, 28, 33))
    d = ImageDraw.Draw(img)
    d.rectangle([0, h - 10, w, h], fill=ION_DIM)
    cx, cy, r = 70, h // 2 - 6, 34
    d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], outline=ION, width=5)
    d.polygon([(cx, cy - 13), (cx + 13, cy), (cx, cy + 13), (cx - 13, cy)], fill=ION)
    tracked(d, (140, 56), text, F.bold(76), color, 8)
    tracked(d, (144, 160), sub, F.mono(26), MUTED, 5)
    return img


def floor_text(F, text, w=1024, h=256):
    img = Image.new("RGB", (w, h), (20, 23, 27))
    d = ImageDraw.Draw(img)
    tw = d.textlength(text, font=F.bold(64)) + 6 * (len(text) - 1)
    tracked(d, ((w - tw) / 2, 82), text, F.bold(64), AMBER, 6)
    return img


def hull_marking(F, w=2048, h=512):
    """Printed hull marking for OTV-1 Meridian on aerospace white (u along the hull toward the nose)."""
    img = Image.new("RGB", (w, h), (216, 217, 213))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 28, w, 40], fill=(97, 190, 210))
    d.rectangle([0, h - 40, w, h - 34], fill=(28, 32, 37))
    cx, cy, r = 190, h // 2 - 10, 92
    d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], outline=(28, 32, 37), width=14)
    d.polygon([(cx, cy - 34), (cx + 34, cy), (cx, cy + 34), (cx - 34, cy)], fill=(40, 120, 140))
    tracked(d, (340, 120), "ODYSSEY", F.bold(210), (28, 32, 37), 26)
    tracked(d, (352, 372), "OTV-1  MERIDIAN   /   EARTH COMMAND   /   CREW TRANSIT", F.mono(44), (69, 75, 82), 10)
    return img


def save(img, name, out=None):
    out = out or OUT
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, name + ".png")
    img.save(p, optimize=True)
    print("wrote", p, img.size)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ue", default="~/TitanEngine/UE-5.8.4")
    F = Fonts(ap.parse_args().ue)
    save(main_display(F), "T_MCC_MainDisplay")
    save(systems_display(F, "POWER  /  THERMAL", "ENGINEERING LINK  NOMINAL",
                         [("BUS A LOAD", "41.2 KW", 0.62, ION), ("BUS B LOAD", "38.9 KW", 0.58, ION), ("THERMAL LOOP A", "18.4 C", 0.44, ION),
                          ("THERMAL LOOP B", "18.9 C", 0.46, ION), ("BATTERY RESERVE", "58 %", 0.58, AMBER), ("CABIN PRESSURE", "101.2 KPA", 0.9, ION)],
                         "TELEMETRY STREAM  /  ENG-01  /  0.5 HZ"), "T_MCC_SystemsDisplay")
    save(systems_display(F, "CREW  /  COMMS", "UPLINK  DSN-34  LOCKED",
                         [("CREW READINESS", "4 / 4", 1.0, ION), ("HEART RATE AVG", "71 BPM", 0.45, ION), ("UPLINK MARGIN", "11.4 DB", 0.76, ION),
                          ("DOWNLINK", "48 MBPS", 0.8, ION), ("LATENCY LUNA", "1.28 S", 0.3, ION), ("NEXT PASS", "T-00:32", 0.7, AMBER)],
                         "VOICE LOOP  FLIGHT  /  CAPCOM  /  TRAINING"), "T_MCC_CommsDisplay")
    save(systems_display(F, "SIMULATOR  /  SESSION 07", "ASCENT PROFILE  /  INSTRUCTOR",
                         [("SCENARIO", "TLI ABORT", 0.35, AMBER), ("TRAINEE", "CREW 01  /  CDR", 1.0, ION), ("MOTION BASE", "ARMED", 0.9, ION),
                          ("CABIN FAULTS INJECTED", "3", 0.3, AMBER), ("SCORE", "86 / 100", 0.86, ION), ("ELAPSED", "00:18:42", 0.5, ION)],
                         "INSTRUCTOR OVERRIDE AVAILABLE  /  E-STOP LIVE"), "T_TRN_SessionDisplay")
    save(systems_display(F, "TRAINEE MONITORING", "BIOMEDICAL  /  CABIN",
                         [("HEART RATE", "94 BPM", 0.55, ION), ("SPO2", "98 %", 0.98, ION), ("RESPIRATION", "17 /MIN", 0.4, ION),
                          ("G LOAD (SIM)", "2.4 G", 0.48, AMBER), ("CABIN TEMP", "21.6 C", 0.5, ION), ("WORKLOAD INDEX", "0.62", 0.62, ION)],
                         "RECORDING  /  SESSION 07  /  CAM 1-4"), "T_TRN_MonitorDisplay")
    save(sign(F, "MISSION CONTROL", "EARTH COMMAND  /  FLIGHT OPERATIONS"), "T_Sign_MissionControl")
    save(sign(F, "TRAINING BAY 01", "SIMULATION  /  CREW CERTIFICATION"), "T_Sign_Training")
    save(floor_text(F, "SIMULATOR ZONE  -  KEEP CLEAR"), "T_Floor_KeepClear")
    save(hull_marking(F), "T_OTV_Marking", os.path.join(os.path.dirname(os.path.dirname(OUT)), "OdysseySpace", "Textures"))

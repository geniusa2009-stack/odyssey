import sys, runpy, unreal
for m in ("odyssey_kit_geometry", "odyssey_slice_assets"):
    sys.modules.pop(m, None)
runpy.run_path("/Users/ahmedibrahim/Desktop/كل المشاريع/ODYSSEY/النسخة الحالية/مصادر العمل المحلية/ODYSSEY-GAME/Tools/Editor/generate_slice_map.py", run_name="__main__")

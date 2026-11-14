src = open("/Users/ahmedibrahim/Desktop/كل المشاريع/ODYSSEY/النسخة الحالية/مصادر العمل المحلية/ODYSSEY-GAME/Tools/Editor/capture_engineering_views.py", encoding="utf-8").read().replace("QUIT = True", "QUIT = False")
src = src.replace('OUT = os.path.join(unreal.Paths.project_saved_dir(), "Odyssey", "Screenshots")', 'OUT = "/private/tmp/claude-501/-Users-ahmedibrahim-Desktop-------------ODYSSEY------------------------------------ODYSSEY-GAME/31e62c89-a087-4e72-9653-22be5588b86d/scratchpad/shots/" + TAG')
exec(compile("TAG = 'baseline'\n" + src, "capture", "exec"), {"__name__": "__main__"})

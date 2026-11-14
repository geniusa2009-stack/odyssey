import os, sys, io, traceback, time, unreal
Q = "/private/tmp/claude-501/-Users-ahmedibrahim-Desktop-------------ODYSSEY------------------------------------ODYSSEY-GAME/31e62c89-a087-4e72-9653-22be5588b86d/scratchpad/ueq2"
state = {"last": 0.0, "busy": False}
def tick(dt):
    if state["busy"] or time.time() - state["last"] < 1.0:
        return
    state["last"] = time.time()
    for name in sorted(os.listdir(Q)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(Q, name)
        run = path + ".running"
        os.rename(path, run)
        state["busy"] = True
        out, old, ok = io.StringIO(), sys.stdout, True
        sys.stdout = out
        try:
            exec(compile(open(run, encoding="utf-8").read(), path, "exec"), {"__name__": "__main__", "__file__": path})
        except Exception:
            ok = False
            out.write(traceback.format_exc())
        finally:
            sys.stdout = old
            state["busy"] = False
        with open(path[:-3] + (".ok" if ok else ".fail"), "w", encoding="utf-8") as f:
            f.write(out.getvalue())
        return
unreal.register_slate_post_tick_callback(tick)
open(os.path.join(Q, "READY"), "w").write("ready")

# Headless logic test for studio_imgui (no window needed).
import dearpygui.dearpygui as dpg

dpg.create_context()
import particle_studio as PS
import studio_imgui as S

states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
tr = S.SimEngine._build_tracks(states, "2d")
assert len(tr) == 2 and tr[0]["shape"] == "circle", tr
k, e, raw = S.SimEngine._locate(tr, 0.0)
assert (k, raw) == (0, 0.0), (k, raw)
s = S.SimEngine.sample_tracks(tr, 0.25, 0.5, 0.5)
assert s["shape"] == "circle", s

eng = S.SimEngine()
em2d = PS.default_emitter("2d")
p = eng.spawn(em2d, "2d", 400, 300, (0, 0, 0),
              S.SimEngine._build_tracks(states, "2d"))
assert len(p) == 22 and p[9] > 0, len(p)
em3d = PS.default_emitter("3d")
p3 = eng.spawn(em3d, "3d", 0, 0, (0, 0, 0),
               S.SimEngine._build_tracks(states, "3d"))
assert len(p3) == 22, len(p3)

n = eng.step_py(em2d, "2d", 400, 300, (0, 0, 0),
                {"yaw": 0.7, "pitch": 0.42, "zoom": 1.0, "ox": 0.0,
                 "oy": 0.0, "focal": 620.0},
                S.SimEngine._build_tracks(states, "2d"), 0.04, 800)
assert n > 0, n

app = S.App()
eff = app.current_effect()
errs = PS.validate_effect(eff)
assert not errs, errs
assert eff["type"] == "2d" and len(eff["states"]) == 2

app.history_commit()
app.em["flow"] = 999
app.history_commit()
app.undo()
assert app.em["flow"] == 40, app.em["flow"]
app.redo()
assert app.em["flow"] == 999, app.em["flow"]

import particle_core
ce = particle_core.Engine()
ce.configure(em2d, S.SimEngine._build_tracks(states, "2d"), False)
out = ce.step(0.04, 400, 300, 0, 0, 0, 0, 0, 0, 300,
              0.7, 0.42, 1.0, 0, 0, 620.0, 400, 312)
print("cpp x-n:", len(out["x"]))
print("HEADLESS-LOGIC-OK")
dpg.destroy_context()

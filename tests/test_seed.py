# Deterministic seed (Phase 7.5): same nonzero seed replays identically
# within each renderer; seed 0 preserves legacy unseeded behavior.
import bootstrap  # noqa: F401

import particle_studio as PS
import studio_imgui as S

states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
tracks = S.SimEngine._build_tracks(states, "2d")
em = PS.default_emitter("2d")
em["mode"] = "Infinite"
em["flow"] = 500.0
cam = {"yaw": 0.7, "pitch": 0.42, "zoom": 1.0, "ox": 0.0, "oy": 0.0, "focal": 620.0}


def run_py(seed, steps=60):
    eng = S.SimEngine()
    eng.seed_sim(seed)
    for _ in range(steps):
        eng.step_py(em, "2d", 400, 300, (0, 0, 0), cam, tracks, 1 / 60, 2000)
    return [(round(p[0], 6), round(p[1], 6), round(p[4], 6)) for p in eng.parts]


a = run_py(1234)
b = run_py(1234)
assert a and a == b, "python seed replay mismatch"
c = run_py(999)
assert c != a, "different seeds must diverge"
d = run_py(0)
assert d, "seed 0 must still simulate"
print(f"python seed replay: OK ({len(a)} parts)")


# NOTE: configure() itself reseeds from emitter.seed — the primary path:
def run_cxx_cfg(seed, steps=60):
    import particle_core as CXX
    e = CXX.Engine()
    e.set_seed(1)  # arbitrary boot (overridden by emitter seed when nonzero)
    em2 = dict(em)
    em2["seed"] = seed
    e.configure(em2, tracks, False)
    out = None
    for _ in range(steps):
        out = e.step(1 / 60, 400, 300, 0, 0, 0, 0, 0, 0, 2000,
                     0.7, 0.42, 1.0, 0, 0, 620.0, 400, 300)
    return [(round(x, 6), round(y, 6)) for x, y in zip(out["x"], out["y"])]


a = run_cxx_cfg(777)
b = run_cxx_cfg(777)
assert a and a == b, "c++ seed replay mismatch"
c = run_cxx_cfg(778)
assert c != a, "c++ different seeds must diverge"
d = run_cxx_cfg(0)
assert d, "c++ seed 0 must still simulate"
print(f"c++ seed replay: OK ({len(a)} parts)")
print("SEED-OK")

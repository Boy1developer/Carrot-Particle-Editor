# Force fields (Phase 7.3): pure-formula asserts, off-means-identical proof,
# determinism under seed, per-field behavior, collision invariant.
# Covers the Python sim and the C++ core with the same scenarios.
import bootstrap  # noqa: F401

import particle_studio as PS
import studio_imgui as S

F = {'turbulence': {'amount': 2.0, 'scale': 0.05, 'speed': 1.0},
     'vortex': {'strength': 3.0},
     'attractor': {'x': 1.0, 'y': 2.0, 'z': 3.0, 'strength': 4.0, 'radius': 200.0},
     'collision': {'planeY': None, 'bounce': 0.5, 'friction': 0.1}}


def close(a, b, tol=1e-9):
    assert len(a) == len(b), (a, b)
    assert all(abs(x - y) <= tol for x, y in zip(a, b)), (a, b)


close(PS.field_accel(10.0, 20.0, 30.0, 1.5, F, 0.0, 0.0, 0.0, False),
      (-2.538150573593, -2.663130821889, 0.264878016006))
close(PS.field_accel(10.0, 20.0, 0.0, 1.5, F, 0.0, 0.0, 0.0, True),
      (-3.075640758651, 0.156763895690, 2.513097445525))
assert PS.field_accel(10, 20, 30, 1.5, {}, 0, 0, 0, False) == (0.0, 0.0, 0.0)
assert PS.field_accel(10, 20, 30, 1.5, None, 0, 0, 0, False) == (0.0, 0.0, 0.0)
assert PS.fields_active(F) is True
assert PS.fields_active({}) is False
assert PS.fields_active(None) is False
assert PS.fields_active({'collision': {'planeY': 100}}) is True
print("pure formulas: OK")

states = [PS.default_state("birth", 0), PS.default_state("death", 1)]
tracks = S.SimEngine._build_tracks(states, "2d")
cam = {"yaw": 0.7, "pitch": 0.42, "zoom": 1.0, "ox": 0.0, "oy": 0.0, "focal": 620.0}


def base_em():
    em = PS.default_emitter("2d")
    em["mode"] = "Infinite"
    em["flow"] = 500.0
    return em


def run_py(em, seed=1234, steps=60):
    eng = S.SimEngine()
    eng.seed_sim(seed)
    for _ in range(steps):
        eng.step_py(em, "2d", 400, 300, (0, 0, 0), cam, tracks, 1 / 60, 2000)
    return [(round(p[0], 6), round(p[1], 6)) for p in eng.parts]


def run_cxx(em, seed=1234, steps=60):
    import particle_core as CXX
    e = CXX.Engine()
    e.set_seed(1)
    em2 = dict(em)
    em2["seed"] = seed
    e.configure(em2, tracks, False)
    out = None
    for _ in range(steps):
        out = e.step(1 / 60, 400, 300, 0, 0, 0, 0, 0, 0, 2000,
                     0.7, 0.42, 1.0, 0, 0, 620.0, 400, 300)
    return [(round(x, 6), round(y, 6)) for x, y in zip(out["x"], out["y"])]


# legacy dict without any fields key behaves exactly like all-zero fields
em_nokey = base_em()
del em_nokey["fields"]
em_zero = base_em()
for label, run in (("py", run_py), ("cxx", run_cxx)):
    a = run(em_nokey)
    b = run(em_zero)
    assert a and a == b, (label, "fields-off mismatch")
print("fields-off identical: OK (py + cxx)")

# each field perturbs deterministically (seeded replay stable)
FIELD_CASES = {
    "turbulence": {"turbulence": {"amount": 60.0, "scale": 0.05, "speed": 2.0}},
    "vortex": {"vortex": {"strength": 30.0}},
    "attractor": {"attractor": {"x": 400.0, "y": 300.0, "z": 0.0,
                                "strength": 400.0, "radius": 2000.0}},
    "collision": {"collision": {"planeY": 290.0, "bounce": 0.4, "friction": 0.2}},
}
for label, run in (("py", run_py), ("cxx", run_cxx)):
    ref = run(em_zero)
    for name, patch in FIELD_CASES.items():
        em = base_em()
        em["fields"] = dict(em_zero["fields"])
        em["fields"][name] = patch[name]
        got = run(em)
        assert got and got != ref, (label, name, "field inert")
        again = run(em)
        assert got == again, (label, name, "not deterministic")
print("fields perturb + replay: OK (py + cxx)")

# collision invariant: nothing ends below the plane (both cores)
for label, run in (("py", run_py), ("cxx", run_cxx)):
    em = base_em()
    em["fields"] = dict(em_zero["fields"])
    em["fields"]["collision"] = FIELD_CASES["collision"]["collision"]
    for x, y in run(em):
        assert y >= 290.0 - 1e-9, (label, x, y)
print("collision invariant: OK (py + cxx)")

# attractor shrinks the cloud vs baseline (both cores)
def mean_r(pts):
    import math
    return sum(math.hypot(x - 400, y - 300) for x, y in pts) / max(1, len(pts))


for label, run in (("py", run_py), ("cxx", run_cxx)):
    em = base_em()
    em["fields"] = dict(em_zero["fields"])
    em["fields"]["attractor"] = FIELD_CASES["attractor"]["attractor"]
    assert mean_r(run(em)) < mean_r(run(em_zero)), label
print("attractor pulls: OK (py + cxx)")
print("FIELDS-OK")

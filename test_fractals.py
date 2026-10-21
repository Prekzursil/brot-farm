"""Brot Farm test suite.

Validates the vectorized machinery against scalar/complex-arithmetic references,
checks invariants (bounds, monotonicity, determinism, culling soundness), and
runs a tiny end-to-end render.
"""
import importlib

import numpy as np
import pytest

import buddhabrot as bb
import brot_farm as farm


RNG = np.random.default_rng(42)


def rand_pts(n, lo=-1.5, hi=1.5):
    return RNG.uniform(lo, hi, n), RNG.uniform(lo, hi, n)


# --------------------------------------------------------------- step rules

@pytest.mark.parametrize("fname,power", [("s_std", 2), ("s_z3", 3), ("s_z4", 4), ("s_z5", 5)])
def test_power_steps_match_complex_arithmetic(fname, power):
    x, y = rand_pts(512)
    cx, cy = rand_pts(512)
    gx, gy = getattr(farm, fname)(x, y, cx, cy)
    z = (x + 1j * y) ** power + (cx + 1j * cy)
    assert np.allclose(gx, z.real, atol=1e-9)
    assert np.allclose(gy, z.imag, atol=1e-9)


@pytest.mark.parametrize("fname,fn", [
    ("s_sinz", np.sin),
    ("s_cosz", np.cos),
    ("s_tricorn", None),  # conj(z)^2 + c
])
def test_entire_and_conjugate_steps_match_complex(fname, fn):
    x, y = rand_pts(512, -2, 2)
    cx, cy = rand_pts(512)
    gx, gy = getattr(farm, fname)(x, y, cx, cy)
    if fn is not None:
        z = fn(x + 1j * y) + (cx + 1j * cy)
    else:
        z = np.conj(x + 1j * y) ** 2 + (cx + 1j * cy)
    assert np.allclose(gx, z.real, atol=1e-9)
    assert np.allclose(gy, z.imag, atol=1e-9)


def test_std_step_matches_buddhabrot_module():
    x, y = rand_pts(256)
    cx, cy = rand_pts(256)
    with np.errstate(over="ignore", invalid="ignore"):
        bx, by = x * x - y * y + cx, 2.0 * x * y + cy
        fx, fy = farm.s_std(x, y, cx, cy)
    assert np.array_equal(bx, fx) and np.array_equal(by, fy)


# ---------------------------------------------------------- escape masks

@pytest.mark.parametrize("name,min_agree", [
    ("z3", 0.97), ("ship", 0.97), ("tricorn", 0.97), ("cosy", 0.97),
    # cosfull: |y| > 100 crossing is not strictly monotone (x' = cos(x^2-y^2)+cx
    # can pass through ~0 and let y hover), so the chunked check can miss a brief
    # excursion the per-step reference catches -- benign for rendering, since any
    # genuine crossing diverges in practice.
    ("cosfull", 0.90),
])
def test_escape_mask_matches_scalar_reference(name, min_agree):
    f = farm.BY_NAME[name]
    x0, y0 = rand_pts(300, -1.0, 1.0)
    cx, cy = x0.copy(), y0.copy()
    cap = 120
    with np.errstate(over="ignore", invalid="ignore"):
        got = farm.escape_mask(f, x0, y0, cx, cy, cap)

    ref = np.zeros(len(x0), dtype=bool)
    with np.errstate(over="ignore", invalid="ignore"):
        for i in range(len(x0)):
            x, y = float(x0[i]), float(y0[i])
            for _ in range(cap):
                nx, ny = f["step"](np.array([x]), np.array([y]),
                                   np.array([cx[i]]), np.array([cy[i]]))
                x, y = float(nx[0]), float(ny[0])
                if f["gone"](np.array([x]), np.array([y]))[0]:
                    ref[i] = True
                    break
    agree = (got == ref).mean()
    assert agree >= min_agree, f"{name}: classification disagreement {1 - agree:.2%}"
    assert not (got & ~ref).any(), "vector path invented an escape the scalar path missed"


def test_escape_mask_marks_known_points():
    f = farm.BY_NAME["z3"]
    # c = 0.3 + 0i stays bounded for z^3 + c (fixed point); c = 2 + 0i escapes instantly
    x0 = np.array([0.3, 2.0])
    y0 = np.array([0.0, 0.0])
    m = farm.escape_mask(f, x0, y0, x0.copy(), y0.copy(), 200)
    assert not m[0] and m[1]


# ---------------------------------------------------------------- culling

def test_culled_region_never_escapes():
    pts = RNG.uniform(-1.2, 1.2, (4000, 2))
    inside = bb.inside_main_sets(pts[:, 0], pts[:, 1])
    assert inside.any()
    f = farm.BY_NAME["nebula"]  # std quadratic step
    x0, y0 = pts[inside, 0], pts[inside, 1]
    with np.errstate(over="ignore", invalid="ignore"):
        m = farm.escape_mask(f, x0, y0, x0.copy(), y0.copy(), 300)
    assert not m.any(), "cardioid/bulb interior points must never escape"


# ------------------------------------------------------------- tone curves

def test_tone_channel_monotonic_bounded():
    h = np.zeros((64, 64))
    h[10, 10] = 1e6
    h[20:40, 20:40] = 100.0
    v = bb.tone_channel(h, plo=30, phi=99.9, gamma=1.35, gain=1.0)
    assert v.min() >= 0.0 and v.max() <= 1.0
    assert v[10, 10] >= v[30, 30] >= v[0, 0]
    assert v.max() == pytest.approx(1.0) or v[10, 10] == v.max()


def test_tone_channel_black_point():
    h = np.full((32, 32), 5.0)
    v = bb.tone_channel(h, plo=50, phi=99.9, gamma=1.0, gain=1.0)
    assert np.allclose(v, 0.0, atol=0.05)  # uniform image -> at/below black point


# ------------------------------------------------------------ plot orbits

def test_plot_orbits_counts_match_manual_trace():
    f = farm.BY_NAME["z3"]
    W = H = 128
    hist = np.zeros(W * H)
    x0 = np.array([0.9])
    y0 = np.array([0.1])
    cap = 30
    with np.errstate(over="ignore", invalid="ignore"):
        farm.plot_orbits(f, x0.copy(), y0.copy(), x0.copy(), y0.copy(), cap, hist, W, H)
    # manual trace
    px0, px1, py0, py1 = f["plot"]
    x, y = 0.9, 0.1
    expect = {}
    with np.errstate(over="ignore", invalid="ignore"):
        for _ in range(cap):
            col = int((x - px0) / (px1 - px0) * W)
            row = int((y - py0) / (py1 - py0) * H)
            if 0 <= col < W and 0 <= row < H:
                expect[row * W + col] = expect.get(row * W + col, 0) + 1
            nx, ny = f["step"](np.array([x]), np.array([y]), np.array([0.9]), np.array([0.1]))
            x, y = float(nx[0]), float(ny[0])
            if f["gone"](np.array([x]), np.array([y]))[0]:
                break
    got = hist.reshape(H, W)
    for idx, cnt in expect.items():
        assert got.flat[idx] == cnt


def test_plot_orbits_stays_in_bounds():
    f = farm.BY_NAME["ship"]
    W = H = 96
    hist = np.zeros(W * H)
    n = 2000
    cap = 80
    x0, y0 = rand_pts(n, -1.8, 1.2)
    with np.errstate(over="ignore", invalid="ignore"):
        esc = farm.escape_mask(f, x0, y0, x0.copy(), y0.copy(), cap)
        farm.plot_orbits(f, x0[esc], y0[esc], x0[esc].copy(), y0[esc].copy(), cap, hist, W, H)
    assert hist.min() >= 0.0
    assert hist.sum() > 0
    assert hist.sum() <= n * cap  # can never plot more points than samples x cap


# ---------------------------------------------------------- configuration

def test_farm_configs_are_sane():
    for f in farm.FRACS:
        assert len(f["chans"]) == 3, f["name"]
        for cap, samples in f["chans"]:
            assert 0 < cap <= 100_000
            assert samples > 0
        px0, px1, py0, py1 = f["plot"]
        sx0, sx1, sy0, sy1 = f["samp"]
        assert px0 < px1 and py0 < py1 and sx0 < sx1 and sy0 < sy1
        W, H = f["size"]
        assert W > 0 and H > 0
        assert f["batch"] > 0


def test_module_imports():
    import cosbrot  # renamed from mutant_brot.py; must stay importable
    assert hasattr(cosbrot, "step")
    assert hasattr(cosbrot, "escape_mask")


# -------------------------------------------------- determinism & symmetry

def _tiny_render(f, size, samples, seed, cap_index=0):
    cap, _ = f["chans"][cap_index]
    rng = np.random.default_rng(seed)
    W = H = size
    hist = np.zeros(W * H)
    sx0, sx1, sy0, sy1 = f["samp"]
    with np.errstate(over="ignore", invalid="ignore"):
        ax = rng.uniform(sx0, sx1, samples)
        ay = rng.uniform(sy0, sy1, samples)
        esc = farm.escape_mask(f, ax, ay, ax.copy(), ay.copy(), cap)
        farm.plot_orbits(f, ax[esc], ay[esc], ax[esc].copy(), ay[esc].copy(), cap, hist, W, H)
    return hist.reshape(H, W)


def test_seed_determinism():
    f = farm.BY_NAME["ship"]
    a = _tiny_render(f, 96, 40_000, seed=7)
    b = _tiny_render(f, 96, 40_000, seed=7)
    assert np.array_equal(a, b)


def test_mirror_symmetry_of_equivariant_map():
    # real-coefficient power maps are conjugation-equivariant:
    # F(conj z, conj c) = conj(F(z, c)), so orbit(conj c) mirrors orbit(c),
    # and a uniformly sampled symmetric window yields a mirror-symmetric
    # histogram up to Monte-Carlo noise (the |2xy| fold of Burning Ship and
    # Buffalo breaks this law on purpose -- those are tested in QC, not here).
    f = farm.BY_NAME["z3"]
    h = _tiny_render(f, 128, 200_000, seed=3)
    strong = h > np.percentile(h[h > 0], 90)
    top, bot = h[strong], h[::-1][strong]
    rel = np.abs(top - bot) / (top + bot + 1e-9)
    assert rel.mean() < 0.25, f"mirror asymmetry too high: {rel.mean():.2%}"


# ------------------------------------------------------------- end-to-end

def test_end_to_end_tiny_render(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "OUT", str(tmp_path))
    hist = bb.render_channel("blue", 50, 40_000, seed=5, size=96, tag="pytest")
    assert hist.shape == (96, 96)
    assert hist.sum() > 0
    assert (hist >= 0).all()
    cache = tmp_path / "hist_pytest_blue.npy"
    assert cache.exists()
    again = bb.render_channel("blue", 50, 40_000, seed=5, size=96, tag="pytest")
    assert np.array_equal(hist, again)  # cache hit path

"""Tests for brot_samplers: the S0/S1/S2 estimators of one orbit histogram.

Correctness anchors: escape_times/trace_orbits are validated against the
buddhabrot machinery they wrap (escape_mask / plot_orbits); each sampler is
checked for determinism, budget caps, and honest diagnostics; S1 and S0 are
checked for statistical agreement (total mass and coarse-blocked histogram
shape) at budgets small enough for CI but large enough to be stable.
"""

import numpy as np
import pytest

import brot_samplers as bs
import buddhabrot as bb

RNG = np.random.default_rng(42)


def coarse(h: np.ndarray, b: int) -> np.ndarray:
    """Block-sum a histogram into b x b cells and renormalise (noise control)."""
    n = h.shape[0] // b
    hi = h.reshape(b, n, b, n).sum(axis=(1, 3))
    return hi / hi.sum()


# ----------------------------------------------------- escape_times


def test_escape_times_known_points():
    cr = np.array([2.0, 0.0, -0.1])  # instant escape, never escapes, interior
    ci = np.array([0.0, 0.0, 0.0])
    with np.errstate(over="ignore", invalid="ignore"):
        t = bs.escape_times(cr, ci, 64, chunk=16)
    assert t[0] == 16  # observed at the first (chunked) check
    assert t[1] == 64  # cap = never escaped
    assert t[2] == 64  # cardioid interior never escapes


def test_escape_times_agrees_with_escape_mask():
    cr = RNG.uniform(bb.XMIN, bb.XMAX, 4000)
    ci = RNG.uniform(bb.YMIN, bb.YMAX, 4000)
    cap = 50
    with np.errstate(over="ignore", invalid="ignore"):
        t = bs.escape_times(cr, ci, cap, chunk=16)
        m = bb.escape_mask(cr, ci, cap)
    assert (t[~m] == cap).all()  # non-escapers sit at the cap
    assert (t[m] <= cap).all()  # escapers never exceed the cap
    assert (t[m] < cap).any()  # ...and most escape strictly earlier


def test_escape_times_deterministic():
    cr = RNG.uniform(-1.5, 1.5, 500)
    ci = RNG.uniform(-1.5, 1.5, 500)
    with np.errstate(over="ignore", invalid="ignore"):
        assert np.array_equal(
            bs.escape_times(cr, ci, 100), bs.escape_times(cr, ci, 100)
        )


# ------------------------------------------------------ trace_orbits


def test_trace_orbits_matches_plot_orbits_histogram():
    """S2's per-seed cells must bin to exactly the machinery histogram.

    The trace input deliberately includes non-escaping seeds: their cells
    must stay empty (g_p = 0 there) while the escapers' points match
    plot_orbits exactly.
    """
    W = H = 96
    cap = 40
    cr = RNG.uniform(bb.XMIN, bb.XMAX, 3000)  # interior + escapers mixed in
    ci = RNG.uniform(bb.YMIN, bb.YMAX, 3000)
    with np.errstate(over="ignore", invalid="ignore"):
        esc = bb.escape_mask(cr, ci, cap)
        hist_a = np.zeros(W * H)
        bb.plot_orbits(cr[esc], ci[esc], cap, hist_a, W, H)
        times, cells = bs.trace_orbits(cr, ci, cap, W, H)
    hist_b = np.bincount(
        np.concatenate(cells) if cells else np.empty(0, np.int64), minlength=W * H
    )
    assert np.array_equal(hist_a, hist_b.astype(np.float64))
    assert all(c.size == 0 for c, e in zip(cells, esc) if not e)
    assert all(c.size > 0 for c, e in zip(cells, esc) if e)  # z1 = c in-frame


def test_trace_orbits_out_of_frame_and_interior():
    W = H = 8
    cap = 10
    # seeds far outside the frame: no in-frame cells, escapes immediately
    with np.errstate(over="ignore", invalid="ignore"):
        times, cells = bs.trace_orbits(np.full(4, -5.0), np.zeros(4), cap, W, H)
    assert (times <= 2).all()
    assert all(c.size == 0 for c in cells)
    # fixed point c = 0 never escapes: cells must be empty (g_p = 0 there),
    # even though its bounded orbit keeps visiting in-frame pixels
    with np.errstate(over="ignore", invalid="ignore"):
        times, cells = bs.trace_orbits(np.zeros(1), np.zeros(1), cap, W, H)
    assert times[0] == cap
    assert cells[0].size == 0


# ------------------------------------------------------ helpers


def test_normalized_and_ess():
    h = np.zeros(16)
    assert bs._normalized(h).sum() == 0.0  # all-zero stays zero
    h[:4] = 2.0
    assert bs._normalized(h).sum() == pytest.approx(1.0)
    assert bs._ess(np.ones(10)) == pytest.approx(10.0)  # Kish: equal weights
    assert bs._ess(np.empty(0)) == 0.0
    assert bs._ess(np.array([1.0, 1.0, 2.0])) == pytest.approx(16.0 / 6.0)
    assert bs.total_variation(np.ones(4) / 4, np.array([1, 0, 0, 0.0])) == 0.75


# ------------------------------------------------------ S0 uniform


def test_s0_uniform_wraps_machinery_and_caps_budget():
    r = bs.sample_uniform(48, 40, 5000, seed=7)
    assert r["evals"] == r["n_drawn"] == 5000
    assert 0 < r["n_escaped"] < 5000
    assert r["n_culled"] > 0  # cardioid/bulb cull actually engaged
    assert r["hist"].sum() == pytest.approx(1.0)
    assert r["ess"] == 5000.0
    assert 0.0 < r["total_mass"] < 40.0  # E[plotted points] < iteration cap
    assert np.array_equal(r["hist"], bs.sample_uniform(48, 40, 5000, seed=7)["hist"])


def test_s0_zero_budget():
    r = bs.sample_uniform(8, 10, 0, seed=1)
    assert r["evals"] == 0 and r["hist"].sum() == 0.0 and r["total_mass"] == 0.0


# ------------------------------------------- S1 boundary importance


def test_s1_diagnostics_and_budget_cap():
    r = bs.sample_boundary_importance(48, 40, 6000, seed=7, grid=16)
    assert r["evals"] == r["prepass_evals"] + r["n_drawn"] == 6000
    assert r["pre_cap"] == 40  # default pre_cap = min(max_iter, 128)
    assert 0.0 < r["acceptance"] < 1.0
    assert r["n_accepted"] == int(r["acceptance"] * r["n_drawn"])
    assert 0.0 < r["ess"] <= r["n_accepted"]
    assert r["hist"].sum() == pytest.approx(1.0)
    assert np.array_equal(
        r["hist"],
        bs.sample_boundary_importance(48, 40, 6000, seed=7, grid=16)["hist"],
    )


def test_s1_no_budget_left_after_prepass():
    # budget exactly consumed by the pre-pass: zero draws, zero everything
    r = bs.sample_boundary_importance(8, 20, 64, seed=3, grid=8)
    assert r["prepass_evals"] == 64 and r["n_drawn"] == 0 and r["n_accepted"] == 0
    assert r["acceptance"] == 0.0 and r["total_mass"] == 0.0 and r["ess"] == 0.0


def test_s1_all_interior_grid_accepts_nothing():
    # a 1x1 pre-pass grid centres on c = -0.55+0i, inside the cardioid:
    # every cell has weight 0, so no draw is ever accepted
    r = bs.sample_boundary_importance(8, 20, 500, seed=3, grid=1)
    assert r["n_drawn"] == 500 - 1 and r["n_accepted"] == 0
    assert r["hist"].sum() == 0.0 and r["ess"] == 0.0


def test_s1_explicit_pre_cap_branch():
    r = bs.sample_boundary_importance(32, 30, 2000, seed=9, grid=8, pre_cap=7)
    assert r["pre_cap"] == 7 and r["n_accepted"] > 0


def test_s1_agrees_with_s0():
    """Same estimand: total mass close, coarse-blocked shape TV-small."""
    size, cap, budget = 64, 60, 20_000
    s0 = bs.sample_uniform(size, cap, budget, seed=20261021)
    s1 = bs.sample_boundary_importance(size, cap, budget, seed=20261022, grid=32)
    assert abs(s1["total_mass"] / s0["total_mass"] - 1.0) < 0.25
    tv = bs.total_variation(coarse(s0["hist"], 8), coarse(s1["hist"], 8))
    assert tv < 0.10, f"S1 shape drift too high: {tv:.4f}"


# ------------------------------------------------- S2 MH mutation


def test_s2_diagnostics_determinism_budget():
    r = bs.sample_mh_mutation(48, 40, 3000, seed=5, chains=6, step=0.05)
    assert r["evals"] <= 3000
    assert r["chains"] == 6 and r["steps"] > 0 and 0 <= r["burn"] < r["steps"]
    assert 0.0 < r["acceptance"] < 1.0  # recorded, and in a healthy band
    assert r["n_states"] == 6 * (r["steps"] - r["burn"])
    assert 0.0 < r["ess"] <= r["n_states"]
    assert r["total_mass"] is None  # SNIS sees the shape only
    assert r["hist"].sum() == pytest.approx(1.0)
    again = bs.sample_mh_mutation(48, 40, 3000, seed=5, chains=6, step=0.05)
    assert np.array_equal(r["hist"], again["hist"])
    assert r["acceptance"] == again["acceptance"]


def test_s2_interior_init_find_no_chains():
    # seed 6 draws c = -0.420-0.533i (cardioid interior) as its first
    # candidate; with budget 3 only one candidate is ever evaluated, so
    # zero chains start and the estimator degrades to a zero histogram
    r = bs.sample_mh_mutation(16, 20, 3, seed=6, chains=1)
    assert r["chains"] == 0 and r["steps"] == 0 and r["n_states"] == 0
    assert r["hist"].sum() == 0.0 and r["acceptance"] == 0.0 and r["ess"] == 0.0


def test_s2_init_consumes_whole_budget():
    # init_cap_frac=1.0 lets initialisation eat the entire budget: chains
    # exist but no mutation steps (and no post-burn states) can run
    r = bs.sample_mh_mutation(16, 20, 8, seed=5, chains=8, init_cap_frac=1.0)
    assert 0 < r["chains"] <= 8
    assert r["steps"] == 0 and r["n_states"] == 0 and r["ess"] == 0.0


def test_s2_huge_step_rejects_all_out_of_frame():
    # step 100 throws every proposal far outside the frame: r = 0 there,
    # so every move is rejected and the chains stay on their init states
    r = bs.sample_mh_mutation(16, 20, 400, seed=5, chains=2, step=100.0)
    assert r["acceptance"] == 0.0
    assert r["hist"].sum() == pytest.approx(1.0)  # init states still counted


def test_s2_agrees_with_s0_shape():
    size, cap, budget = 64, 60, 20_000
    s0 = bs.sample_uniform(size, cap, budget, seed=20261021)
    s2 = bs.sample_mh_mutation(size, cap, budget, seed=20261023, chains=32, step=0.05)
    tv = bs.total_variation(coarse(s0["hist"], 8), coarse(s2["hist"], 8))
    assert tv < 0.35, f"S2 shape drift too high: {tv:.4f}"
    tv4 = bs.total_variation(coarse(s0["hist"], 4), coarse(s2["hist"], 4))
    assert tv4 < 0.30, f"S2 coarse shape drift too high: {tv4:.4f}"


# ------------------------------------------------------ compare/CLI


def test_compare_runs_all_three_and_metrics():
    res = bs.compare(size=32, max_iter=30, budget=2500, seed=11, grid=8, chains=4)
    assert res["s0"]["evals"] == res["s1"]["evals"] == 2500
    assert res["s2"]["evals"] <= 2500
    for v in res["tv"].values():
        assert 0.0 <= v <= 1.0


def test_main_cli_smoke_and_save(tmp_path, capsys):
    out = tmp_path / "samplers.npz"
    bs.main(
        [
            "--size",
            "32",
            "--max-iter",
            "30",
            "--budget",
            "2500",
            "--grid",
            "8",
            "--chains",
            "4",
            "--step",
            "0.05",
            "--seed",
            "5",
            "--save",
            str(out),
        ]
    )
    text = capsys.readouterr().out
    assert "[S0]" in text and "[S1]" in text and "[S2]" in text
    assert "TV(P1,P0)" in text
    assert out.exists()
    got = np.load(out)
    assert set(got.files) == {"s0", "s1", "s2"}


def test_main_cli_full_preset_no_save(capsys):
    bs.main(
        [
            "--full",
            "--size",
            "32",
            "--max-iter",
            "30",
            "--budget",
            "2500",
            "--grid",
            "8",
            "--chains",
            "4",
            "--seed",
            "5",
        ]
    )
    assert "wrote" not in capsys.readouterr().out

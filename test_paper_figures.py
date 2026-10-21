"""Paper figure pipeline tests: every receipts schema scripts/paper_figures.py
consumes is pinned here against synthetic fixtures, plus figure builders,
deterministic output writing, and the one-command CLI regeneration."""

import json

import matplotlib.pyplot as plt
import numpy as np
import pytest

from scripts import paper_figures as pf


# ------------------------------------------------------------ json fixtures


def cell_json(map_name="mandel", cap=80, s1_degenerate=True) -> dict:
    rungs = lambda s, base: [  # noqa: E731
        {
            "sampler": s,
            "budget": b,
            "mean_rel_err": base * (62_500 / b) ** 0.5,
            "degenerate": False,
        }
        for b in (62_500, 250_000, 1_000_000, 4_000_000)
    ]
    runs = [
        {"sampler": "S0", "by_budget": rungs("S0", 0.5)},
        {
            "sampler": "S1",
            "by_budget": [
                {
                    "sampler": "S1",
                    "budget": 62_500,
                    "mean_rel_err": 1.0,
                    "degenerate": s1_degenerate,
                }
            ]
            + rungs("S1", 0.5)[1:],
        },
        {"sampler": "S2", "by_budget": rungs("S2", 1.5)},
    ]
    slopes = {"S0": -0.48, "S1": -0.50, "S2": -0.20}
    return {
        "map": map_name,
        "cap": cap,
        "grid": 64,
        "reference": {"budget": 40_000_000},
        "roi": {"roi_pixels": 10},
        "runs": runs,
        "convergence_loglog_slopes": {s: {"slope": v} for s, v in slopes.items()},
        "bias_check_top_rung": {"mean_rel_ratio_S2_over_S0": 4.7},
    }


def nanbug_json() -> dict:
    v = lambda tag, n: {  # noqa: E731
        "predicate": tag,
        "n_samples": 1000,
        "n_classified": n,
        "escape_fraction_of_draws": n / 1000,
    }
    return {
        "guarded": v("guarded", 870),
        "unguarded": v("unguarded", 27),
        "comparison": {
            "dropped_escaper_fraction": 0.969,
            "histogram_mass_ratio_unguarded_over_guarded": 0.2,
        },
    }


def gallery_json() -> dict:
    def m(name, family, real, imag, power, sym, equiv, direction):
        return {
            "name": name,
            "family": family,
            "grammar_ops": {"real": real, "imag": imag, "power": power},
            "formula": f"{name} formula",
            "mirror_symmetry": sym,
            "equivariant_prediction": equiv,
            "predicate": {"name": "g_test", "direction": direction},
            "caps": [1, 2, 3],
        }

    maps = (
        [
            m(
                f"pw{i}",
                "power",
                None,
                "plain",
                i + 2,
                0.99 - i * 0.02,
                True,
                "radial something",
            )
            for i in range(4)
        ]
        + [
            m(
                f"fd{i}",
                "fold",
                "abs" if i % 2 else None,
                "plain",
                2,
                0.95 - i * 0.1,
                i % 2 == 0,
                "radial something",
            )
            for i in range(4)
        ]
        + [
            m(
                f"mu{i}",
                "mutation",
                "cos",
                "plain",
                2,
                0.1 + i * 0.05,
                False,
                "vertical something",
            )
            for i in range(2)
        ]
    )
    return {"size": 8, "samples_per_channel": 100, "maps": maps}


def grammar_json() -> dict:
    return {
        "grammar": {
            "families": {
                "power": {
                    "formula": "z -> z^n + c",
                    "powers": [2, 3],
                    "real_ops": None,
                    "imag_ops": None,
                },
                "fold": {
                    "formula": "fold",
                    "powers": [2],
                    "real_ops": ["abs"],
                    "imag_ops": ["plain", "neg"],
                },
                "mutation": {
                    "formula": "mut",
                    "real_ops": ["cos", "tan"],
                    "imag_ops": ["plain"],
                },
            },
            "op_sources": {"real": {}, "imag": {}, "power_terms": {}},
        },
        "exit_predicates": [
            {
                "name": "g_z",
                "exit_direction": "radial",
                "maps_in_FRACS": ["a"],
                "source": "s",
            },
            {
                "name": "g_y",
                "exit_direction": "vertical",
                "maps_in_FRACS": ["b"],
                "source": "s",
            },
            {
                "name": "g_x",
                "exit_direction": "horizontal",
                "maps_in_FRACS": ["c"],
                "source": "s",
            },
        ],
    }


def write(path, obj) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


# ---------------------------------------------------------------- _expect


def test_expect_type_paths():
    d = {"f": 1.5, "i": 3, "b": True, "s": "x", "d": {}, "l": []}
    assert pf._expect(d, "f", float, "c") == 1.5
    assert pf._expect(d, "i", int, "c") == 3  # int field rejects bool below
    assert pf._expect(d, "b", bool, "c") is True
    assert pf._expect(d, "s", str, "c") == "x"
    assert pf._expect(d, "d", dict, "c") == {}
    assert pf._expect(d, "l", list, "c") == []
    assert pf._expect({"f": 2}, "f", float, "c") == 2  # int accepted as float


@pytest.mark.parametrize(
    "key,typ", [("f", int), ("i", bool), ("b", int), ("s", float), ("d", list)]
)
def test_expect_rejects_wrong_types(key, typ):
    d = {"f": 1.5, "i": 3, "b": True, "s": "x", "d": {}}
    with pytest.raises(pf.ParseError):
        pf._expect(d, key, typ, "ctx")


def test_expect_missing_key():
    with pytest.raises(pf.ParseError, match="missing key"):
        pf._expect({}, "map", str, "ctx")


# -------------------------------------------------------------- load_cell


def test_load_cell_happy(tmp_path):
    p = tmp_path / "cell_mandel_80.json"
    write(p, cell_json())
    c = pf.load_cell(p)
    assert (c.map_name, c.cap, c.ref_budget) == ("mandel", 80, 40_000_000)
    assert set(c.rungs) == {"S0", "S1", "S2"}
    assert c.rungs["S1"][0].degenerate
    assert c.slopes["S2"] == -0.20
    assert c.ratio_s2_s0_top == 4.7


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("runs"),
        lambda d: d["runs"].clear(),
        lambda d: d["runs"][0].pop("by_budget"),
        lambda d: d["runs"][0]["by_budget"][0].pop("mean_rel_err"),
        lambda d: d["runs"][0]["by_budget"][0].__setitem__("budget", "many"),
        lambda d: d["runs"][0]["by_budget"][0].__setitem__("degenerate", "no"),
        lambda d: d["convergence_loglog_slopes"].pop("S0"),
        lambda d: d["bias_check_top_rung"].pop("mean_rel_ratio_S2_over_S0"),
    ],
)
def test_load_cell_schema_violations(tmp_path, mutate):
    d = cell_json()
    mutate(d)
    p = tmp_path / "cell.json"
    write(p, d)
    with pytest.raises(pf.ParseError):
        pf.load_cell(p)


def test_load_cells_dir(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    write(results / "cell_mandel_80.json", cell_json("mandel", 80))
    write(results / "cell_z3_400.json", cell_json("z3", 400, s1_degenerate=False))
    cells = pf.load_cells(results)
    assert set(cells) == {("mandel", 80), ("z3", 400)}
    with pytest.raises(pf.ParseError):
        pf.load_cells(tmp_path / "empty")


# ------------------------------------------------------------- npz loaders


def test_load_hist_happy(tmp_path):
    p = tmp_path / "h.npz"
    np.savez(p, hist=np.ones((4, 5)))
    assert pf.load_hist(p).shape == (4, 5)


def test_load_hist_missing_key(tmp_path):
    p = tmp_path / "h.npz"
    np.savez(p, other=np.ones((4, 5)))
    with pytest.raises(pf.ParseError, match="hist"):
        pf.load_hist(p)
    # reference-npz layout: raw counts under 'raw'
    p2 = tmp_path / "ref.npz"
    np.savez(p2, raw=np.ones((4, 5)))
    assert pf.load_hist(p2, key="raw").shape == (4, 5)
    np.savez(tmp_path / "nokey.npz")
    with pytest.raises(pf.ParseError, match="raw"):
        pf.load_hist(tmp_path / "nokey.npz", key="raw")


def test_load_hist_wrong_ndim(tmp_path):
    p = tmp_path / "h.npz"
    np.savez(p, hist=np.ones(4))
    with pytest.raises(pf.ParseError, match="2-D"):
        pf.load_hist(p)


def test_load_rgb_happy_and_violations(tmp_path):
    p = tmp_path / "r.npz"
    np.savez(p, rgb=np.zeros((4, 5, 3), dtype=np.uint8))
    assert pf.load_rgb(p).shape == (4, 5, 3)
    np.savez(p, rgb=np.zeros((4, 5)))
    with pytest.raises(pf.ParseError, match="rgb"):
        pf.load_rgb(p)
    np.savez(p, nope=np.zeros((4, 5, 3)))
    with pytest.raises(pf.ParseError, match="rgb"):
        pf.load_rgb(p)


# ------------------------------------------------------------ other parsers


def test_load_nanbug(tmp_path):
    p = tmp_path / "nb.json"
    write(p, nanbug_json())
    nb = pf.load_nanbug(p)
    assert nb.variants["unguarded"].n_classified == 27
    assert nb.dropped_fraction == 0.969
    d = nanbug_json()
    d.pop("guarded")
    write(p, d)
    with pytest.raises(pf.ParseError):
        pf.load_nanbug(p)
    d = nanbug_json()
    d["comparison"]["dropped_escaper_fraction"] = "0.9"
    write(p, d)
    with pytest.raises(pf.ParseError):
        pf.load_nanbug(p)


def test_load_gallery(tmp_path):
    p = tmp_path / "g.json"
    write(p, gallery_json())
    g = pf.load_gallery(p)
    assert len(g.maps) == 10
    assert g.maps[0].real is None  # power family has no real op
    assert g.maps[-1].real == "cos"
    assert g.samples_per_channel == 100
    d = gallery_json()
    d["maps"].clear()
    write(p, d)
    with pytest.raises(pf.ParseError):
        pf.load_gallery(p)
    d = gallery_json()
    d["maps"][0].pop("mirror_symmetry")
    write(p, d)
    with pytest.raises(pf.ParseError):
        pf.load_gallery(p)


def test_load_grammar(tmp_path):
    p = tmp_path / "gf.json"
    write(p, grammar_json())
    g = pf.load_grammar(p)
    assert {x.direction for x in g.predicates} == {"radial", "vertical", "horizontal"}
    assert g.families["power"]["real_ops"] is None
    d = grammar_json()
    d["grammar"].pop("families")
    write(p, d)
    with pytest.raises(pf.ParseError):
        pf.load_grammar(p)


# ---------------------------------------------------------------- helpers


def test_tone_log():
    rng = np.random.default_rng(0)
    h = rng.pareto(2.0, (16, 16))
    lo, hi = pf.tone_log(h)
    assert 0.0 < lo < hi
    lo0, hi0 = pf.tone_log(np.zeros((4, 4)))
    assert (lo0, hi0) == (0.0, 1.0)  # no lit pixels -> neutral window
    lo_c, hi_c = pf.tone_log(np.full((4, 4), 3.0))
    assert hi_c == lo_c + 1.0  # constant image -> degenerate window widened


def test_rel_dev():
    ref = np.array([[2.0, 0.0]])
    h = np.array([[3.0, 5.0]])
    d = pf.rel_dev(h, ref)
    assert d[0, 0] == 0.5
    assert np.isnan(d[0, 1])


# --------------------------------------------------------------- figures


def make_cells():
    return {
        (m, c): pf.parse_cell(cell_json(m, c), "t") for m in pf.MAPS for c in pf.CAPS
    }


def test_fig1_convergence(tmp_path):
    fig = pf.fig1_convergence(make_cells())
    assert len(fig.axes) == 9
    pf.write_figure(fig, tmp_path, "t")
    assert (tmp_path / "t.png").exists() and (tmp_path / "t.pdf").exists()


def test_fig2_equal_budget():
    rng = np.random.default_rng(1)
    ref = rng.pareto(2.0, (32, 32))
    s0 = ref * 0.8 + rng.random((32, 32))
    s2 = ref * 0.5 + rng.random((32, 32)) * 2
    cell = pf.Cell(
        map_name="mandel",
        cap=1500,
        rungs={
            s: tuple(
                pf.Rung(s, b, 0.5 * (62_500 / b) ** 0.5, False)
                for b in (62_500, 250_000, 1_000_000, 4_000_000)
            )
            for s in ("S0", "S1", "S2")
        },
        slopes={"S0": -0.48, "S1": -0.5, "S2": -0.2},
        ratio_s2_s0_top=4.7,
        ref_budget=40_000_000,
    )
    fig = pf.fig2_equal_budget(s0, s2, ref, cell, 1_000_000)
    assert len(fig.axes) == 6
    plt.close(fig)


def test_fig3_nanbug():
    rng = np.random.default_rng(2)
    g = rng.pareto(2.0, (16, 16))
    fig = pf.fig3_nanbug(g * 0.1, g, pf.parse_nanbug(nanbug_json(), "t"))
    assert len(fig.axes) == 2
    assert any("96.9%" in t.get_text() for t in fig.texts)
    plt.close(fig)


def test_fig4_gallery(tmp_path):
    gl = pf.parse_gallery(gallery_json(), "t")
    imgs = {m.name: np.full((6, 6, 3), 128, dtype=np.uint8) for m in gl.maps}
    fig = pf.fig4_gallery(gl, imgs)
    thumbs = sum(1 for ax in fig.axes if ax.get_images())
    assert thumbs == 10  # 4 + 4 + 2 gallery cells (rest are filler/table)
    pf.write_figure(fig, tmp_path, "t4")


def test_fig5_grammar(tmp_path):
    g = pf.parse_grammar(grammar_json(), "t")
    gl = pf.parse_gallery(gallery_json(), "t")
    fig = pf.fig5_grammar(g, gl)
    assert len(fig.axes) == 2
    pf.write_figure(fig, tmp_path, "t5")


def test_write_figure_deterministic_png(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    pf.write_figure(fig, tmp_path, "d")
    b1 = (tmp_path / "d.png").read_bytes()
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    pf.write_figure(fig, tmp_path, "d2")
    b2 = (tmp_path / "d2.png").read_bytes()
    assert b1 == b2


def test_outline_text():
    txt = pf.outline_text(
        make_cells(),
        pf.parse_nanbug(nanbug_json(), "t"),
        pf.parse_gallery(gallery_json(), "t"),
    )
    assert "fig1_convergence" in txt and "fig5_grammar" in txt
    assert "96.9%" in txt
    assert "ρ" in txt


# -------------------------------------------------------------------- cli


def synthetic_paper_tree(root) -> None:
    results = root / "experiments" / "results"
    data = root / "experiments" / "data"
    results.mkdir(parents=True)
    data.mkdir(parents=True)
    for m in pf.MAPS:
        for c in pf.CAPS:
            write(results / f"cell_{m}_{c}.json", cell_json(m, c))
    write(results / "fig3_nanbug.json", nanbug_json())
    write(results / "fig4_gallery.json", gallery_json())
    write(results / "grammar_facts.json", grammar_json())
    rng = np.random.default_rng(3)
    h = rng.pareto(2.0, (16, 16))
    np.savez(data / "hist_mandel_1500_S0_1000000_study.npz", hist=h)
    np.savez(data / "hist_mandel_1500_S2_1000000_study.npz", hist=h * 0.5)
    np.savez(data / "ref_mandel_1500.npz", raw=h * 4)
    np.savez(data / "fig3_nanbug_unguarded.npz", hist=h * 0.1)
    np.savez(data / "fig3_nanbug_guarded.npz", hist=h)
    for m in pf.parse_gallery(gallery_json(), "t").maps:
        np.savez(
            data / f"fig4_gallery_{m.name}.npz",
            rgb=np.full((6, 6, 3), 90, dtype=np.uint8),
        )


def test_main_full_and_only(tmp_path, capsys):
    synthetic_paper_tree(tmp_path)
    rc = pf.main(["--paper-root", str(tmp_path)])
    assert rc == 0
    figs = tmp_path / "figures"
    for stem in (
        "fig1_convergence",
        "fig2_equal_budget",
        "fig3_nanbug",
        "fig4_gallery",
        "fig5_grammar",
    ):
        assert (figs / f"{stem}.png").exists()
        assert (figs / f"{stem}.pdf").exists()
    assert (figs / "OUTLINE.md").exists()
    out = capsys.readouterr().out
    assert out.count("->") == 10  # 5 figures x png+pdf
    rc = pf.main(["--paper-root", str(tmp_path), "--only", "F1,"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "fig1_convergence" in out and "fig5_grammar" not in out

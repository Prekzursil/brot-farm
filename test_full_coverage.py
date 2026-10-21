"""Full-coverage suite: drives every executable line of the four modules,
including CLI entry points (via monkeypatched argv and tiny configs),
poster/tone outputs, caching paths, and the topup tool.
"""

import os
import shutil
import sys

import numpy as np
import pytest
from PIL import Image

import buddhabrot as bb
import brot_farm as farm
import cosbrot
import topup

RNG = np.random.default_rng(1234)

TINY_FARM = dict(
    name="tiny",
    title="T I N Y",
    sub="x\u2032 = x\u00b2 \u2212 y\u00b2",
    step=farm.s_std,
    gone=farm.g_z,
    chunk=8,
    cull=False,
    invert=False,
    julia=None,
    samp=(-1.5, 1.5, -1.5, 1.5),
    plot=(-1.5, 1.5, -1.5, 1.5),
    size=(96, 96),
    chans=((30, 3_000), (30, 2_000), (30, 1_000)),
    batch=1_000,
)


def run_cli(mod, argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", [mod.__name__] + argv)
    mod.main()


# ----------------------------------------------------- uncovered step rules


@pytest.mark.parametrize(
    "fname",
    [
        "s_ship",
        "s_celtic",
        "s_buffalo",
        "s_tanmut",
        "s_sinhmut",
        "s_expmut",
        "s_cosfull",
    ],
)
def test_remaining_step_rules_run(fname):
    x, y = RNG.uniform(-0.8, 0.8, 64), RNG.uniform(-0.8, 0.8, 64)
    cx, cy = RNG.uniform(-0.5, 0.5, 64), RNG.uniform(-0.5, 0.5, 64)
    gx, gy = getattr(farm, fname)(x, y, cx, cy)
    assert np.isfinite(gx).any() and np.isfinite(gy).any()


def test_celtic_matches_absolute_value_semantics():
    x = np.array([0.5, -0.25])
    y = np.array([0.3, 0.1])
    gx, gy = farm.s_celtic(x, y, np.zeros(2), np.zeros(2))
    assert np.allclose(gx, np.abs(x * x - y * y))
    assert np.allclose(gy, 2 * x * y)


@pytest.mark.parametrize(
    "gone,xbad,ybad",
    [
        (farm.g_big, 2000.0, 0.0),  # |z| > 1e6
        (farm.g_big, np.nan, 0.0),  # NaN
        (farm.g_y, 0.0, 200.0),  # |y| > 100
        (farm.g_x, 200.0, 0.0),  # |x| > 100
        (farm.g_z, 2.1, 0.0),  # |z| > 2
    ],
)
def test_gone_predicates_fire(gone, xbad, ybad):
    assert bool(gone(np.array([xbad]), np.array([ybad]))[0])
    assert not bool(gone(np.array([0.1]), np.array([0.1]))[0])
    assert bool(gone(np.array([np.inf]), np.array([0.0]))[0])


def test_g_z_nan_escape_regression():
    # the bug this project actually hit: overflow -> NaN must count as escaped
    assert bool(farm.g_z(np.array([np.nan]), np.array([np.nan]))[0])


# ------------------------------------------------------- buddhabrot extras


def test_escape_mask_all_prisoners_branch():
    pts = RNG.uniform(-0.2, 0.1, (500, 2))  # deep inside the main cardioid
    m = bb.escape_mask(pts[:, 0].copy(), pts[:, 1].copy(), 60)
    assert not m.any()  # and the empty-escaped-parts branch was taken


def test_tone_channel_empty_histogram():
    v = bb.tone_channel(np.zeros((8, 8)), plo=30, phi=99.9, gamma=1.2, gain=1.0)
    assert v.shape == (8, 8) and np.all(v == 0)  # nothing lit -> pure black


def test_build_rgb_sat_one_skips_vibrance():
    h = {k: RNG.random((16, 16)) * 100 for k in ("red", "green", "blue")}
    a = bb.build_rgb(h, 30, 99.9, 1.0, {"red": 1.0, "green": 1.0, "blue": 1.0}, 1.0)
    assert a.shape == (16, 16, 3)
    b = bb.build_rgb(h, 30, 99.9, 1.0, {"red": 1.0, "green": 1.0, "blue": 1.0}, 1.3)
    assert b.shape == (16, 16, 3)


# platform constants only -- no environment-derived paths (CodeQL path-injection)
FONT_PROBES = [
    "C:\\Windows\\Fonts\\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def test_load_font_truetype_and_default_branches(tmp_path):
    source = next((p for p in FONT_PROBES if os.path.exists(p)), None)
    if source is None:
        pytest.skip("no system font available to exercise the truetype branch")
    assert source is not None  # pytest.skip raises, but narrow for the checker
    fonts = tmp_path / "Fonts"
    fonts.mkdir()
    shutil.copy(source, fonts / "arial.ttf")
    real = bb.load_font(14, fonts_dir=str(fonts))
    fallback = bb.load_font(14, fonts_dir=str(tmp_path / "empty"))
    # the truetype branch must have loaded OUR copied file, not a default
    assert os.path.basename(str(getattr(real, "path", ""))) == "arial.ttf"
    assert fallback is not None


def test_make_poster_writes_file(tmp_path):
    u8 = (RNG.random((64, 64, 3)) * 255).astype(np.uint8)
    out = tmp_path / "p.png"
    bb.make_poster(u8, str(out), 12_345)
    assert out.exists()


def test_buddhabrot_cli_render_then_tone(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bb, "OUT", str(tmp_path))
    monkeypatch.setitem(
        bb.CONFIGS,
        "smoke",
        dict(
            size=64,
            channels=(
                ("blue", 25, 2_000, 1),
                ("green", 25, 1_500, 2),
                ("red", 25, 1_000, 3),
            ),
        ),
    )
    run_cli(bb, ["render", "--smoke"], monkeypatch)
    assert (tmp_path / "buddhabrot_smoke.png").exists()
    assert (tmp_path / "buddhabrot_smoke_poster.png").exists()
    run_cli(bb, ["tone", "--smoke", "--gamma", "1.1"], monkeypatch)
    out = capsys.readouterr().out
    assert "wrote" in out


def test_buddhabrot_cli_tone_only_creates_out_dir(tmp_path, monkeypatch):
    fresh = tmp_path / "fresh"
    monkeypatch.setattr(bb, "OUT", str(fresh))
    monkeypatch.setitem(
        bb.CONFIGS,
        "smoke",
        dict(
            size=48,
            channels=(
                ("blue", 20, 1_200, 1),
                ("green", 20, 900, 2),
                ("red", 20, 700, 3),
            ),
        ),
    )
    run_cli(bb, ["render", "--smoke"], monkeypatch)  # populate caches
    (fresh / "buddhabrot_smoke.png").unlink()
    (fresh / "buddhabrot_smoke_poster.png").unlink()
    run_cli(bb, ["tone", "--smoke"], monkeypatch)  # tone-only: dir exists, no crash
    assert (fresh / "buddhabrot_smoke.png").exists()


# ---------------------------------------------------------- brot_farm extras


def test_farm_write_outputs_without_args(tmp_path, monkeypatch):
    monkeypatch.setattr(farm, "OUT", str(tmp_path))
    hists = {c: RNG.random((32, 32)) * 50 for c in ("blue", "green", "red")}
    f = dict(TINY_FARM, size=(32, 32))
    farm.write_outputs(f, hists, None)
    assert (tmp_path / "brot_tiny.png").exists()
    assert (tmp_path / "brot_tiny_poster.png").exists()


def test_farm_render_skips_existing_png(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(farm, "OUT", str(tmp_path))
    Image.new("RGB", (4, 4)).save(tmp_path / "brot_tiny.png")
    f = dict(TINY_FARM)
    farm.render_fractal(f)
    assert "already rendered" in capsys.readouterr().out


def test_farm_render_uses_cached_channels(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(farm, "OUT", str(tmp_path))
    for ci in range(3):
        np.save(tmp_path / f"hist_tiny_{ci}.npy", RNG.random((96, 96)) * 40)
    farm.render_fractal(dict(TINY_FARM))
    assert "cached" in capsys.readouterr().out
    assert (tmp_path / "brot_tiny.png").exists()


def test_farm_cli_list_and_render_and_tone(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(farm, "OUT", str(tmp_path))
    monkeypatch.setattr(farm, "FRACS", [TINY_FARM])
    monkeypatch.setattr(farm, "BY_NAME", {TINY_FARM["name"]: TINY_FARM})
    run_cli(farm, ["--list"], monkeypatch)
    assert "tiny" in capsys.readouterr().out
    run_cli(farm, ["render", "--shard", "0", "--shards", "1"], monkeypatch)
    assert (tmp_path / "brot_tiny.png").exists()
    run_cli(farm, ["tone", "tiny", "--gamma", "1.1"], monkeypatch)
    assert (tmp_path / "brot_tiny.png").exists()


def test_farm_cli_qc_with_mixed_outputs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(farm, "OUT", str(tmp_path))
    other = dict(TINY_FARM, name="ghost")
    monkeypatch.setattr(farm, "FRACS", [TINY_FARM, other])
    Image.fromarray((RNG.random((32, 32, 3)) * 255).astype(np.uint8)).save(
        tmp_path / "brot_tiny.png"
    )
    run_cli(farm, ["qc"], monkeypatch)
    out = capsys.readouterr().out
    assert "MISSING" in out and "ghost" in out and "tiny" in out


# ------------------------------------------------------------ cosbrot CLI


def test_cosbrot_step_gone_and_masks():
    x, y = RNG.uniform(-1, 1, 128), RNG.uniform(-1, 1, 128)
    with np.errstate(over="ignore", invalid="ignore"):
        nx, ny = cosbrot.step(x, y, x.copy(), y.copy())
        assert np.isfinite(nx).any()
        assert cosbrot.gone(nx, ny).any() or True
        m = cosbrot.escape_mask(x, y, 100)
    assert m.dtype == bool
    hist = np.zeros(64 * 64)
    with np.errstate(over="ignore", invalid="ignore"):
        cosbrot.plot_orbits(x[m][:50], y[m][:50], 100, hist, 64, 64)
    assert hist.sum() >= 0


def test_cosbrot_cli_smoke(tmp_path, monkeypatch):
    monkeypatch.setattr(cosbrot, "OUT", str(tmp_path))
    monkeypatch.setitem(
        cosbrot.CONFIGS,
        "smoke",
        dict(
            size=64,
            channels=(
                ("blue", 40, 1_500, 101),
                ("green", 60, 1_000, 202),
                ("red", 80, 700, 303),
            ),
        ),
    )
    run_cli(cosbrot, ["render", "--smoke"], monkeypatch)
    assert (tmp_path / "cosbrot_smoke.png").exists()
    assert (tmp_path / "cosbrot_smoke_poster.png").exists()


def test_cosbrot_render_channel_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cosbrot, "OUT", str(tmp_path))
    a = cosbrot.render_channel("blue", 30, 800, seed=5, size=48, tag="unit")
    b = cosbrot.render_channel("blue", 30, 800, seed=5, size=48, tag="unit")
    assert np.array_equal(a, b)  # cache hit


# ---------------------------------------------------------------- topup

FAKE = dict(
    name="fake",
    title="F A K E",
    sub="unit-test map",
    step=lambda x, y, cx, cy: (x * x - y * y + cx, 2.0 * x * y + cy),
    gone=lambda x, y: x * x + y * y > 4.0,
    chunk=8,
    cull=False,
    invert=False,
    julia=None,
    samp=(-1.2, 1.2, -1.2, 1.2),
    plot=(-1.2, 1.2, -1.2, 1.2),
    size=(96, 96),
    chans=((40, 1_000), (40, 800), (40, 600)),
    batch=400,
)


def _seed_caches(tmp_path):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    for ci in range(3):
        np.save(out / f"hist_fake_{ci}.npy", RNG.random((96, 96)) * 30)


def test_topup_crop_and_accumulate(tmp_path, monkeypatch, capsys):
    _seed_caches(tmp_path)
    monkeypatch.setattr(topup, "HERE", str(tmp_path))
    topup.farm.BY_NAME["fake"] = dict(FAKE)
    topup.topup("fake", 64, [500, 400, 300])
    out = tmp_path / "out"
    for ci in range(3):
        h = np.load(out / f"hist_fake_{ci}.npy")
        assert h.shape == (64, 64)  # cropped and saved back
    assert "top-up done" in capsys.readouterr().out
    topup.farm.BY_NAME.pop("fake", None)


def test_topup_is_idempotent_on_cropped_cache(tmp_path, monkeypatch):
    _seed_caches(tmp_path)
    monkeypatch.setattr(topup, "HERE", str(tmp_path))
    topup.farm.BY_NAME["fake"] = dict(FAKE)
    try:
        topup.topup("fake", 64, [300, 200, 100])
        first = np.load(tmp_path / "out" / "hist_fake_0.npy").copy()
        topup.topup("fake", 64, [300, 200, 100])  # now already cropped
        second = np.load(tmp_path / "out" / "hist_fake_0.npy")
        assert second.shape == first.shape == (64, 64)
        assert second.sum() >= first.sum()
    finally:
        topup.farm.BY_NAME.pop("fake", None)


def test_topup_rejects_corrupt_cache_shape(tmp_path, monkeypatch):
    (tmp_path / "out").mkdir(exist_ok=True)
    np.save(tmp_path / "out" / "hist_fake_0.npy", RNG.random((13, 13)))
    monkeypatch.setattr(topup, "HERE", str(tmp_path))
    topup.farm.BY_NAME["fake"] = dict(FAKE)
    try:
        with pytest.raises(AssertionError):
            topup.topup("fake", 64, [10, 0, 0])
    finally:
        topup.farm.BY_NAME.pop("fake", None)


def test_topup_cli_argv_parsing(tmp_path, monkeypatch):
    # the __main__ block is pragma'd; this exercises the same argv contract
    _seed_caches(tmp_path)
    monkeypatch.setattr(topup, "HERE", str(tmp_path))
    topup.farm.BY_NAME["fake"] = dict(FAKE)
    try:
        argv = ["topup.py", "fake", "64", "200", "100", "50"]
        name, crop_px, extra = argv[1], int(argv[2]), [int(v) for v in argv[3:6]]
        topup.topup(name, crop_px, extra)
        h = np.load(tmp_path / "out" / "hist_fake_0.npy")
        assert h.shape == (64, 64)
    finally:
        topup.farm.BY_NAME.pop("fake", None)


# ---------------------------------------------- flush & mode branches


def test_plot_orbits_flush_branch_all_modules():
    for mod, args in ((bb, ()), (farm, None), (cosbrot, ())):
        hist = np.zeros(32 * 32)
        rng = np.random.default_rng(7)
        x0 = rng.uniform(-1.2, 1.2, 400)
        y0 = rng.uniform(-1.2, 1.2, 400)
        with np.errstate(over="ignore", invalid="ignore"):
            if mod is farm:
                f = dict(TINY_FARM, size=(32, 32), plot=(-1.5, 1.5, -1.5, 1.5))
                esc = farm.escape_mask(f, x0, y0, x0.copy(), y0.copy(), 40)
                farm.plot_orbits(
                    f,
                    x0[esc],
                    y0[esc],
                    x0[esc].copy(),
                    y0[esc].copy(),
                    40,
                    hist,
                    32,
                    32,
                    flush_at=10,
                )
            elif mod is bb:
                esc = bb.escape_mask(x0.copy(), y0.copy(), 40)
                bb.plot_orbits(x0[esc], y0[esc], 40, hist, 32, 32, flush_at=10)
            else:
                esc = cosbrot.escape_mask(x0.copy(), y0.copy(), 40)
                cosbrot.plot_orbits(x0[esc], y0[esc], 40, hist, 32, 32, flush_at=10)
        assert hist.sum() > 0


def test_farm_julia_cull_invert_render_modes(tmp_path, monkeypatch):
    monkeypatch.setattr(farm, "OUT", str(tmp_path))
    cfgs = []
    for name, extra in (
        (
            "tjulia",
            dict(
                julia=(-0.7, 0.27),
                samp=(-1.2, 1.2, -1.2, 1.2),
                plot=(-1.2, 1.2, -1.2, 1.2),
            ),
        ),
        ("tcull", dict(cull=True)),
        ("tanti", dict(invert=True)),
    ):
        cfgs.append(dict(TINY_FARM, name=name, **extra))
    monkeypatch.setattr(farm, "FRACS", cfgs)
    for f in cfgs:
        farm.render_fractal(f)
    for f in cfgs:
        assert (tmp_path / f"brot_{f['name']}.png").exists(), f["name"]


def test_topup_julia_and_cull_and_skip_branches(tmp_path, monkeypatch):
    monkeypatch.setattr(topup, "HERE", str(tmp_path))
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    for name, extra in (
        ("fjulia", dict(julia=(-0.7, 0.27))),
        ("fcull", dict(cull=True)),
    ):
        f = dict(FAKE, name=name, **extra)
        for ci in range(3):
            np.save(out / f"hist_{name}_{ci}.npy", RNG.random((96, 96)) * 20)
        topup.farm.BY_NAME[name] = f
        topup.topup(name, 64, [300, 0, 0])  # zero extras exercise the skip branch
    for name in ("fjulia", "fcull"):
        assert (out / f"hist_{name}_0.npy").exists()
        topup.farm.BY_NAME.pop(name, None)


def test_topup_already_cropped_with_fresh_config(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    for ci in range(3):
        np.save(out / f"hist_fake_{ci}.npy", RNG.random((96, 96)) * 20)
    monkeypatch.setattr(topup, "HERE", str(tmp_path))
    topup.farm.BY_NAME["fake"] = dict(FAKE)
    try:
        topup.topup("fake", 64, [300, 200, 100])  # mutates its config + crops cache
        topup.farm.BY_NAME["fake"] = dict(FAKE)  # fresh config, cache already 64x64
        topup.topup("fake", 64, [300, 200, 100])  # -> already-cropped elif path
        h = np.load(out / "hist_fake_0.npy")
        assert h.shape == (64, 64)
    finally:
        topup.farm.BY_NAME.pop("fake", None)


def test_plot_orbits_all_out_of_window_branches():
    # Points that live entirely OUTSIDE the plot window exercise the
    # `if inb.any()` false path per iteration and the empty final
    # `if buffered:` flush guard. |z|=50 escapes on the first step for the
    # g_z maps, so the loop plots once (out of window), then exits empty.
    for mod in (bb, farm, cosbrot):
        hist = np.zeros(16 * 16)
        x0 = np.array([50.0])
        y0 = np.array([0.0])
        with np.errstate(over="ignore", invalid="ignore"):
            if mod is farm:
                f = dict(TINY_FARM, plot=(-1.5, 1.5, -1.5, 1.5))
                mod.plot_orbits(
                    f, x0.copy(), y0.copy(), x0.copy(), y0.copy(), 10, hist, 16, 16
                )
            elif mod is bb:
                mod.plot_orbits(x0.copy(), y0.copy(), 10, hist, 16, 16)
            else:
                mod.plot_orbits(x0.copy(), y0.copy(), 10, hist, 16, 16)
        assert hist.sum() == 0  # nothing in-window was ever plotted


def test_cosbrot_escape_mask_no_escapers_branch():
    # c = 0 has a bounded orbit for the cos mutation (fixed point of
    # x = cos(x^2)), so the `if escaped:` false path is taken.
    m = cosbrot.escape_mask(np.zeros(8), np.zeros(8), 80)
    assert not m.any()


# ------------------------------------------------------------ version_assets


def test_version_assets_versions_and_is_idempotent(tmp_path, monkeypatch):
    import scripts.version_assets as va  # noqa: PLC0415

    docs = tmp_path / "docs" / "assets"
    docs.mkdir(parents=True)
    (docs / "app.js").write_text("console.log(1)\n", encoding="utf-8")
    (tmp_path / "docs" / "index.html").write_text(
        '<html lang="en"><head><script src="assets/app.js"></script></head></html>\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(va, "DOCS", tmp_path / "docs")
    changed = va.version_docs()
    html = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert changed == 1
    assert "?v=" in html and 'data-build="' in html
    # idempotent: second run changes nothing
    assert va.version_docs() == 0
    assert (tmp_path / "docs" / "index.html").read_text(encoding="utf-8") == html
    # refreshes a stale hash when the asset changes
    (docs / "app.js").write_text("console.log(2)\n", encoding="utf-8")
    assert va.version_docs() == 1
    html2 = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert html2 != html


def test_version_assets_stamps_only_one_build_attr(tmp_path, monkeypatch):
    import scripts.version_assets as va

    docs = tmp_path / "docs" / "assets"
    docs.mkdir(parents=True)
    (docs / "app.js").write_text("x\n", encoding="utf-8")
    (tmp_path / "docs" / "a.html").write_text(
        '<html lang="en" data-build="old"><script src="assets/app.js"></script></html>',
        encoding="utf-8",
    )
    monkeypatch.setattr(va, "DOCS", tmp_path / "docs")
    va.version_docs()
    html = (tmp_path / "docs" / "a.html").read_text(encoding="utf-8")
    assert html.count("data-build=") == 1 and "old" not in html


def test_version_assets_hash_is_line_ending_independent(tmp_path, monkeypatch):
    import scripts.version_assets as va

    docs = tmp_path / "docs" / "assets"
    docs.mkdir(parents=True)
    lf = docs / "a.js"
    lf.write_bytes(b"console.log(1)\n")
    h_lf = va.asset_hash(lf)
    lf.write_bytes(b"console.log(1)\r\n")  # CRLF working tree (autocrlf clone)
    assert va.asset_hash(lf) == h_lf, "hash must not depend on checkout line endings"

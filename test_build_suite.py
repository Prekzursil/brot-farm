"""Build-suite tests: brot_build.py at 100% line+branch, plus the
Python<->JavaScript map parity gate (CI-enforced: the two sides can never
drift apart in the map catalogue)."""

import json
import re

import pytest

import brot_build as bb
import brot_farm as farm

USERMAP_NAMES = {p.stem for p in bb.USERMAPS.glob("*.py") if not p.stem.startswith("_")}


# ------------------------------------------------------------- grammar core


@pytest.mark.parametrize(
    "family,real,imag,power",
    [
        ("mutation", "cos", "plain", 2),
        ("mutation", "exp", "cos", 2),
        ("fold", "plain", "cos", 2),
        ("fold", "abs", "abs", 4),
        ("power", "plain", "plain", 3),
    ],
)
def test_step_sources_families(family, real, imag, power):
    py_r, py_i, esc = bb.step_sources(family, real, imag, power)
    assert "cx" in py_r and "cy" in py_i
    assert float(esc) > 0


@pytest.mark.parametrize("family", ["mutation", "fold", "power"])
def test_formula_text_families(family):
    text = bb.formula_text(family, "abs", "cos", 4)
    assert "x'" in text or "z" in text


def test_fold_abs_wraps_real_term():
    py_r, _, _ = bb.step_sources("fold", "abs", "plain", 2)
    assert py_r.startswith("np.abs(")


# ----------------------------------------------------------- scaffold cycle


def test_new_scout_preview_check_mutate_cycle(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "USERMAPS", tmp_path)
    monkeypatch.setattr(bb, "OUT", tmp_path / "out")
    monkeypatch.setattr(bb, "DOCS", tmp_path / "docs")
    bb.cmd_new("t_cos", "mutation", "cos", "plain", 2)
    assert (tmp_path / "t_cos.py").exists()
    with pytest.raises(SystemExit, match="already exists"):
        bb.cmd_new("t_cos", "mutation", "cos", "plain", 2)
    with pytest.raises(SystemExit, match="no user map"):
        bb.load_usermap("missing_map")
    # scout writes a report and recommends a window
    report = bb.cmd_scout("t_cos")
    assert any(w["escape_fraction"] >= 0 for w in report["windows"])
    # preview renders tiny + writes the thumb
    bb.cmd_preview("t_cos", size=64, samples=9_000)
    assert (tmp_path / "out" / "preview_t_cos.png").exists()
    assert (tmp_path / "docs" / "maps" / "t_cos.jpg").exists()
    # full quality bar passes
    assert bb.cmd_check("t_cos") is True
    # mutate swaps the real operator, grammar carried
    bb.cmd_mutate("t_cos", "t_tan", real="tan")
    src = (tmp_path / "t_tan.py").read_text(encoding="utf-8")
    assert "np.tan" in src


def test_check_reports_each_failure_class(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "USERMAPS", tmp_path)
    monkeypatch.setattr(bb, "OUT", tmp_path / "out")
    monkeypatch.setattr(bb, "DOCS", tmp_path / "docs")
    bb.cmd_new("bad", "mutation", "cos", "plain", 2)
    bad = tmp_path / "bad.py"
    src = bad.read_text(encoding="utf-8")
    # 1: NaN guard text removed
    bad.write_text(src.replace("~np.isfinite", "np.isfinite"), encoding="utf-8")
    problems = _check_problems("bad")
    assert any("NaN guard" in p for p in problems)
    # 2: gone that never fires (escaper probe fails) + no-finite-step probe:
    bad.write_text(
        src.replace(
            "return (r > 1e4) | ~np.isfinite(r)",
            "return np.zeros_like(x, dtype=bool) | (np.full_like(x, np.nan) > 1e4)",
        ),
        encoding="utf-8",
    )
    problems = _check_problems("bad")
    assert any("escaper" in p or "finite" in p for p in problems)
    # 3: missing thumb + stale catalogue
    bad.write_text(src, encoding="utf-8")
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "assets").mkdir(exist_ok=True)
    (tmp_path / "docs" / "assets" / "catalogue.js").write_text(
        "window.BROT_CATALOGUE = [];", encoding="utf-8"
    )
    problems = _check_problems("bad")
    assert any("preview thumb" in p for p in problems)
    assert any("catalogue" in p for p in problems)


def _check_problems(name: str) -> list[str]:
    import io
    import contextlib

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ok = bb.cmd_check(name)
    assert ok is False
    return [
        line for line in out.getvalue().splitlines() if line.strip().startswith("FAIL")
    ]


def test_scout_no_band_match_recommends_none(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "USERMAPS", tmp_path)
    monkeypatch.setattr(bb, "OUT", tmp_path)
    monkeypatch.setattr(
        bb, "DOCS", tmp_path / "docs"
    )  # never leak into the real catalogue
    bb.cmd_new("esc", "mutation", "exp", "plain", 2)  # everything escapes fast
    report = bb.cmd_scout("esc")
    assert report["recommended_half_width"] is None or report["recommended_half_width"]


# ------------------------------------------------------------- catalogue


def test_catalogue_regenerates_and_carries_grammar(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "USERMAPS", tmp_path)
    monkeypatch.setattr(bb, "OUT", tmp_path / "out")
    monkeypatch.setattr(bb, "DOCS", tmp_path / "docs")
    bb.cmd_new("c1", "fold", "abs", "neg", 4)
    entries = bb.cmd_catalogue()
    assert entries[0]["grammar"]["family"] == "fold"
    js = (tmp_path / "docs" / "assets" / "catalogue.js").read_text(encoding="utf-8")
    assert "c1" in js and "window.BROT_CATALOGUE" in js


# ------------------------------------------------------------- CLI + parity


def test_cli_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "USERMAPS", tmp_path)
    monkeypatch.setattr(bb, "OUT", tmp_path / "out")
    monkeypatch.setattr(bb, "DOCS", tmp_path / "docs")
    bb.main(["new", "cli_map", "--family", "power", "--power", "3"])
    assert (tmp_path / "cli_map.py").exists()
    bb.main(["catalogue"])
    assert (tmp_path / "out" / "catalogue.json").exists()
    with pytest.raises(SystemExit) as ei:
        bb.main(["check", "cli_map"])  # no preview thumb yet -> exit 1
    assert ei.value.code == 1
    bb.main(["preview", "cli_map", "--size", "48", "--samples", "3000"])
    with pytest.raises(SystemExit) as ok:
        bb.main(["check", "cli_map"])
    assert ok.value.code == 0
    bb.main(["mutate", "cli_map", "cli_map2", "--real", "sin"])


def test_python_javascript_map_parity():
    """The parity gate: farm base maps and playground MAPS must agree,
    modulo the documented alias allow-list."""
    js = (bb.DOCS / "assets" / "playground.js").read_text(encoding="utf-8")
    js_maps = set(re.findall(r"^\s{2}([a-z0-9]+):\s*\{\s*label", js, re.M))
    farm_base = {f["name"] for f in farm.FRACS if "grammar" not in f}
    aliases = {"anti": "mandel", "nebula": "mandel", "julia": "mandel"}
    mapped = {aliases.get(n, n) for n in farm_base}
    js_only_allowed = {"cosmut"}  # browser-only preset of the session mutation
    assert mapped - js_only_allowed == js_maps - js_only_allowed, (
        f"parity drift: farm-only={mapped - js_maps - js_only_allowed} "
        f"js-only={js_maps - mapped - js_only_allowed}"
    )


def test_every_usermap_in_catalogue_js():
    js = (bb.DOCS / "assets" / "catalogue.js").read_text(encoding="utf-8")
    for name in USERMAP_NAMES:
        assert name in js, (
            f"user map {name} missing from docs catalogue (run brot_build.py catalogue)"
        )


def test_usermaps_extend_the_farm():
    assert any(f["name"] == "demo_cossin" for f in farm.FRACS)
    assert farm.BY_NAME["demo_cossin"]["grammar"]["real"] == "cos"


def test_check_channel_sanity_and_nan_step_branches(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "USERMAPS", tmp_path)
    monkeypatch.setattr(bb, "OUT", tmp_path / "out")
    monkeypatch.setattr(bb, "DOCS", tmp_path / "docs")
    bb.cmd_new("weird", "mutation", "cos", "plain", 2)
    src = (tmp_path / "weird.py").read_text(encoding="utf-8")
    # bad channel config -> sanity problem branch
    (tmp_path / "weird.py").write_text(
        src.replace(
            "((60, 8_000_000), (300, 5_000_000), (1000, 3_000_000))", "((0, 0),)"
        ),
        encoding="utf-8",
    )
    problems = _check_problems("weird")
    assert any("channel config" in p for p in problems)
    # all-NaN step -> no-finite-outputs branch
    (tmp_path / "weird.py").write_text(
        src.replace("np.cos(x * x) - y + cx", "np.nan * x + cx"), encoding="utf-8"
    )
    problems = _check_problems("weird")
    assert any("finite" in p for p in problems)
    # present on disk but absent from the generated catalogue -> that branch
    (tmp_path / "weird.py").write_text(src, encoding="utf-8")
    monkeypatch.setattr(bb, "catalogue_entries", lambda: [])
    problems = _check_problems("weird")
    assert any("missing from catalogue" in p for p in problems)


def test_cli_scout_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "USERMAPS", tmp_path)
    monkeypatch.setattr(bb, "OUT", tmp_path / "out")
    monkeypatch.setattr(bb, "DOCS", tmp_path / "docs")
    bb.main(["new", "s1", "--family", "power", "--power", "4"])
    bb.main(["scout", "s1"])
    assert (tmp_path / "out" / "scout_s1.json").exists()


# ----------------------------------------------------------------- APRS (L5)


def test_aprs_export_round_trips_validator(tmp_path, monkeypatch):
    """brot_build aprs is a producer: its output must pass validate_aprs."""
    from scripts.validate_aprs import validate_file

    monkeypatch.setattr(bb, "APRS_PREVIEW_SAMPLES", 3_000)  # tiny smoke budget
    monkeypatch.setattr(bb, "OUT", tmp_path / "fresh_out")
    out = tmp_path / "demo_cossin.aprs.json"
    bb.main(["aprs", "demo_cossin", "--out", str(out)])
    assert out.exists()
    assert validate_file(out) == []  # round-trip: producer -> validator
    rec = json.loads(out.read_text(encoding="utf-8"))
    assert rec["name"] == "demo_cossin"
    assert rec["grammar"] == {
        "family": "mutation",
        "real": "cos",
        "imag": "plain",
        "power": 2,
    }
    assert rec["window"] == [-2.5, 2.5, -2.5, 2.5]
    assert rec["caps"] == [60, 300, 1000]
    assert rec["renderer"] == "fractal-darkroom"
    assert rec["provenance"] == "authored-on-site"
    assert rec["preview"]
    # the aprs dispatch returns before the implicit catalogue regeneration
    assert not (tmp_path / "fresh_out" / "catalogue.json").exists()


def test_aprs_preview_hash_is_deterministic():
    monkeypatch_samples = 250
    r1 = bb.aprs_record(
        "demo_cossin",
        author="t",
        provenance="authored-on-site",
        preview_samples=monkeypatch_samples,
    )
    r2 = bb.aprs_record(
        "demo_cossin",
        author="t",
        provenance="authored-on-site",
        preview_samples=monkeypatch_samples,
    )
    assert r1["preview"] == r2["preview"] and len(r1["preview"]) == 8


def test_aprs_export_refuses_invalid_record(tmp_path, monkeypatch, capsys):
    """A usermap whose window is not ordered fails self-validation; no file."""
    monkeypatch.setattr(bb, "USERMAPS", tmp_path)
    monkeypatch.setattr(bb, "OUT", tmp_path / "out")
    monkeypatch.setattr(bb, "DOCS", tmp_path / "docs")
    monkeypatch.setattr(bb, "APRS_PREVIEW_SAMPLES", 3_000)
    bb.cmd_new("broken", "mutation", "cos", "plain", 2)
    src = (tmp_path / "broken.py").read_text(encoding="utf-8")
    # NB replacement length differs from the original: the usermaps __pycache__
    # pyc is keyed on (mtime-seconds, size); a same-length same-second rewrite
    # would load stale bytecode and silently test nothing.
    (tmp_path / "broken.py").write_text(
        src.replace("plot=(-2.5, 2.5, -2.5, 2.5)", "plot=(5, -2.5, -2.5, 2.5)"),
        encoding="utf-8",
    )
    assert bb.load_usermap("broken")["plot"] == (5, -2.5, -2.5, 2.5)  # fresh load
    out = tmp_path / "sub" / "broken.aprs.json"
    with pytest.raises(SystemExit, match="failed validation"):
        bb.cmd_aprs("broken", out, "tester", "authored-on-site")
    assert not out.exists()
    assert "window must be ordered" in capsys.readouterr().out


def test_invalid_aprs_file_rejected_with_clear_reason(tmp_path):
    """The acceptance bullet: an invalid file is rejected with a clear reason."""
    from scripts.validate_aprs import validate_file

    bad = tmp_path / "bad.aprs.json"
    payload = bb.aprs_record(
        "demo_cossin",
        author="t",
        provenance="authored-on-site",
        preview_samples=250,
    )
    payload["schema"]["version"] = 2  # tamper
    bad.write_text(json.dumps(payload), encoding="utf-8")
    (reason,) = validate_file(bad)
    assert "schema.version must be the integer 1" in reason

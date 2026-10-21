"""APRS validator tests: scripts/validate_aprs.py at 100% line+branch.

The validator is the structural authority for .aprs.json records
(docs/adr/0001-aprs.md) — every failure branch below is a documented
rejection reason the intake workflow quotes back to submitters.
"""

import json

import pytest

from scripts import validate_aprs as va

VALID = {
    "schema": {"version": 1},
    "name": "demo_cossin",
    "grammar": {"family": "mutation", "real": "cos", "imag": "plain", "power": 2},
    "window": [-2.5, 2.5, -2.5, 2.5],
    "caps": [60, 300, 1000],
    "gamma": 1.3,
    "notes": "seed record",
    "author": "tester",
    "created": "2026-10-21T12:00:00Z",
    "renderer": "fractal-darkroom",
    "provenance": "authored-on-site",
    "preview": "9edd1c0b",
}


def rec(**over: object) -> dict:
    out = dict(VALID)
    for k, v in over.items():
        if v is ...:  # sentinel: delete the key entirely
            out.pop(k, None)
        else:
            out[k] = v
    return out


def reasons(**over: object) -> list[str]:
    return va.validate_data(rec(**over))


def test_valid_record_passes():
    assert va.validate_data(VALID) == []
    assert va.validate_data(rec(preview=None)) == []
    assert va.validate_data(rec(created="2026-10-21T12:00:00.123+02:00")) == []
    assert va.validate_data(rec(name="A map name-2")) == []


def test_top_level_must_be_object():
    assert va.validate_data([VALID]) == ["top level must be a JSON object"]
    assert va.validate_data("nope") == ["top level must be a JSON object"]


def test_unknown_and_missing_fields():
    r = reasons(extra_field="x")
    assert any("unknown field 'extra_field'" in p for p in r)
    r = reasons(schema=...)
    assert any("missing required field 'schema'" in p for p in r)
    # no unknown keys / no missing keys: the comprehension else-arcs
    assert va.validate_data(VALID) == []


def test_schema_block():
    assert any("schema must be an object" in p for p in reasons(schema="v1"))
    r = reasons(schema={"version": 1, "junk": 2})
    assert any("unknown field 'junk' in schema" in p for p in r)
    for bad in (2, "1", 1.0, None, True):
        r = reasons(schema={"version": bad})
        assert any("schema.version must be the integer 1" in p for p in r), bad


@pytest.mark.parametrize(
    "name",
    ["", "x" * 41, "bad name!", "-leading", "tab\tname"],
)
def test_name_rules(name):
    assert any("name must be" in p for p in reasons(name=name))


def test_grammar_block():
    assert any("grammar must be an object" in p for p in reasons(grammar="cos"))
    # a deleted grammar reports as missing (not as wrong type)
    assert any("missing required field 'grammar'" in p for p in reasons(grammar=...))
    r = reasons(grammar={**VALID["grammar"], "family": "bogus"})
    assert any("grammar.family must be one of" in p for p in r)
    r = reasons(grammar={**VALID["grammar"], "family": 3})
    assert any("grammar.family must be one of" in p for p in r)
    r = reasons(grammar={**VALID["grammar"], "real": "sec"})
    assert any("grammar.real must be one of" in p for p in r)
    r = reasons(grammar={**VALID["grammar"], "imag": None})
    assert any("grammar.imag must be one of" in p for p in r)
    for bad in (6, "2", 2.5, True):
        r = reasons(grammar={**VALID["grammar"], "power": bad})
        assert any("grammar.power must be an integer" in p for p in r), bad
    r = reasons(grammar={**VALID["grammar"], "junk": 1})
    assert any("unknown field 'junk' in grammar" in p for p in r)


def test_window_rules():
    for bad in (
        "[-2.5, 2.5]",  # wrong type
        [1, 2, 3],  # wrong length
        [1, 2, 3, float("nan")],  # non-finite (late element fails)
        [float("nan"), 1, 2, 3],  # non-finite (first element fails)
        [1, 2, 3, 1e9],  # out of bounds
        [True, 2, 3, 4],  # bool is not a number here
    ):
        r = reasons(window=bad)
        assert any("window must be 4 finite numbers" in p for p in r), bad
    r = reasons(window=[2.5, -2.5, -2.5, 2.5])  # x1 < x0
    assert any("window must be ordered" in p for p in r)
    r = reasons(window=[-2.5, 2.5, 2.5, -2.5])  # y1 < y0
    assert any("window must be ordered" in p for p in r)


def test_caps_rules():
    for bad in (
        "60,300,1000",
        [60, 300],
        [60, 300, 1000, 5000],
        [0, 300, 1000],
        [60, 300, 100_001],
        ["60", 300, 1000],  # first element fails
        [60, 300.5, 1000],
        [60, True, 1000],
    ):
        r = reasons(caps=bad)
        assert any("caps must be 3 integers" in p for p in r), bad
    r = reasons(caps=[300, 60, 1000])  # descending
    assert any("caps must be 3 strictly ascending" in p for p in r)
    r = reasons(caps=[60, 60, 1000])  # equal pair
    assert any("caps must be 3 strictly ascending" in p for p in r)


def test_gamma_notes_author_rules():
    for bad in (0, -1, 11, float("inf"), "1.3", True, None):
        r = reasons(gamma=bad)
        assert any("gamma must be a finite number" in p for p in r), bad
    r = reasons(notes="x" * 2001)
    assert any("notes must be a string" in p for p in r)
    r = reasons(notes=7)
    assert any("notes must be a string" in p for p in r)
    for bad in ("", "y" * 81, 5):
        r = reasons(author=bad)
        assert any("author must be a string of 1-80" in p for p in r), bad


def test_created_rules():
    for bad in (
        123,
        "not-a-date",
        "2026-10-21 12:00:00Z",  # space separator: regex rejects
        "2026-10-21T12:00:00",  # naive: no timezone
        "2026-13-21T12:00:00Z",  # regex ok, calendar invalid
        "2026-10-21T25:00:00Z",  # regex ok, clock invalid
    ):
        r = reasons(created=bad)
        assert any("created must be an RFC 3339" in p for p in r), bad


def test_parse_created_helper_direct():
    assert va._parse_created("2026-10-21T12:00:00") is None  # naive
    assert va._parse_created(7) is None  # non-string branch
    assert va._parse_created("2026-10-21T12:00:00Z") is not None


def test_renderer_provenance_preview_rules():
    r = reasons(renderer="other-renderer")
    assert any("renderer must be 'fractal-darkroom'" in p for p in r)
    r = reasons(renderer=...)
    assert any("renderer must be 'fractal-darkroom'" in p for p in r)
    r = reasons(provenance="imported")
    assert any("provenance must be one of" in p for p in r)
    for bad in ("DEADBEEF", "deadbee", "deadbeeff", 12, ["d", "e"]):
        r = reasons(preview=bad)
        assert any("preview must be null or 8 lowercase hex" in p for p in r), bad


def test_many_problems_reported_together():
    r = reasons(name="", gamma=0, renderer="x")
    assert len([p for p in r if p]) >= 3


def test_absent_window_and_caps_report_missing():
    r = reasons(window=..., caps=...)
    assert any("missing required field 'window'" in p for p in r)
    assert any("missing required field 'caps'" in p for p in r)


# ------------------------------------------------------------- file + CLI


def _write(tmp_path, obj, name="t.aprs.json"):
    p = tmp_path / name
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return p


def test_validate_file_ok(tmp_path):
    assert va.validate_file(_write(tmp_path, VALID)) == []


def test_validate_file_unreadable(tmp_path):
    (r,) = va.validate_file(tmp_path / "missing.aprs.json")
    assert "cannot read" in r


def test_validate_file_not_utf8(tmp_path):
    p = tmp_path / "bin.aprs.json"
    p.write_bytes(b"\xff\xfe\x00garbage")
    (r,) = va.validate_file(p)
    assert "not valid UTF-8" in r


def test_validate_file_bad_json(tmp_path):
    (r,) = va.validate_file(_write(tmp_path, "{oops"))
    assert "not valid JSON" in r and "line" in r


def test_validate_file_invalid_record(tmp_path):
    rs = va.validate_file(_write(tmp_path, rec(gamma=0)))
    assert any("gamma" in p for p in rs)


def test_cli_ok_exit_zero(tmp_path, capsys):
    p = _write(tmp_path, VALID)
    va.main([str(p)])
    assert "OK" in capsys.readouterr().out


def test_cli_invalid_exit_one_with_reasons(tmp_path, capsys):
    p = _write(tmp_path, rec(caps=[1000, 300, 60]))
    with pytest.raises(SystemExit) as ei:
        va.main([str(p)])
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "caps must be 3 strictly ascending" in err

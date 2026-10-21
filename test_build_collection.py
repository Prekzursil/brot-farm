"""Collection index tests: scripts/build_collection.py at 100% line+branch.

The intake workflow runs this script before opening its curation PR, so a
record that fails validation can never reach the rendered collection page.
"""

import json

import pytest

from scripts import build_collection as bc
from test_validate_aprs import VALID


def seed(col_dir, fname, **over):
    d = dict(VALID)
    d.update(over)
    p = col_dir / f"{fname}.aprs.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


def test_index_valid_sorted_and_outputs_written(tmp_path, capsys):
    col, docs = tmp_path / "collection", tmp_path / "docs"
    col.mkdir()
    seed(col, "aaaa1111", created="2026-10-02T00:00:00Z", name="older")
    seed(col, "bbbb2222", created="2026-10-01T00:00:00Z", name="newer")
    seed(col, "zzzz3333", created="2026-10-01T00:00:00Z", name="same_ts")
    entries = bc.write_outputs(col, docs)
    assert [e["name"] for e in entries] == ["newer", "same_ts", "older"]
    assert entries[0]["file"] == "bbbb2222.aprs.json"
    index = json.loads((col / "index.json").read_text(encoding="utf-8"))
    assert index["schema"] == {"version": 1} and len(index["entries"]) == 3
    js = (docs / "assets" / "collection.js").read_text(encoding="utf-8")
    assert js.startswith(bc.JS_HEADER) and "window.BROT_COLLECTION = " in js
    assert "older" in js
    assert "entries" in capsys.readouterr().out


def test_index_rejects_invalid_record(tmp_path):
    col = tmp_path / "collection"
    col.mkdir()
    seed(col, "good1111")
    bad = col / "bad2222.aprs.json"
    bad.write_text(json.dumps({**VALID, "gamma": 0}), encoding="utf-8")
    with pytest.raises(SystemExit, match="invalid APRS"):
        bc.build_index(col)


def test_index_missing_dir(tmp_path):
    with pytest.raises(SystemExit, match="does not exist"):
        bc.build_index(tmp_path / "nope")


def test_index_empty_dir(tmp_path):
    (tmp_path / "empty").mkdir()
    assert bc.build_index(tmp_path / "empty") == []


def test_main_with_explicit_dirs(tmp_path):
    col, docs = tmp_path / "c2", tmp_path / "d2"
    col.mkdir()
    seed(col, "cccc4444")
    bc.main(["--collection-dir", str(col), "--docs-dir", str(docs)])
    assert (col / "index.json").exists()
    assert (docs / "assets" / "collection.js").exists()


def test_main_with_module_defaults(tmp_path, monkeypatch):
    col, docs = tmp_path / "c3", tmp_path / "d3"
    col.mkdir()
    seed(col, "dddd5555")
    monkeypatch.setattr(bc, "COLLECTION", col)
    monkeypatch.setattr(bc, "DOCS", docs)
    bc.main([])
    assert (docs / "assets" / "collection.js").exists()

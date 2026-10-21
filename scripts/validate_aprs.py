#!/usr/bin/env python3
"""APRS validator — the structural authority for .aprs.json records.

APRS = Attractor Parameter Record Set (docs/adr/0001-aprs.md): a versioned,
human-readable JSON record of one fractal-darkroom experiment. This script is
stdlib-only and enforces docs/aprs.schema.json *plus* the cross-field rules
draft-07 cannot express (window/caps ordering, RFC 3339 parsing).

CLI: exit 0 with "OK <path>" when valid; exit 1 with one specific reason per
line otherwise.

    python scripts/validate_aprs.py my_map.aprs.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, TypeGuard

FAMILIES = ("mutation", "fold", "power")
REAL_OPS = ("cos", "sin", "tan", "sinh", "exp", "abs")
IMAG_OPS = ("plain", "cos", "abs", "neg", "absxy")
PROVENANCES = ("authored-on-site", "imported-bundle")
RENDERER = "fractal-darkroom"
POWER_MIN, POWER_MAX = 2, 5
CAP_MAX = 100_000
GAMMA_MAX = 10.0
WINDOW_ABS_MAX = 1e4
NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ -]*$")
PREVIEW_RE = re.compile(r"^[0-9a-f]{8}$")
CREATED_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)
REQUIRED = (
    "schema",
    "name",
    "grammar",
    "window",
    "caps",
    "gamma",
    "notes",
    "author",
    "created",
    "renderer",
    "provenance",
    "preview",
)
ALLOWED = frozenset(REQUIRED)


def _is_num(v: Any) -> TypeGuard[int | float]:
    """JSON number (bool is an int subclass in Python — exclude it)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_int(v: Any) -> TypeGuard[int]:
    return isinstance(v, int) and not isinstance(v, bool)


def _parse_created(v: Any) -> datetime | None:
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def validate_data(data: Any) -> list[str]:
    """Return a list of specific problems ([] == valid APRS v1 record)."""
    if not isinstance(data, dict):
        return ["top level must be a JSON object"]
    problems: list[str] = []
    problems += [
        f"unknown field {k!r} (strict schema: additionalProperties false)"
        for k in data
        if k not in ALLOWED
    ]
    problems += [f"missing required field {k!r}" for k in REQUIRED if k not in data]

    schema = data.get("schema")
    if isinstance(schema, dict):
        problems += [f"unknown field {k!r} in schema" for k in schema if k != "version"]
        if "version" in schema and not (
            _is_int(schema["version"]) and schema["version"] == 1
        ):
            problems.append(
                f"schema.version must be the integer 1 (got {schema['version']!r})"
            )
    elif "schema" in data:
        problems.append("schema must be an object with an integer version field")

    name = data.get("name")
    if (
        not isinstance(name, str)
        or not (1 <= len(name) <= 40)
        or not NAME_RE.match(name)
    ):
        problems.append(
            "name must be 1-40 chars matching ^[A-Za-z0-9_][A-Za-z0-9_ -]*$"
        )

    grammar = data.get("grammar")
    if isinstance(grammar, dict):
        for k, table in (
            ("family", FAMILIES),
            ("real", REAL_OPS),
            ("imag", IMAG_OPS),
        ):
            v = grammar.get(k)
            if not (isinstance(v, str) and v in table):
                problems.append(f"grammar.{k} must be one of {'|'.join(table)}")
        power = grammar.get("power")
        if not (_is_int(power) and POWER_MIN <= power <= POWER_MAX):
            problems.append(
                f"grammar.power must be an integer in [{POWER_MIN}, {POWER_MAX}]"
            )
        problems += [
            f"unknown field {k!r} in grammar"
            for k in grammar
            if k not in {"family", "real", "imag", "power"}
        ]
    elif "grammar" in data:
        problems.append("grammar must be an object {family, real, imag, power}")

    window = data.get("window")
    if (
        isinstance(window, list)
        and len(window) == 4
        and all(
            _is_num(v) and math.isfinite(v) and abs(v) <= WINDOW_ABS_MAX for v in window
        )
    ):
        if not (window[1] > window[0] and window[3] > window[2]):
            problems.append("window must be ordered [x0<x1, y0<y1]")
    elif "window" in data:
        problems.append(
            f"window must be 4 finite numbers with |v| <= {WINDOW_ABS_MAX:.0f}"
        )

    caps = data.get("caps")
    if (
        isinstance(caps, list)
        and len(caps) == 3
        and all(_is_int(c) and 0 < c <= CAP_MAX for c in caps)
    ):
        if not (caps[0] < caps[1] < caps[2]):
            problems.append("caps must be 3 strictly ascending iteration caps")
    elif "caps" in data:
        problems.append(f"caps must be 3 integers with 0 < cap <= {CAP_MAX}")

    gamma = data.get("gamma")
    if not (_is_num(gamma) and math.isfinite(gamma) and 0 < gamma <= GAMMA_MAX):
        problems.append(f"gamma must be a finite number in (0, {GAMMA_MAX:.0f}]")

    notes = data.get("notes")
    if not (isinstance(notes, str) and len(notes) <= 2000):
        problems.append("notes must be a string of at most 2000 chars")

    author = data.get("author")
    if not (isinstance(author, str) and 1 <= len(author) <= 80):
        problems.append("author must be a string of 1-80 chars")

    created = data.get("created")
    if (
        not isinstance(created, str)
        or CREATED_RE.match(created) is None
        or _parse_created(created) is None
    ):
        problems.append(
            "created must be an RFC 3339 date-time with timezone (e.g. 2026-10-21T12:00:00Z)"
        )

    if data.get("renderer") != RENDERER:
        problems.append(f"renderer must be {RENDERER!r}")

    provenance = data.get("provenance")
    if not (isinstance(provenance, str) and provenance in PROVENANCES):
        problems.append(f"provenance must be one of {'|'.join(PROVENANCES)}")

    preview = data.get("preview")
    if preview is not None and not (
        isinstance(preview, str) and PREVIEW_RE.match(preview)
    ):
        problems.append("preview must be null or 8 lowercase hex chars (sha1[:8])")

    return problems


def validate_file(path: Path) -> list[str]:
    """Load + validate; file/JSON problems are reported the same way."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read {path}: {exc}"]
    except UnicodeDecodeError as exc:
        return [f"not valid UTF-8: {exc.reason}"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"]
    return validate_data(data)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="validate_aprs",
        description="Validate an APRS (.aprs.json) record; exit 1 with reasons on failure.",
    )
    ap.add_argument("file", type=Path, help="path to the .aprs.json file")
    args = ap.parse_args(argv)
    problems = validate_file(args.file)
    for p in problems:
        print(f"aprs: {p}", file=sys.stderr)
    if problems:
        raise SystemExit(1)
    print(f"OK {args.file} (schema v1)")


if __name__ == "__main__":  # pragma: no cover
    main()

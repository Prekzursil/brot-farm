"""Brot Build Suite — author new fractal maps end to end.

Subcommands:
    new <name> --family mutation|fold|power --real cos --imag plain [--power 3]
        scaffold a user map (usermaps/<name>.py + docs card + catalogue entry)
    scout <name>       numeric window/escape scouting for a user map
    preview <name>     fast 512px 3-channel preview (seconds, ~1M samples)
    check <name>       full quality bar: config sane, escape-proof comment,
                       scalar smoke, docs card, playground catalogue parity
    mutate <base> <new-name> [--real ...] [--imag ...] [--power ...]
                       one-operator change of an existing user map
    aprs <name> --out FILE [--author A] [--provenance P]
                       export a user map as an APRS record
                       (.aprs.json, docs/adr/0001-aprs.md); the record is
                       validated with scripts/validate_aprs.py before write,
                       and re-importable in the playground ("load APRS")
    catalogue          regenerate out/catalogue.json + docs/assets/catalogue.js

Mutation grammar (identical semantics in Python and the browser playground):
    real ops f: cos sin tan sinh exp abs      -> x' = f(x*x) - y + cx
    imag ops g: plain cos abs neg absxy       -> y' = g(2xy) + cy
    power n: 2..7                              -> z^n + c family
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import brot_farm as farm

HERE = Path(__file__).resolve().parent
USERMAPS = HERE / "usermaps"
DOCS = HERE / "docs"
OUT = HERE / "out"
APRS_PREVIEW_SIZE = 128  # the APRS preview contract: a 128px PNG (ADR 0001)
APRS_PREVIEW_SAMPLES = 120_000  # per channel; deterministic (seeded rng)

REAL_OPS: dict[str, tuple[str, str]] = {  # name -> (numpy expr source, js expr source)
    "cos": ("np.cos(x * x) - y + cx", "Math.cos(x * x) - y + cx"),
    "sin": ("np.sin(x * x) - y + cx", "Math.sin(x * x) - y + cx"),
    "tan": ("np.tan(x * x) - y + cx", "Math.tan(x * x) - y + cx"),
    "sinh": ("np.sinh(x * x) - y + cx", "Math.sinh(x * x) - y + cx"),
    "exp": ("np.exp(x * x) - y + cx", "Math.exp(x * x) - y + cx"),
    "abs": ("np.abs(x * x) - y + cx", "Math.abs(x * x) - y + cx"),
}
IMAG_OPS: dict[str, tuple[str, str]] = {
    "plain": ("2.0 * x * y + cy", "2.0 * x * y + cy"),
    "cos": ("np.cos(2.0 * x * y) + cy", "Math.cos(2.0 * x * y) + cy"),
    "abs": ("np.abs(2.0 * x * y) + cy", "Math.abs(2.0 * x * y) + cy"),
    "neg": ("-2.0 * x * y + cy", "-2.0 * x * y + cy"),
    "absxy": (
        "2.0 * np.abs(x) * np.abs(y) + cy",
        "2.0 * Math.abs(x) * Math.abs(y) + cy",
    ),
}
POWER_TERMS = {
    2: ("x * x - y * y + cx", "2.0 * x * y + cy", "x * x + y * y > 4.0"),
    3: (
        "x**3 - 3 * x * y * y + cx",
        "3 * x * x * y - y**3 + cy",
        "x * x + y * y > 4.0",
    ),
    4: (
        "x**4 - 6 * x * x * y * y + y**4 + cx",
        "4 * x * y * (x * x - y * y) + cy",
        "x * x + y * y > 4.0",
    ),
    5: (
        "x**5 - 10 * x**3 * y * y + 5 * x * y**4 + cx",
        "5 * x**4 * y - 10 * x * x * y**3 + y**5 + cy",
        "x * x + y * y > 4.0",
    ),
}

MAP_TEMPLATE = '''"""User map: {name} — {desc}.

Escape predicate includes the NaN guard (diverged orbits overflow to NaN and
NaN comparisons are False; without the guard the point is misclassified as a
prisoner forever — see the project's known-issues KB).
"""
from __future__ import annotations

import numpy as np
from typing import Any


def make() -> dict[str, Any]:
    def step(x, y, cx, cy):
        return {py_real}, {py_imag}

    def gone(x, y):
        r = x * x + y * y
        return (r > {esc}) | ~np.isfinite(r)

    return dict(
        name="{name}", title="{title}", sub="{sub}",
        step=step, gone=gone, chunk=8, cull=False, invert=False, julia=None,
        samp={samp}, plot={plot}, size=(2048, 2048),
        batch=1_500_000,
        chans=((60, 8_000_000), (300, 5_000_000), (1000, 3_000_000)),
        grammar=dict(family="{family}", real="{real}", imag="{imag}", power={power}),
    )
'''


def step_sources(family: str, real: str, imag: str, power: int) -> tuple[str, str, str]:
    """Return (py_real, py_imag, escape_test_source) for a grammar choice."""
    if family == "mutation":
        return REAL_OPS[real][0], IMAG_OPS[imag][0], "1e4"
    if family == "fold":
        py_real = POWER_TERMS[power][0]
        if real == "abs":
            py_real = f"np.abs({POWER_TERMS[power][0]})"
        return py_real, IMAG_OPS[imag][0], "4.0"
    # power family
    return POWER_TERMS[power][0], POWER_TERMS[power][1], "4.0"


def formula_text(family: str, real: str, imag: str, power: int) -> str:
    if family == "mutation":
        return (
            f"x' = {real}(x^2) - y, y' = {imag == 'plain' and '2xy' or imag + '(2xy)'}"
        )
    if family == "fold":
        base = {2: "x^2-y^2", 3: "Re z^3", 4: "Re z^4", 5: "Re z^5"}[power]
        return f"x' = {'|' + base + '|' if real == 'abs' else base}, y' = {imag}(2xy)"
    return f"z -> z^{power} + c"


def cmd_new(name: str, family: str, real: str, imag: str, power: int) -> Path:
    USERMAPS.mkdir(exist_ok=True)
    path = USERMAPS / f"{name}.py"
    if path.exists():
        raise SystemExit(f"user map {name!r} already exists")
    py_real, py_imag, esc = step_sources(family, real, imag, power)
    (USERMAPS / "__init__.py").write_text(
        "# generated package init — loads every user map module\n"
        "from pathlib import Path as _P\n"
        "import importlib.util as _iu\n"
        "FRACS = []\n"
        "for _f in sorted(_P(__file__).parent.glob('*.py')):\n"
        "    if _f.stem.startswith('_'):\n"
        "        continue\n"
        "    _sp = _iu.spec_from_file_location('usermaps.' + _f.stem, _f)\n"
        "    assert _sp is not None and _sp.loader is not None\n"
        "    _m = _iu.module_from_spec(_sp)\n"
        "    _sp.loader.exec_module(_m)\n"
        "    FRACS.append(_m.make())\n",
        encoding="utf-8",
    )
    path.write_text(
        MAP_TEMPLATE.format(
            name=name,
            title=" ".join(name.upper()) or name,
            sub=formula_text(family, real, imag, power),
            desc=formula_text(family, real, imag, power),
            py_real=py_real,
            py_imag=py_imag,
            family=family,
            real=real,
            imag=imag,
            power=power,
            esc=esc,
            samp="(-1.0, 1.0, -1.0, 1.0)",
            plot="(-2.5, 2.5, -2.5, 2.5)",
        ),
        encoding="utf-8",
    )
    print(f"scaffolded {path}")
    cmd_catalogue()
    return path


def load_usermap(name: str) -> dict[str, Any]:
    spec_path = USERMAPS / f"{name}.py"
    if not spec_path.exists():
        raise SystemExit(f"no user map named {name!r} (looked in {USERMAPS})")
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"usermaps.{name}", spec_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.make()


def cmd_scout(name: str) -> dict[str, Any]:
    f = load_usermap(name)
    rng = np.random.default_rng(7)
    report: dict[str, Any] = {"name": name, "windows": []}
    for w in (0.5, 0.8, 1.2, 2.0):
        cr = rng.uniform(-w, w, 60_000)
        ci = rng.uniform(-w, w, 60_000)
        with np.errstate(over="ignore", invalid="ignore"):
            m = farm.escape_mask(f, cr, ci, cr.copy(), ci.copy(), 300)
        report["windows"].append(
            {"half_width": w, "escape_fraction": round(float(m.mean()), 4)}
        )
        print(f"  window ±{w}: escape {m.mean():.2%} at cap 300")
    best = next(
        (
            wd["half_width"]
            for wd in report["windows"]
            if 0.15 <= wd["escape_fraction"] <= 0.9
        ),
        None,
    )
    report["recommended_half_width"] = best
    print(f"  recommended sampling half-width: {best}")
    (OUT / f"scout_{name}.json").parent.mkdir(exist_ok=True)
    (OUT / f"scout_{name}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def render_rgb(f: dict[str, Any], size: int, samples: int) -> np.ndarray:
    """Deterministic 3-channel density render (the preview pipeline).

    Same seeded rng and tone map on every call — the APRS preview hash
    (sha1 of the PNG bytes) is a stable function of (map, size, samples).
    """
    hists: dict[str, np.ndarray] = {}
    for ci, (cap, budget) in enumerate(f["chans"]):
        total = min(samples, budget)  # --samples caps the per-channel budget
        rng = np.random.default_rng(1000 + ci)
        W = H = size
        hist = np.zeros(W * H)
        sx0, sx1, sy0, sy1 = f["samp"]
        done = 0
        with np.errstate(over="ignore", invalid="ignore"):
            while done < total:
                n = min(150_000, total - done)
                ax = rng.uniform(sx0, sx1, n)
                ay = rng.uniform(sy0, sy1, n)
                esc = farm.escape_mask(f, ax, ay, ax.copy(), ay.copy(), cap)
                farm.plot_orbits(
                    f, ax[esc], ay[esc], ax[esc].copy(), ay[esc].copy(), cap, hist, W, H
                )
                done += n
        hists[farm.CHAN_NAMES[ci]] = hist.reshape(H, W)[::-1]
    from buddhabrot import build_rgb

    return build_rgb(
        hists, 30, 99.9, 1.3, {"red": 1.15, "green": 1.05, "blue": 0.90}, 1.15
    )


def cmd_preview(name: str, size: int = 512, samples: int = 900_000) -> Path:
    from PIL import Image

    f = load_usermap(name)
    rgb = render_rgb(f, size, samples)
    u8 = (rgb * 255.0 + 0.5).astype(np.uint8)
    OUT.mkdir(exist_ok=True)
    out_path = OUT / f"preview_{name}.png"
    Image.fromarray(u8).save(out_path)
    thumb = DOCS / "maps" / f"{name}.jpg"
    thumb.parent.mkdir(exist_ok=True)
    im = Image.fromarray(u8)
    im.thumbnail((460, 460))
    im.save(thumb, "JPEG", quality=84)
    print(f"preview -> {out_path} (thumb {thumb})")
    cmd_catalogue()
    return out_path


def aprs_record(
    name: str,
    *,
    author: str,
    provenance: str,
    preview_samples: int,
) -> dict[str, Any]:
    """Build an APRS v1 record (docs/adr/0001-aprs.md) for a user map.

    preview = sha1[:8] of the deterministic 128px preview PNG.
    """
    from PIL import Image

    f = load_usermap(name)
    u8 = (render_rgb(f, APRS_PREVIEW_SIZE, preview_samples) * 255.0 + 0.5).astype(
        np.uint8
    )
    buf = io.BytesIO()
    Image.fromarray(u8).save(buf, "PNG")
    g = f["grammar"]
    return {
        "schema": {"version": 1},
        "name": name,
        "grammar": {
            "family": str(g["family"]),
            "real": str(g["real"]),
            "imag": str(g["imag"]),
            "power": int(g["power"]),
        },
        "window": [float(v) for v in f["plot"]],
        "caps": [int(c[0]) for c in f["chans"]],
        "gamma": 1.3,  # the preview pipeline's tone gamma (build_rgb call above)
        "notes": f"{f['sub']} — exported by brot_build aprs",
        "author": author,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "renderer": "fractal-darkroom",
        "provenance": provenance,
        "preview": hashlib.sha1(buf.getvalue()).hexdigest()[:8],
    }


def cmd_aprs(name: str, out: Path, author: str, provenance: str) -> Path:
    """Export a user map as APRS; self-validates before writing."""
    from scripts.validate_aprs import validate_data

    rec = aprs_record(
        name,
        author=author,
        provenance=provenance,
        preview_samples=APRS_PREVIEW_SAMPLES,
    )
    problems = validate_data(rec)
    if problems:
        for p in problems:
            print(f"  FAIL aprs: {p}")
        raise SystemExit(f"APRS export of {name!r} failed validation; nothing written")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    print(f"APRS -> {out} (preview {rec['preview']}, validator OK)")
    return out


def catalogue_entries() -> list[dict[str, Any]]:
    entries = []
    for p in sorted(USERMAPS.glob("*.py")) if USERMAPS.exists() else []:
        if p.stem.startswith("_"):
            continue
        import importlib.util

        spec = importlib.util.spec_from_file_location(f"usermaps.{p.stem}", p)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cfg = mod.make()
        preview = DOCS / "maps" / f"{p.stem}.jpg"
        entries.append(
            {
                "name": cfg["name"],
                "formula": cfg["sub"],
                "window": list(cfg["plot"]),
                "caps": [c[0] for c in cfg["chans"]],
                "preview": f"maps/{p.stem}.jpg" if preview.exists() else None,
                "hasPreview": preview.exists(),
                "grammar": cfg.get("grammar"),
            }
        )
    return entries


def cmd_catalogue() -> list[dict[str, Any]]:
    entries = catalogue_entries()
    OUT.mkdir(exist_ok=True)
    (DOCS / "assets").mkdir(parents=True, exist_ok=True)
    (OUT / "catalogue.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    (DOCS / "assets" / "catalogue.js").write_text(
        "// generated by brot_build.py catalogue — shared Python<->JS map list\n"
        "// (parity gate: every usermaps/ entry must appear here)\n"
        f"window.BROT_CATALOGUE = {json.dumps(entries)};\n",
        encoding="utf-8",
    )
    print(
        f"catalogue: {len(entries)} entries -> out/catalogue.json + docs/assets/catalogue.js"
    )
    return entries


def cmd_check(name: str) -> bool:
    problems: list[str] = []
    f = load_usermap(name)
    src = (USERMAPS / f"{name}.py").read_text(encoding="utf-8")
    if "~np.isfinite" not in src:
        problems.append("escape predicate missing the NaN guard (~np.isfinite)")
    # config sanity via the farm's own checker semantics
    try:
        assert len(f["chans"]) == 3
        for cap, samples in f["chans"]:
            assert 0 < cap <= 100_000 and samples > 0
    except AssertionError:
        problems.append(
            "channel config failed sanity (3 channels, 0<cap<=100k, samples>0)"
        )
    # scalar smoke: step is finite on in-range points; known escaper escapes
    rng = np.random.default_rng(3)
    x, y = rng.uniform(-0.5, 0.5, 200), rng.uniform(-0.5, 0.5, 200)
    with np.errstate(over="ignore", invalid="ignore"):
        gx, gy = f["step"](x, y, np.zeros(200), np.zeros(200))
        if not np.isfinite(gx).any():
            problems.append("step produced no finite outputs on the sample window")
        # NB c=3.5+0i is a PRISONER here (the real axis is invariant for the
        # mutation family: y'=2xy+cy keeps y=0); the known escaper is 3.5i.
        m = farm.escape_mask(
            f, np.array([0.0]), np.array([3.5]), np.array([0.0]), np.array([3.5]), 200
        )
    if not bool(m[0]):
        problems.append("known escaper (c=3.5i) was not classified as escaping")
    # docs card + catalogue parity
    entries = {e["name"] for e in catalogue_entries()}
    if name not in entries:
        problems.append("name missing from catalogue (run: brot_build.py catalogue)")
    if not (DOCS / "maps" / f"{name}.jpg").exists():
        problems.append("no preview thumb (run: brot_build.py preview " + name + ")")
    catalogue_js = (DOCS / "assets" / "catalogue.js").read_text(encoding="utf-8")
    if name not in catalogue_js:
        problems.append(
            "name missing from docs/assets/catalogue.js (run: brot_build.py catalogue)"
        )
    for p in problems:
        print("  FAIL", p)
    print(
        "check:", "FAILED" if problems else f"OK — {name} passes the full quality bar"
    )
    return not problems


def cmd_mutate(
    base: str,
    new: str,
    real: str | None = None,
    imag: str | None = None,
    power: int | None = None,
) -> Path:
    """One-operator change of an existing user map (grammar carried in the map)."""
    g = load_usermap(base)["grammar"]
    return cmd_new(
        new,
        g["family"],
        real or g["real"],
        imag or g["imag"],
        power or g["power"],
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="brot_build")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new")
    p_new.add_argument("name")
    p_new.add_argument(
        "--family", choices=["mutation", "fold", "power"], default="mutation"
    )
    p_new.add_argument("--real", choices=sorted(REAL_OPS), default="cos")
    p_new.add_argument("--imag", choices=sorted(IMAG_OPS), default="plain")
    p_new.add_argument("--power", type=int, choices=sorted(POWER_TERMS), default=2)
    p_scout = sub.add_parser("scout")
    p_scout.add_argument("name")
    p_prev = sub.add_parser("preview")
    p_prev.add_argument("name")
    p_prev.add_argument("--size", type=int, default=512)
    p_prev.add_argument("--samples", type=int, default=900_000)
    p_check = sub.add_parser("check")
    p_check.add_argument("name")
    p_mut = sub.add_parser("mutate")
    p_mut.add_argument("base")
    p_mut.add_argument("new")
    p_mut.add_argument("--real", choices=sorted(REAL_OPS))
    p_mut.add_argument("--imag", choices=sorted(IMAG_OPS))
    p_mut.add_argument("--power", type=int, choices=sorted(POWER_TERMS))
    p_aprs = sub.add_parser("aprs")
    p_aprs.add_argument("name")
    p_aprs.add_argument(
        "--out", type=Path, required=True, help="output .aprs.json path"
    )
    p_aprs.add_argument("--author", default="brot_build CLI")
    p_aprs.add_argument(
        "--provenance",
        choices=["authored-on-site", "imported-bundle"],
        default="authored-on-site",
    )
    sub.add_parser("catalogue")
    args = ap.parse_args(argv)

    if args.cmd == "new":
        cmd_new(args.name, args.family, args.real, args.imag, args.power)
    elif args.cmd == "scout":
        cmd_scout(args.name)
    elif args.cmd == "preview":
        cmd_preview(args.name, args.size, args.samples)
    elif args.cmd == "check":
        raise SystemExit(0 if cmd_check(args.name) else 1)
    elif args.cmd == "mutate":
        cmd_mutate(args.base, args.new, args.real, args.imag, args.power)
    elif args.cmd == "aprs":
        cmd_aprs(args.name, args.out, args.author, args.provenance)
        return
    # args.cmd == "catalogue" is the remaining choice (argparse guarantees it)
    cmd_catalogue()


if __name__ == "__main__":  # pragma: no cover
    main()

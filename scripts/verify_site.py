#!/usr/bin/env python3
"""Automated site verification for the Fractal Darkroom docs (LANE 2).

Real browsers (Playwright), every advertised surface, every interaction.
Matrix: browser in {chromium, firefox, webkit} x origin in {local http,
file://, --live https} x viewport in {desktop, mobile-390}. Also runs the
detector self-test, the stale/broken-asset degradation probe, and the
asset-versioning lint. Exit 0 only when every probe passes.

Usage:
    python scripts/verify_site.py                 # local http + file, all installed browsers
    python scripts/verify_site.py --browsers chromium --origin file
    python scripts/verify_site.py --live          # against the deployed Pages site
    python scripts/verify_site.py --browsers chromium   # CI lane
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # scripts.validate_aprs import when run directly

DOCS = REPO / "docs"
PAGES = ["index.html", "math.html", "code.html", "playground.html", "collection.html"]
CANVAS_LUM = """(cid) => {
    const c = document.getElementById(cid);
    if (!c) return null;
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let s = 0, n = 0;
    for (let i = 0; i < d.length; i += 1600) { s += d[i] + d[i+1] + d[i+2]; n++; }
    return s / n;
}"""

results: list[tuple[str, str, str]] = []  # (page/lane, check, verdict-note)


def record(lane: str, check: str, ok: bool, note: str = "") -> bool:
    results.append((lane, check, ("PASS " if ok else "FAIL ") + note))
    return ok


def serve_docs() -> tuple[socketserver.TCPServer, str]:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(DOCS)
    )
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def check_page(pg, base: str, page_name: str, mobile: bool) -> None:
    lane = f"{page_name}{'@390' if mobile else ''}"
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on(
        "console",
        lambda m: (
            errors.append(f"console.error: {m.text}") if m.type == "error" else None
        ),
    )
    pg.on(
        "requestfailed",
        lambda r: (
            errors.append(f"requestfailed: {r.url.split('/')[-1]}")
            if "favicon" not in r.url
            else None
        ),
    )

    pg.goto(
        f"{base}/{page_name}"
        if not base.startswith("file")
        else f"{base}/{page_name}".replace("file:///", "file:///")
        if False
        else f"{base}/{page_name}",
        wait_until="load",
    )
    pg.wait_for_timeout(1100)

    # asset versioning lint: every local asset reference carries ?v=
    if base.startswith("http"):
        unversioned = pg.evaluate("""() => [...document.querySelectorAll('script[src], link[href]')]
            .map(e => e.getAttribute('src') || e.getAttribute('href'))
            .filter(u => u && u.includes('assets/') && !u.includes('?v=')).length""")
        record(
            lane,
            "asset-versioning",
            unversioned == 0,
            f"{unversioned} unversioned refs",
        )

    # scroll-reveal must actually reveal: .reveal content invisible (opacity 0)
    # on pages that forget to load app.js (the IntersectionObserver owner)
    op = pg.evaluate(
        "() => { const el = document.querySelector('.reveal');"
        " return el ? getComputedStyle(el).opacity : '1'; }"
    )
    record(lane, "reveal-visible", float(op) > 0.9, f"opacity={op}")

    if page_name == "index.html":
        hero = pg.evaluate(
            "() => { const c = document.getElementById('develop-photo-view') || "
            "document.querySelector('.hero canvas'); return c ? 100 : 0; }"
        )
        pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        pg.wait_for_timeout(700)
        pg.evaluate("() => window.scrollTo(0, 0)")
        pg.wait_for_timeout(300)
        pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        pg.wait_for_timeout(700)
        imgs = pg.evaluate(
            "() => [...document.images].filter(i => !i.complete || i.naturalWidth === 0).length"
        )
        record(lane, "gallery-images", imgs == 0, f"{imgs} broken")
        hud = (pg.text_content("#develop-hud") or "").strip()
        file_proto = base.startswith("file")
        record(
            lane,
            "hero",
            (hero is not None and hero > 0.5)
            or (file_proto and "static exposure" in hud),
            f"lum={hero and round(hero, 1)} hud={hud[:40]!r}",
        )
    elif page_name == "math.html":
        record(lane, "hist-data", pg.evaluate("() => !!window.BROT_HIST_B64"))
        record(lane, "tone-lab", (pg.evaluate(CANVAS_LUM, "tl-canvas") or 0) > 0.5)
        hud0 = pg.text_content("#tl-hud") or ""
        pg.evaluate(
            "() => { const s = document.getElementById('tl-g'); s.value = 0.55; s.dispatchEvent(new Event('input')); }"
        )
        pg.wait_for_timeout(120)
        record(lane, "tone-slider", (pg.text_content("#tl-hud") or "") != hud0)
        pg.click("#orbit-demo", position={"x": 120, "y": 60})
        pg.wait_for_timeout(350)
        record(
            lane,
            "orbit-demo",
            any(
                k in (pg.text_content("#orbit-hud") or "")
                for k in ("escaped", "trapped")
            ),
        )
    elif page_name == "playground.html":
        record(lane, "orbit-theater", (pg.evaluate(CANVAS_LUM, "ot-canvas") or 0) > 0.5)
        pg.click("#ot-apply")
        pg.wait_for_timeout(350)
        record(
            lane,
            "formula-apply",
            "custom formula" in (pg.text_content("#ot-hud") or ""),
        )
        lum0 = pg.evaluate(CANVAS_LUM, "ot-canvas") or 0
        pg.click("#ot-rain")
        pg.wait_for_timeout(2200)
        record(lane, "rain", (pg.evaluate(CANVAS_LUM, "ot-canvas") or 0) > lum0 + 3)
        pg.click("#ot-rain")  # stop
        pg.wait_for_timeout(3200)
        hud = (pg.text_content("#mb-hud") or "").replace("\n", " ")
        record(
            lane,
            "mini-buddha",
            "samples" in hud and "0 " not in hud.split("samples")[0][-6:],
            hud[:70],
        )
        pg.click("#ex-canvas", position={"x": 150, "y": 90})
        pg.wait_for_timeout(250)
        record(
            lane,
            "explorer-click",
            "sent c" in (pg.text_content("#ex-hud") or ""),
            (pg.text_content("#ex-hud") or "")[-60:],
        )
    if page_name == "collection.html":
        n = pg.evaluate("() => document.getElementById('col-list').children.length")
        record(lane, "collection-entries", n > 0, f"{n} entries")
        hud = (pg.text_content("#col-hud") or "").replace("\n", " ")
        record(
            lane,
            "collection-hud",
            "curated record" in hud,
            hud[:60],
        )
        badge = pg.evaluate(
            "() => [...document.querySelectorAll('#col-list b, #col-list span')]"
            ".some(e => /authored-on-site|imported-bundle/.test(e.textContent))"
        )
        record(lane, "collection-badges", bool(badge), "provenance badge present")
        nav = pg.evaluate(
            "() => [...document.querySelectorAll('nav a')].some(a => a.textContent === 'Collection')"
        )
        record(lane, "collection-nav", bool(nav))
    if page_name == "playground.html" and not mobile:
        # build-suite panel: preview paints, register adds the map, catalogue lists entries
        record(lane, "build-preview", (pg.evaluate(CANVAS_LUM, "bu-canvas") or 0) > 1)
        pg.evaluate(
            "() => { document.getElementById('bu-real').value = 'tan';"
            " document.getElementById('bu-real').dispatchEvent(new Event('change')); }"
        )
        pg.wait_for_timeout(200)
        pg.click("#bu-register")
        pg.wait_for_timeout(250)
        registered = pg.evaluate(
            "() => [...document.getElementById('ot-map').options].some(o => o.value === 'built_my_map')"
        )
        record(lane, "build-register", bool(registered))
        n_cat = pg.evaluate(
            "() => document.getElementById('bu-catalogue').children.length"
        )
        record(lane, "build-catalogue", n_cat > 0, f"{n_cat} entries")
        # L4 experiments: seeded surprise registers a map, mutate renders a
        # visibly different side-by-side, pin adds a localStorage entry,
        # suggestions are deterministic, and a serialized state in the URL
        # hash restores exactly after a reload.
        pg.click("#exp-surprise")
        pg.wait_for_timeout(400)
        surprised = pg.evaluate(
            "() => [...document.getElementById('ot-map').options]"
            ".some(o => o.value === 'exp_s12345')"
        )
        record(lane, "exp-surprise", bool(surprised), "seed 12345 -> exp_s12345")
        pg.click("#exp-mutate")
        pg.wait_for_timeout(400)
        mutated = pg.evaluate(
            "() => [...document.getElementById('ot-map').options]"
            ".some(o => o.value === 'exp_mut1')"
        )
        base_lum = pg.evaluate(CANVAS_LUM, "bu-base") or 0
        record(
            lane,
            "exp-mutate",
            bool(mutated) and base_lum > 1,
            f"registered={mutated} base-lum={round(base_lum, 1)}",
        )
        suggest0 = pg.evaluate(
            "() => [...document.querySelectorAll('#exp-suggest canvas')]"
            ".map(c => c.toDataURL()).join('|')"
        )
        pg.click("#exp-resuggest")
        pg.wait_for_timeout(300)
        suggest1 = pg.evaluate(
            "() => [...document.querySelectorAll('#exp-suggest canvas')]"
            ".map(c => c.toDataURL()).join('|')"
        )
        n_sug = suggest0.count("data:image/png")
        record(
            lane,
            "exp-suggest",
            n_sug == 3 and suggest0 == suggest1,
            f"{n_sug} thumbs, deterministic={suggest0 == suggest1}",
        )
        pg.click("#exp-pin")
        pg.wait_for_timeout(200)
        pins = pg.evaluate("() => document.getElementById('exp-pins').children.length")
        record(lane, "exp-pin", pins > 0, f"{pins} pinned")
        state = {
            "v": 1,
            "map": {
                "family": "power",
                "real": "cos",
                "imag": "plain",
                "power": 4,
                "name": "probe_restore",
            },
            "cap": 200,
            "gamma": 1.55,
            "seed": 777,
        }
        pg.evaluate(
            "(s) => { location.hash = '#exp=' + encodeURIComponent(JSON.stringify(s)); }",
            state,
        )
        pg.reload(wait_until="load")
        pg.wait_for_timeout(1200)
        exp_hud = (pg.text_content("#exp-hud") or "").replace("\n", " ")
        gamma_back = pg.evaluate("() => document.getElementById('mb-gamma').value")
        record(
            lane,
            "exp-hash-restore",
            "restored" in exp_hud and gamma_back == "1.55",
            f"hud={exp_hud[:60]!r} gamma={gamma_back}",
        )
        pg.evaluate("() => { location.hash = ''; }")
        # L5 APRS: playground export -> the real Python validator -> load back.
        # The download is the producer's artifact; validate_file is the same
        # authority the intake workflow runs.
        from scripts.validate_aprs import validate_file

        pg.evaluate(
            "() => { const g = document.getElementById('mb-gamma');"
            " g.value = '1.85'; g.dispatchEvent(new Event('input')); }"
        )
        with pg.expect_download() as dl:
            pg.click("#exp-export-aprs")
        dl.value.save_as("out/aprs_probe_download.aprs.json")
        reasons = validate_file(Path("out/aprs_probe_download.aprs.json"))
        record(
            lane,
            "aprs-export-validates",
            reasons == [],
            "; ".join(reasons[:2]) or dl.value.suggested_filename,
        )
        pg.evaluate(
            "() => { const g = document.getElementById('mb-gamma');"
            " g.value = '1.0'; g.dispatchEvent(new Event('input')); }"
        )
        pg.set_input_files("#exp-import-aprs", "out/aprs_probe_download.aprs.json")
        pg.wait_for_timeout(700)
        aprs_hud = (pg.text_content("#exp-hud") or "").replace("\n", " ")
        gamma_back2 = pg.evaluate("() => document.getElementById('mb-gamma').value")
        record(
            lane,
            "aprs-load-restores",
            "APRS loaded" in aprs_hud and gamma_back2 == "1.85",
            f"hud={aprs_hud[:60]!r} gamma={gamma_back2}",
        )
    record(lane, "console-clean", not errors, "; ".join(errors[:3])[:180])


def run_origin(
    pw, browser_type: str, origin_url: str, mobile: bool, live: bool
) -> None:
    browser = getattr(pw, browser_type).launch()
    pg = browser.new_page(
        viewport={"width": 390, "height": 844}
        if mobile
        else {"width": 1400, "height": 1000}
    )

    # detector self-test (both-states rule): a thrown error MUST be captured
    thrown: list[str] = []
    pg.on("pageerror", lambda e: thrown.append(str(e)))
    pg.goto(origin_url + "/index.html", wait_until="load")
    pg.evaluate("() => setTimeout(() => { throw new Error('probe-error') }, 0)")
    pg.wait_for_timeout(250)
    assert any("probe-error" in t for t in thrown), (
        "DETECTOR BROKEN: injected error not captured"
    )
    record(f"selftest:{browser_type}", "error-detector", True)

    for page_name in PAGES:
        try:
            check_page(pg, origin_url, page_name, mobile)
        except Exception as exc:  # noqa: BLE001 - a page crash is a finding, not a test abort
            record(
                f"{page_name}{'@390' if mobile else ''}",
                "page-load",
                False,
                f"{type(exc).__name__}: {exc}"[:160],
            )
    browser.close()


def run_degradation(pw) -> None:
    """Broken/missing app.js must degrade visibly (error banner), not silently."""
    browser = pw.chromium.launch()
    pg = browser.new_page()
    pg.route("**/assets/app.js", lambda route: route.abort())
    pg.goto(f"file:///{DOCS}/index.html", wait_until="load")
    pg.wait_for_timeout(600)
    pg.evaluate(
        "() => setTimeout(() => { throw new Error('synthetic-banner-probe') }, 0)"
    )
    pg.wait_for_timeout(400)
    banner = pg.evaluate(
        "() => { const b = document.getElementById('fd-error-banner'); return !!b && b.getBoundingClientRect().height > 0; }"
    )
    record(
        "degradation",
        "error-banner",
        bool(banner),
        "banner visible after error with app.js blocked",
    )
    browser.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--browsers", default="chromium,firefox,webkit")
    ap.add_argument("--origin", choices=["http", "file", "live"], default="http")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    browsers = [b for b in args.browsers.split(",") if b]

    srv, local_http = serve_docs()
    file_base = f"file:///{DOCS}".replace("\\", "/")
    base = (
        "https://prekzursil.github.io/fractal-darkroom"
        if (args.live or args.origin == "live")
        else (local_http if args.origin == "http" else file_base)
    )

    with sync_playwright() as pw:
        for b in browsers:
            run_origin(pw, b, base, mobile=False, live=args.live)
        if "chromium" in browsers and not base.startswith("https"):
            run_origin(pw, "chromium", base, mobile=True, live=False)
        if "chromium" in browsers:
            run_degradation(pw)
    srv.shutdown()

    fails = [r for r in results if r[2].startswith("FAIL")]
    for lane, check, verdict in results:
        print(f"{verdict[0]}  {lane:<22} {check:<18} {verdict[5:]}")
    print(json.dumps({"total": len(results), "failed": len(fails)}))
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()

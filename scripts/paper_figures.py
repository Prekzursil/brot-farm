"""Generate the fractal-darkroom paper figure sequence (F1-F5) from receipts.

Every figure is drawn ONLY from receipt artifacts of the paper tree
(default --paper-root D:/Research/projects/fractal-darkroom-paper); nothing
is recomputed or rendered here. One command regenerates the whole set,
deterministically (PDF+PNG, 300 dpi, creation-date-free for byte-stable
rebuilds), plus figures/OUTLINE.md:

    python scripts/paper_figures.py [--paper-root DIR] [--only F1,F3]

Data contract (parsers below raise ParseError on any schema drift, and the
test suite pins every schema this module consumes):
  F1  experiments/results/cell_{map}_{cap}.json        convergence receipts
  F2  experiments/data/hist_{map}_{cap}_{S}_{N}_study.npz + ref_{map}_{cap}.npz
  F3  experiments/results/fig3_nanbug.json + data/fig3_nanbug_*.npz
  F4  experiments/results/fig4_gallery.json + data/fig4_gallery_*.npz
  F5  experiments/results/grammar_facts.json (+ fig4_gallery.json cross-tab)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

DEFAULT_PAPER_ROOT = Path("D:/Research/projects/fractal-darkroom-paper")

MAPS = ("mandel", "z3", "cosmut")
CAPS = (80, 400, 1500)
MAP_TITLES = {"mandel": "z²+c (mandel)", "z3": "z³+c (power)", "cosmut": "cos mutation"}
SAMPLERS = ("S0", "S1", "S2")
SAMPLER_NAMES = {"S0": "S0 uniform", "S1": "S1 boundary-IS", "S2": "S2 MH mutation"}
# Okabe-Ito colorblind-safe palette + distinct markers/linestyles so no
# channel relies on hue alone
SAMPLER_STYLE: dict[str, dict[str, Any]] = {
    "S0": dict(color="#0072B2", marker="o", linestyle="-"),
    "S1": dict(color="#E69F00", marker="s", linestyle="--"),
    "S2": dict(color="#009E73", marker="^", linestyle=":"),
}
SEQ_CMAP = "cividis"  # designed for color-vision deficiency
DIV_CMAP = "coolwarm"


class ParseError(ValueError):
    """A receipt file does not match the schema this figure pipeline expects."""


# --------------------------------------------------------------- receipts in


def _expect(d: dict[str, Any], key: str, typ: type, ctx: str) -> Any:
    """Fetch d[key] enforcing a JSON type (bool excluded from int/float)."""
    if key not in d:
        raise ParseError(f"{ctx}: missing key {key!r}")
    v = d[key]
    if typ is float:
        ok = isinstance(v, (int, float)) and not isinstance(v, bool)
    elif typ is int:
        ok = isinstance(v, int) and not isinstance(v, bool)
    else:
        ok = isinstance(v, typ)
    if not ok:
        raise ParseError(
            f"{ctx}: {key!r} expected {typ.__name__}, got {type(v).__name__}"
        )
    return v


@dataclass(frozen=True)
class Rung:
    sampler: str
    budget: int
    mean_rel_err: float
    degenerate: bool


@dataclass(frozen=True)
class Cell:
    map_name: str
    cap: int
    rungs: dict[str, tuple[Rung, ...]]
    slopes: dict[str, float]
    ratio_s2_s0_top: float
    ref_budget: int


def parse_cell(d: dict[str, Any], ctx: str) -> Cell:
    name = _expect(d, "map", str, ctx)
    cap = _expect(d, "cap", int, ctx)
    ref = _expect(d, "reference", dict, ctx)
    ref_budget = _expect(ref, "budget", int, ctx)
    runs = _expect(d, "runs", list, ctx)
    raw_slopes = _expect(d, "convergence_loglog_slopes", dict, ctx)
    bias = _expect(d, "bias_check_top_rung", dict, ctx)
    rungs: dict[str, tuple[Rung, ...]] = {}
    slopes: dict[str, float] = {}
    for run in runs:
        s = _expect(run, "sampler", str, ctx)
        by = _expect(run, "by_budget", list, ctx)
        entries = []
        for row in by:
            entries.append(
                Rung(
                    sampler=_expect(row, "sampler", str, ctx),
                    budget=_expect(row, "budget", int, ctx),
                    mean_rel_err=_expect(row, "mean_rel_err", float, ctx),
                    degenerate=_expect(row, "degenerate", bool, ctx),
                )
            )
        rungs[s] = tuple(entries)
        sl = _expect(raw_slopes, s, dict, ctx)
        slopes[s] = _expect(sl, "slope", float, ctx)
    if not rungs:
        raise ParseError(f"{ctx}: cell has no sampler runs")
    return Cell(
        map_name=name,
        cap=cap,
        rungs=rungs,
        slopes=slopes,
        ratio_s2_s0_top=_expect(bias, "mean_rel_ratio_S2_over_S0", float, ctx),
        ref_budget=ref_budget,
    )


def load_cell(path: Path) -> Cell:
    return parse_cell(json.loads(path.read_text(encoding="utf-8")), str(path))


def load_cells(results: Path) -> dict[tuple[str, int], Cell]:
    cells = {
        (c.map_name, c.cap): c
        for c in (load_cell(p) for p in sorted(results.glob("cell_*.json")))
    }
    if not cells:
        raise ParseError(f"{results}: no cell_*.json receipts found")
    return cells


def load_hist(path: Path, key: str = "hist") -> np.ndarray:
    """2-D orbit-density histograms. The convergence study stores per-run
    histograms under 'hist' and 40M references under 'raw' (raw counts)."""
    with np.load(path) as z:
        if key not in z:
            raise ParseError(f"{path}: npz missing {key!r}")
        h = z[key]
    if h.ndim != 2:
        raise ParseError(f"{path}: hist must be 2-D, got shape {h.shape}")
    return h.astype(float)


def load_rgb(path: Path) -> np.ndarray:
    """Gallery plate images: uint8 RGB stored under 'rgb' by fig_gallery.py."""
    with np.load(path) as z:
        if "rgb" not in z:
            raise ParseError(f"{path}: npz missing 'rgb'")
        h = z["rgb"]
    if h.ndim != 3 or h.shape[2] != 3:
        raise ParseError(f"{path}: rgb must be (H, W, 3), got shape {h.shape}")
    return h


@dataclass(frozen=True)
class NanbugVariant:
    predicate: str
    n_samples: int
    n_classified: int
    escape_fraction: float


@dataclass(frozen=True)
class Nanbug:
    variants: dict[str, NanbugVariant]
    dropped_fraction: float


def parse_nanbug(d: dict[str, Any], ctx: str) -> Nanbug:
    variants = {}
    for tag in ("guarded", "unguarded"):
        v = _expect(d, tag, dict, ctx)
        variants[tag] = NanbugVariant(
            predicate=_expect(v, "predicate", str, ctx),
            n_samples=_expect(v, "n_samples", int, ctx),
            n_classified=_expect(v, "n_classified", int, ctx),
            escape_fraction=_expect(v, "escape_fraction_of_draws", float, ctx),
        )
    comp = _expect(d, "comparison", dict, ctx)
    return Nanbug(
        variants=variants,
        dropped_fraction=_expect(comp, "dropped_escaper_fraction", float, ctx),
    )


def load_nanbug(path: Path) -> Nanbug:
    return parse_nanbug(json.loads(path.read_text(encoding="utf-8")), str(path))


@dataclass(frozen=True)
class GalleryMap:
    name: str
    family: str
    real: str | None
    imag: str
    power: int
    formula: str
    sym: float
    equivariant: bool
    exit_direction: str


@dataclass(frozen=True)
class Gallery:
    maps: tuple[GalleryMap, ...]
    samples_per_channel: int


def parse_gallery(d: dict[str, Any], ctx: str) -> Gallery:
    spc = _expect(d, "samples_per_channel", int, ctx)
    raw = _expect(d, "maps", list, ctx)
    maps = []
    for m in raw:
        ops = _expect(m, "grammar_ops", dict, ctx)
        real = _expect(ops, "real", str, ctx) if ops.get("real") is not None else None
        pred = _expect(m, "predicate", dict, ctx)
        maps.append(
            GalleryMap(
                name=_expect(m, "name", str, ctx),
                family=_expect(m, "family", str, ctx),
                real=real,
                imag=_expect(ops, "imag", str, ctx),
                power=_expect(ops, "power", int, ctx),
                formula=_expect(m, "formula", str, ctx),
                sym=_expect(m, "mirror_symmetry", float, ctx),
                equivariant=_expect(m, "equivariant_prediction", bool, ctx),
                exit_direction=_expect(pred, "direction", str, ctx),
            )
        )
    if not maps:
        raise ParseError(f"{ctx}: gallery has no maps")
    return Gallery(maps=tuple(maps), samples_per_channel=spc)


def load_gallery(path: Path) -> Gallery:
    return parse_gallery(json.loads(path.read_text(encoding="utf-8")), str(path))


@dataclass(frozen=True)
class ExitPredicate:
    name: str
    direction: str
    maps: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class Grammar:
    families: dict[str, dict[str, Any]]
    op_sources: dict[str, Any]
    predicates: tuple[ExitPredicate, ...]


def parse_grammar(d: dict[str, Any], ctx: str) -> Grammar:
    g = _expect(d, "grammar", dict, ctx)
    fams = _expect(g, "families", dict, ctx)
    ops = _expect(g, "op_sources", dict, ctx)
    raw_p = _expect(d, "exit_predicates", list, ctx)
    preds = []
    for p in raw_p:
        preds.append(
            ExitPredicate(
                name=_expect(p, "name", str, ctx),
                direction=_expect(p, "exit_direction", str, ctx),
                maps=tuple(_expect(p, "maps_in_FRACS", list, ctx)),
                source=_expect(p, "source", str, ctx),
            )
        )
    return Grammar(families=fams, op_sources=ops, predicates=tuple(preds))


def load_grammar(path: Path) -> Grammar:
    return parse_grammar(json.loads(path.read_text(encoding="utf-8")), str(path))


# ------------------------------------------------------------------ helpers


def tone_log(
    h: np.ndarray, plo: float = 30.0, phi: float = 99.9
) -> tuple[float, float]:
    """Repo tone anchoring (buddhabrot.tone_channel, buddhabrot.py:177-187):
    log1p, black point at the plo-th percentile of lit pixels, white at phi."""
    v = np.log1p(h)
    pos = v[v > 0]
    if pos.size:
        lo, hi = np.percentile(pos, plo), np.percentile(pos, phi)
    else:
        lo, hi = 0.0, 1.0
    return float(lo), float(hi if hi > lo else lo + 1.0)


def rel_dev(h: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Signed relative deviation (h - ref)/ref where ref > 0, NaN elsewhere."""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (h - ref) / ref
    return np.where(ref > 0, r, np.nan)


def _im(ax: Axes, h: np.ndarray, lo: float, hi: float) -> None:
    ax.imshow(np.log1p(h), cmap=SEQ_CMAP, vmin=lo, vmax=hi, origin="upper")
    ax.set_xticks([])
    ax.set_yticks([])


def _dev_im(ax: Axes, d: np.ndarray) -> None:
    cm = plt.get_cmap(DIV_CMAP).with_extremes(bad="0.88")
    m = np.ma.masked_invalid(np.clip(d, -1.0, 1.0))
    ax.imshow(m, cmap=cm, vmin=-1.0, vmax=1.0, origin="upper")
    ax.set_xticks([])
    ax.set_yticks([])


def write_figure(fig: Figure, outdir: Path, stem: str) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    png, pdf = outdir / f"{stem}.png", outdir / f"{stem}.pdf"
    fig.savefig(png, dpi=300)
    fig.savefig(pdf, metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    return [png, pdf]


# ------------------------------------------------------------------- figures


def fig1_convergence(cells: dict[tuple[str, int], Cell]) -> Figure:
    """F1 — log-log convergence: 3 maps x 3 caps, S0/S1/S2 vs MC rate."""
    fig, axes = plt.subplots(
        3, 3, figsize=(7.2, 6.4), sharex=True, sharey=True, layout="constrained"
    )
    for r, m in enumerate(MAPS):
        for c, cap in enumerate(CAPS):
            ax = axes[r, c]
            cell = cells[(m, cap)]
            for s in SAMPLERS:
                pts = [x for x in cell.rungs[s] if not x.degenerate]
                xs = [x.budget for x in pts]
                ys = [x.mean_rel_err for x in pts]
                ax.loglog(xs, ys, markersize=3.2, linewidth=1.2, **SAMPLER_STYLE[s])
            xx = np.array([6.0e4, 5.0e6])
            ax.loglog(
                xx,
                1.2 * (xx / 1e6) ** -0.5,
                color="0.55",
                linewidth=0.9,
                zorder=0,
            )
            notes = "  ".join(f"{s} {cell.slopes[s]:.2f}" for s in SAMPLERS)
            ax.set_title(f"{MAP_TITLES[m]} · cap {cap}", fontsize=8.5, pad=3)
            ax.text(
                0.97,
                0.95,
                notes + f"\nS2/S0 @4M ×{cell.ratio_s2_s0_top:.1f}",
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=6.4,
                color="0.25",
            )
            ax.tick_params(labelsize=7)
            ax.grid(True, which="major", alpha=0.25, linewidth=0.4)
    for ax in axes[-1]:
        ax.set_xlabel("seed budget N", fontsize=8)
    for ax in axes[:, 0]:
        ax.set_ylabel("mean ROI rel. error", fontsize=8)
    handles = [
        Line2D([], [], label=f"{SAMPLER_NAMES[s]} (slope)", **SAMPLER_STYLE[s])
        for s in SAMPLERS
    ]
    handles.append(
        Line2D([], [], color="0.55", linewidth=0.9, label="MC rate N$^{-1/2}$")
    )
    fig.legend(handles=handles, loc="outside upper center", ncol=4, fontsize=8)
    axes[2][1].set_xlabel(
        "Slopes are receipted fits (cell_*.json). S1's 62.5k rung is degenerate "
        "(pre-pass consumes the budget) and is excluded.",
        fontsize=6.5,
        color="0.3",
    )
    return fig


def fig2_equal_budget(
    s0: np.ndarray, s2: np.ndarray, ref: np.ndarray, cell: Cell, budget: int
) -> Figure:
    """F2 — equal-budget crop: S0 vs S2 at N=1M against the 40M reference."""
    half = min(s0.shape) // 5
    cy, cx = np.unravel_index(int(np.argmax(ref)), ref.shape)
    ys = np.clip([cy - half, cy + half], 0, ref.shape[0])
    xs = np.clip([cx - half, cx + half], 0, ref.shape[1])
    crop = lambda a: a[ys[0] : ys[1], xs[0] : xs[1]]  # noqa: E731
    r_c = crop(ref)
    lo, hi = tone_log(r_c)
    err = {s: cell.rungs[s] for s in SAMPLERS}
    top_err = {
        s: next(r.mean_rel_err for r in err[s] if r.budget == budget)
        for s in ("S0", "S2")
    }
    fig, axes = plt.subplots(2, 3, figsize=(7.0, 4.9), layout="constrained")
    panels = (
        (crop(s0), f"S0 @ N={budget:,}\nmean ROI rel. err {top_err['S0']:.3f}"),
        (crop(s2), f"S2 @ N={budget:,}\nmean ROI rel. err {top_err['S2']:.3f}"),
        (r_c, f"reference @ N={cell.ref_budget / 1e6:.0f}M (10× top rung)"),
    )
    for ax, (img, title) in zip(axes[0], panels, strict=True):
        _im(ax, img, lo, hi)
        ax.set_title(title, fontsize=8)
    dens = lambda a: a / max(a.sum(), 1.0)  # noqa: E731
    for ax, img, lab in (
        (axes[1, 0], rel_dev(dens(crop(s0)), dens(r_c)), "S0 − reference"),
        (axes[1, 1], rel_dev(dens(crop(s2)), dens(r_c)), "S2 − reference"),
    ):
        _dev_im(ax, img)
        ax.set_title(f"{lab}\n(density rel. dev., clipped ±100%)", fontsize=8)
    axes[1, 2].axis("off")
    axes[1, 2].text(
        0.0,
        0.98,
        "top row: log tone, shared\nblack/white points (cividis)\n\n"
        "S2's deficit concentrates on\nhigh-density pixels (blue) and\n"
        "its surplus on low-density\nones (red) — the receipted\n"
        f"b(S2) bias signature\n(cell {cell.map_name}/{cell.cap}):\n"
        f"S2/S0 error ratio @4M ×{cell.ratio_s2_s0_top:.1f}",
        va="top",
        fontsize=7.5,
    )
    return fig


def fig3_nanbug(unguarded: np.ndarray, guarded: np.ndarray, nb: Nanbug) -> Figure:
    """F3 — the NaN failure mode: sparse (buggy) vs corrected render."""
    lo, hi = tone_log(guarded)
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.6), layout="constrained")
    ug, gd = nb.variants["unguarded"], nb.variants["guarded"]
    for ax, img, v in (
        (axes[0], unguarded, ug),
        (axes[1], guarded, gd),
    ):
        _im(ax, img, lo, hi)
        ax.set_title(
            f"{v.predicate}: r2 > 4 {('| isnan(r2)') if v.predicate == 'guarded' else 'only'}\n"
            f"{v.n_classified:,} escapers / {v.n_samples:,} draws "
            f"({100 * v.escape_fraction:.1f}%)",
            fontsize=8,
        )
    fig.suptitle(
        "missing NaN guard silently deletes "
        f"{100 * nb.dropped_fraction:.1f}% of quadratic-family escapers "
        "(same seeds, same kernels)",
        fontsize=9.5,
    )
    return fig


def fig4_gallery(gallery: Gallery, images: dict[str, np.ndarray]) -> Figure:
    """F4 — grammar gallery: one row per family + symmetry table."""
    fig = Figure(figsize=(10.0, 8.6))
    gs = fig.add_gridspec(3, 5, height_ratios=[1, 1, 1.15], hspace=0.28, wspace=0.06)
    fams = ("power", "fold", "mutation")
    fam_title = {
        "power": "power family\nz → zⁿ + c",
        "fold": "fold family\n(|·|)Re zⁿ, g(2xy)",
        "mutation": "mutation family\nf(x²) − y, g(2xy)",
    }
    for r, fam in enumerate(fams):
        row = [m for m in gallery.maps if m.family == fam]
        for c, m in enumerate(row[:4]):
            ax = fig.add_subplot(gs[r, c])
            ax.imshow(images[m.name])
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(f"{m.name}   ρ={m.sym:.2f}", fontsize=8.5, pad=3)
            if c == 0:
                ax.set_ylabel(fam_title[fam], fontsize=8.5)
        for c in range(len(row), 4):
            fig.add_subplot(gs[r, c]).axis("off")
    tax = fig.add_subplot(gs[2, :])
    tax.axis("off")
    cols = ["map", "family", "real·imag ops", "exit", "ρ mirror", "predict"]
    rows = [
        [
            m.name,
            m.family,
            (f"{m.real}·{m.imag}" if m.real else f"z^{m.power}"),
            m.exit_direction.split()[0],
            f"{m.sym:.2f}",
            "equivariant" if m.equivariant else "breaks law",
        ]
        for m in gallery.maps
    ]
    tbl = tax.table(
        cellText=rows,
        colLabels=cols,
        cellLoc="center",
        loc="center",
        bbox=Bbox.from_bounds(0.0, 0.0, 1.0, 0.98),
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7)
    for (i, _j), cell in tbl.get_celld().items():
        cell.set_edgecolor("0.6")
        if i == 0 or i % 2 == 0:
            cell.set_facecolor("0.94" if i == 0 else "0.985")
    fig.suptitle(
        f"grammar gallery — {len(gallery.maps)} maps, "
        f"{gallery.samples_per_channel:,} samples/channel; "
        "ρ = top/bottom mirror correlation of tone-mapped density "
        "(repo QC metric)",
        fontsize=9.5,
    )
    return fig


def fig5_grammar(grammar: Grammar, gallery: Gallery) -> Figure:
    """F5 — schematic: grammar families, operator slots, exit directions."""
    fig = Figure(figsize=(10.0, 4.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1.0], wspace=0.18)
    left = fig.add_subplot(gs[0])
    left.set_xlim(0, 10)
    left.set_ylim(0, 10)
    left.axis("off")
    fams = ("power", "fold", "mutation")
    top = 9.6
    for fam in fams:
        info = grammar.families[fam]
        left.add_patch(
            FancyBboxPatch(
                (0.3, top - 2.75),
                9.2,
                2.75,
                boxstyle="round,pad=0.12",
                facecolor="0.96",
                edgecolor="0.35",
            )
        )
        left.text(0.7, top - 0.4, fam, fontsize=11, weight="bold", va="top")
        power_note = (
            "   (n ∈ " + ",".join(str(p) for p in info["powers"]) + ")"
            if info.get("powers")
            else ""
        )
        left.text(0.7, top - 1.05, info["formula"] + power_note, fontsize=9, va="top")
        line = top - 1.65
        if info.get("real_ops"):
            left.text(
                0.7,
                line,
                "real ops f:  " + ", ".join(info["real_ops"]),
                fontsize=6.8,
                va="top",
            )
            line -= 0.5
        if info.get("imag_ops"):
            left.text(
                0.7,
                line,
                "imag ops g:  " + ", ".join(info["imag_ops"]),
                fontsize=6.8,
                va="top",
            )
        top -= 3.1
    left.set_title("parameter-space grammar (brot_build.py)", fontsize=10)

    dirs = ("radial", "vertical", "horizontal")
    dlab = {
        "radial": ("|z| bailout", "all directions"),
        "vertical": ("|y| bailout", "vertical exit only"),
        "horizontal": ("|x| bailout", "horizontal exit only"),
    }
    right = fig.add_subplot(gs[1])
    right.set_xlim(-1.6, 1.6)
    right.set_ylim(-1.95, 1.5)
    right.axis("off")
    right.set_title("escape predicates → exit directions", fontsize=10)
    yy = 1.35
    for d in dirs:
        preds = [p for p in grammar.predicates if p.direction == d]
        nm = ", ".join(p.name for p in preds)
        n_maps = sum(len(p.maps) for p in preds)
        right.add_patch(
            FancyBboxPatch(
                (-1.55, yy - 1.0),
                3.1,
                1.0,
                boxstyle="round,pad=0.08",
                facecolor="0.96",
                edgecolor="0.35",
            )
        )
        right.text(-1.45, yy - 0.2, f"{dlab[d][0]} — {nm}", fontsize=8.5, va="top")
        right.text(-1.45, yy - 0.5, dlab[d][1], fontsize=7, va="top")
        right.text(
            -1.45,
            yy - 0.78,
            f"{n_maps} production maps",
            fontsize=7,
            va="top",
            color="0.35",
        )
        cx, cy = 1.18, yy - 0.5
        right.add_patch(
            Rectangle(
                (cx - 0.26, cy - 0.26), 0.52, 0.52, facecolor="none", edgecolor="0.25"
            )
        )
        arrows: list[tuple[float, float]] = (
            [
                (0, 0.42),
                (0, -0.42),
                (0.42, 0),
                (-0.42, 0),
                (0.3, 0.3),
                (-0.3, 0.3),
                (0.3, -0.3),
                (-0.3, -0.3),
            ]
            if d == "radial"
            else [(0, 0.42), (0, -0.42)]
            if d == "vertical"
            else [(0.42, 0), (-0.42, 0)]
        )
        for dx, dy in arrows:
            right.annotate(
                "",
                xy=(cx + dx, cy + dy),
                xytext=(cx + 0.8 * dx, cy + 0.8 * dy),
                arrowprops=dict(arrowstyle="-|>", color="#0072B2", linewidth=1.1),
            )
        yy -= 1.1
    fig.text(
        0.5,
        0.015,
        "cross-tab (gallery maps): "
        + " · ".join(
            f"{m.family}/{m.name}→{m.exit_direction.split()[0]}"
            for m in gallery.maps[:6]
        )
        + " · …",
        ha="center",
        fontsize=6.5,
        color="0.3",
    )
    return fig


# -------------------------------------------------------------------- outline


def outline_text(
    cells: dict[tuple[str, int], Cell], nb: Nanbug, gallery: Gallery
) -> str:
    slopes0 = [cells[(m, c)].slopes["S0"] for m in MAPS for c in CAPS]
    slopes2 = [cells[(m, c)].slopes["S2"] for m in MAPS for c in CAPS]
    mc = cells[("mandel", 1500)]
    sym_eq = [m.sym for m in gallery.maps if m.equivariant]
    sym_ne = [m.sym for m in gallery.maps if not m.equivariant]
    return f"""# OUTLINE — Whitesides figure plan (final order)

Regenerate everything with one command:
`python scripts/paper_figures.py` (from the brot-farm repo; receipts only).

| # | file | claim (one sentence) |
|---|------|----------------------|
| 1 | fig5_grammar | A single parameter-space grammar — three families (power, fold, mutation) composed from six real operators, five imaginary operators and powers 2–5 — generates every map in the farm, and each map's escape predicate turns it into a radial, vertical or horizontal exit test. |
| 2 | fig4_gallery | Measured mirror-symmetry correlation separates the {len(gallery.maps)} gallery maps exactly as the conjugation-equivariance law predicts: all {len(sym_eq)} equivariant step rules measure ρ = {min(sym_eq):.2f}–{max(sym_eq):.2f} while all {len(sym_ne)} law-breakers (even-in-y fold operators, and every −y mutation) sit lower at ρ = {min(sym_ne):.2f}–{max(sym_ne):.2f}. |
| 3 | fig3_nanbug | One missing NaN guard in the chunked escape predicate silently deletes {100 * nb.dropped_fraction:.1f}% of quadratic-family escapers (measured at cap 1500, chunk 32; same seeds both panels) while the render still looks plausible — classifier correctness is not visually detectable. |
| 4 | fig1_convergence | S0 (uniform) and S1 (boundary importance) converge at the Monte-Carlo N^−1/2 rate (fitted log-log slopes {min(slopes0):.2f}…{max(slopes0):.2f} and {min(cells[(m, c)].slopes["S1"] for m in MAPS for c in CAPS):.2f}…{max(cells[(m, c)].slopes["S1"] for m in MAPS for c in CAPS):.2f} across the nine map×cap cells) while S2 (Metropolis seed mutation) stalls at {min(slopes2):.2f}…{max(slopes2):.2f} with a receipted bias of up to 38% on top-decile pixels. |
| 5 | fig2_equal_budget | At equal 1M budget on the same crop of the mandel cap-1500 cell, S2 is visibly biased and splotchy against the 40M reference (mean ROI relative error {next(r.mean_rel_err for r in mc.rungs["S2"] if r.budget == 1_000_000):.2f} vs S0's {next(r.mean_rel_err for r in mc.rungs["S0"] if r.budget == 1_000_000):.2f}) because SNIS 1/r reweighting cannot restore regions its chains under-visit. |

Paper order runs system → artifact space → correctness → estimation quality →
visual proof; file stems keep their F-numbers (F5=fig5_grammar … F2=fig2_equal_budget).
"""


# ------------------------------------------------------------------------ cli


def build_all(paper_root: Path) -> dict[str, list[Path]]:
    """Parse every receipt and build the full figure set + OUTLINE.md."""
    results = paper_root / "experiments" / "results"
    data = paper_root / "experiments" / "data"
    outdir = paper_root / "figures"
    cells = load_cells(results)
    nb = load_nanbug(results / "fig3_nanbug.json")
    gallery = load_gallery(results / "fig4_gallery.json")
    grammar = load_grammar(results / "grammar_facts.json")
    written: dict[str, list[Path]] = {}
    written["F1"] = write_figure(fig1_convergence(cells), outdir, "fig1_convergence")
    cell = cells[("mandel", 1500)]
    budget = 1_000_000
    written["F2"] = write_figure(
        fig2_equal_budget(
            load_hist(data / f"hist_mandel_1500_S0_{budget}_study.npz"),
            load_hist(data / f"hist_mandel_1500_S2_{budget}_study.npz"),
            load_hist(data / "ref_mandel_1500.npz", key="raw"),
            cell,
            budget,
        ),
        outdir,
        "fig2_equal_budget",
    )
    written["F3"] = write_figure(
        fig3_nanbug(
            load_hist(data / "fig3_nanbug_unguarded.npz"),
            load_hist(data / "fig3_nanbug_guarded.npz"),
            nb,
        ),
        outdir,
        "fig3_nanbug",
    )
    images = {
        m.name: load_rgb(data / f"fig4_gallery_{m.name}.npz") for m in gallery.maps
    }
    written["F4"] = write_figure(fig4_gallery(gallery, images), outdir, "fig4_gallery")
    written["F5"] = write_figure(fig5_grammar(grammar, gallery), outdir, "fig5_grammar")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "OUTLINE.md").write_text(
        outline_text(cells, nb, gallery), encoding="utf-8"
    )
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paper-root", type=Path, default=DEFAULT_PAPER_ROOT)
    ap.add_argument("--only", help="comma list of figure ids (F1..F5) to rebuild")
    args = ap.parse_args(argv)
    if args.only:
        wanted = {t.strip().upper() for t in args.only.split(",") if t.strip()}
    else:
        wanted = {"F1", "F2", "F3", "F4", "F5"}
    written = build_all(args.paper_root)
    for key in sorted(wanted):
        for p in written[key]:
            print(f"{key} -> {p}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

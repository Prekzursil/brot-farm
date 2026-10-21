// Brot Farm playground — everything computed live in your browser.
// Vanilla JS, no dependencies. Mirrors the Python renderer's semantics
// (two-phase classification fused per-sample; percentile-anchored log tone map).
"use strict";

/* ------------------------------------------------------------------ maps */
// step(x, y, cx, cy) -> [x', y']; gone(x, y) -> escape predicate.
const M = Math;
const MAPS = {
	mandel: {
		label: "z² + c",
		win: [-2.25, 1.15, -1.7, 1.7],
		step: (x, y, cx, cy) => [x * x - y * y + cx, 2 * x * y + cy],
		gone: (x, y) => x * x + y * y > 4,
	},
	z3: {
		label: "z³ + c",
		win: [-1.6, 1.6, -1.6, 1.6],
		step: (x, y, cx, cy) => [
			x ** 3 - 3 * x * y * y + cx,
			3 * x * x * y - y ** 3 + cy,
		],
		gone: (x, y) => x * x + y * y > 4,
	},
	z4: {
		label: "z⁴ + c",
		win: [-1.45, 1.45, -1.45, 1.45],
		step: (x, y, cx, cy) => [
			x ** 4 - 6 * x * x * y * y + y ** 4 + cx,
			4 * x * y * (x * x - y * y) + cy,
		],
		gone: (x, y) => x * x + y * y > 4,
	},
	z5: {
		label: "z⁵ + c",
		win: [-1.35, 1.35, -1.35, 1.35],
		step: (x, y, cx, cy) => [
			x ** 5 - 10 * x ** 3 * y * y + 5 * x * y ** 4 + cx,
			5 * x ** 4 * y - 10 * x * x * y ** 3 + y ** 5 + cy,
		],
		gone: (x, y) => x * x + y * y > 4,
	},
	ship: {
		label: "Burning Ship",
		win: [-2.2, 1.2, -1.8, 1.8],
		step: (x, y, cx, cy) => [x * x - y * y + cx, M.abs(2 * x * y) + cy],
		gone: (x, y) => x * x + y * y > 4,
	},
	tricorn: {
		label: "Tricorn z̄² + c",
		win: [-2.1, 2.1, -1.8, 1.8],
		step: (x, y, cx, cy) => [x * x - y * y + cx, -2 * x * y + cy],
		gone: (x, y) => x * x + y * y > 4,
	},
	celtic: {
		label: "Celtic",
		win: [-2.2, 1.0, -1.6, 1.6],
		step: (x, y, cx, cy) => [M.abs(x * x - y * y) + cx, 2 * x * y + cy],
		gone: (x, y) => x * x + y * y > 4,
	},
	buffalo: {
		label: "Buffalo",
		win: [-2.2, 1.0, -1.9, 1.9],
		step: (x, y, cx, cy) => [M.abs(x * x - y * y) + cx, M.abs(2 * x * y) + cy],
		gone: (x, y) => x * x + y * y > 4,
	},
	sinz: {
		label: "sin z + c",
		win: [-3.5, 3.5, -1.8, 1.8],
		step: (x, y, cx, cy) => [
			M.sin(x) * M.cosh(y) + cx,
			M.cos(x) * M.sinh(y) + cy,
		],
		gone: (x, y) => !(isFinite(x) && isFinite(y)) || x * x + y * y > 1e6,
	},
	cosz: {
		label: "cos z + c",
		win: [-4, 4, -2.2, 2.2],
		step: (x, y, cx, cy) => [
			M.cos(x) * M.cosh(y) + cx,
			-M.sin(x) * M.sinh(y) + cy,
		],
		gone: (x, y) => !(isFinite(x) && isFinite(y)) || x * x + y * y > 1e6,
	},
	cosmut: {
		label: "cos(x²) − y mutation",
		win: [-3, 3, -3, 3],
		step: (x, y, cx, cy) => [M.cos(x * x) - y + cx, 2 * x * y + cy],
		gone: (x, y) => M.abs(y) > 100 || !isFinite(x + y),
	},
	cosfull: {
		label: "cos(x²−y²) mutation",
		win: [-2.5, 2.5, -5, 5],
		step: (x, y, cx, cy) => [M.cos(x * x - y * y) + cx, 2 * x * y + cy],
		gone: (x, y) => M.abs(y) > 100 || !isFinite(x + y),
	},
	cosy: {
		label: "y′ = cos 2xy mutation",
		win: [-2.5, 2.5, -2.5, 2.5],
		step: (x, y, cx, cy) => [x * x - y * y + cx, M.cos(2 * x * y) + cy],
		gone: (x, y) => M.abs(x) > 100 || !isFinite(x + y),
	},
	tanmut: {
		label: "tan mutation",
		win: [-2, 2.4, -2.4, 2],
		step: (x, y, cx, cy) => [M.tan(x * x) - y + cx, 2 * x * y + cy],
		gone: (x, y) => M.abs(y) > 100 || !isFinite(x + y),
	},
	sinhmut: {
		label: "sinh mutation",
		win: [-2, 2.2, -1.8, 1.3],
		step: (x, y, cx, cy) => [M.sinh(x * x) - y + cx, 2 * x * y + cy],
		gone: (x, y) => M.abs(y) > 100 || !isFinite(x + y),
	},
	expmut: {
		label: "exp mutation",
		win: [-2, 2, -2, 2],
		step: (x, y, cx, cy) => [M.exp(x * x) - y + cx, 2 * x * y + cy],
		gone: (x, y) => M.abs(y) > 100 || !isFinite(x + y),
	},
};
// gallery deep-links remap to playground-capable maps (anti/julia handled in the mini-renderer)
const ALIASES = { anti: "mandel", nebula: "mandel", julia: "mandel" };
const qs = new URLSearchParams(location.search);
let initialMap = qs.get("map") || "mandel";

/* ------------------------------------------------- formula sandbox compile */
function compileFormula(fxSrc, fySrc) {
	const names = Object.getOwnPropertyNames(Math).filter(
		(k) => typeof Math[k] === "function",
	);
	const wrap = (src) =>
		new Function(
			"x",
			"y",
			"cx",
			"cy",
			...names,
			`"use strict"; return (${src});`,
		);
	const fx = wrap(fxSrc),
		fy = wrap(fySrc);
	const vals = names.map((k) => Math[k]);
	const test = (x, y) => {
		const a = fx(x, y, 0, 0, ...vals),
			b = fy(x, y, 0, 0, ...vals);
		return Number.isFinite(a) && Number.isFinite(b);
	};
	if (!test(0.3, 0.2) || !test(-1.2, 0.7))
		throw new Error("formula does not evaluate cleanly");
	return {
		step: (x, y, cx, cy) => [
			fx(x, y, cx, cy, ...vals),
			fy(x, y, cx, cy, ...vals),
		],
		gone: (x, y) =>
			!isFinite(x + y) ||
			x * x + y * y > 1e10 ||
			Math.abs(x) + Math.abs(y) > 1e5,
	};
}

/* ------------------------------------------------------------ shared utils */
function fillSelect(sel, extra) {
	for (const [k, v] of Object.entries(MAPS)) {
		const o = document.createElement("option");
		o.value = k;
		o.textContent = v.label + (extra && extra[k] ? ` (${extra[k]})` : "");
		sel.appendChild(o);
	}
}
function currentMap(sel) {
	return MAPS[sel.value] || MAPS.mandel;
}

/* =========================================================== ORBIT THEATER */
(function () {
	const cv = document.getElementById("ot-canvas");
	if (!cv) return;
	const ctx = cv.getContext("2d");
	const mapSel = document.getElementById("ot-map");
	const hud = document.getElementById("ot-hud");
	fillSelect(mapSel, {});
	mapSel.value =
		ALIASES[initialMap] || (MAPS[initialMap] ? initialMap : "mandel");

	let custom = null; // compiled custom {step, gone, win}
	const active = () => custom || currentMap(mapSel);
	const W = cv.width,
		H = cv.height;
	let c = [-0.1, 0.65];
	let trail = []; // [x0, y0, x1, y1, age]
	let head = [0, 0];
	let nIter = 0,
		escaped = false;
	let playing = true;
	let bg = null; // prisoner-country layer

	function win() {
		return active().win || currentMap(mapSel).win;
	}
	function toPx(x, y) {
		const [x0, x1, y0, y1] = win();
		return [((x - x0) / (x1 - x0)) * W, ((y1 - y) / (y1 - y0)) * H];
	}
	function toWorld(px, py) {
		const [x0, x1, y0, y1] = win();
		return [x0 + (px / W) * (x1 - x0), y1 - (py / H) * (y1 - y0)];
	}

	function buildBG() {
		const m = active();
		const off = document.createElement("canvas");
		off.width = W;
		off.height = H;
		const octx = off.getContext("2d");
		const cell = 8;
		for (let py = 0; py < H; py += cell) {
			for (let px = 0; px < W; px += cell) {
				const [cx, cy] = toWorld(px + cell / 2, py + cell / 2);
				let x = cx,
					y = cy,
					k = 0;
				for (; k < 60; k++) {
					[x, y] = m.step(x, y, cx, cy);
					if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) break;
				}
				if (k >= 60) {
					octx.fillStyle = "rgba(111,195,223,0.16)";
					octx.fillRect(px, py, cell, cell);
				} else if (k > 15) {
					octx.fillStyle = `rgba(232,160,76,${0.03 + (k / 60) * 0.13})`;
					octx.fillRect(px, py, cell, cell);
				}
			}
		}
		bg = off;
	}

	function reset() {
		head = [c[0], c[1]];
		nIter = 0;
		escaped = false;
		trail = [];
		hudUpdate();
	}

	function stepOnce(count) {
		const m = active();
		for (let i = 0; i < count && !escaped; i++) {
			const [nx, ny] = m.step(head[0], head[1], c[0], c[1]);
			trail.push([head[0], head[1], nx, ny, 0]);
			head = [nx, ny];
			nIter++;
			if (!isFinite(nx) || !isFinite(ny) || m.gone(nx, ny)) escaped = true;
			if (nIter > 20000) escaped = true;
		}
	}

	function hudUpdate() {
		const r = M.hypot(head[0], head[1]);
		hud.innerHTML =
			`map <b>${custom ? "custom formula" : currentMap(mapSel).label}</b><br>` +
			`c = <b>${c[0].toFixed(4)} ${c[1] < 0 ? "−" : "+"} ${M.abs(c[1]).toFixed(4)}i</b><br>` +
			`n = <b>${nIter}</b> · z = ${head[0].toFixed(3)} ${head[1] < 0 ? "−" : "+"} ${M.abs(head[1]).toFixed(3)}i · |z| = ${r.toFixed(3)}<br>` +
			(escaped
				? `<b style="color:#d96a6a">escaped after ${nIter} iterations</b>`
				: nIter === 0
					? "press play or step"
					: "orbit continues…");
	}

	// ------------------------------------------------------------- rain mode
	const film = document.createElement("canvas");
	film.width = W;
	film.height = H;
	const fctx = film.getContext("2d");
	let rain = null;
	function startRain(x, y, spread = 0.25) {
		const [x0, x1, y0, y1] = win();
		rain = Array.from({ length: 1800 }, () => {
			const cx = M.max(x0, M.min(x1, x + (Math.random() * 2 - 1) * spread));
			const cy = M.max(y0, M.min(y1, y + (Math.random() * 2 - 1) * spread));
			return { c: [cx, cy], z: [cx, cy], alive: true };
		});
	}
	function rainFrame() {
		if (!rain) return;
		const m = active();
		fctx.globalCompositeOperation = "lighter";
		fctx.lineWidth = 0.7;
		fctx.strokeStyle = "rgba(232,160,76,0.055)";
		let live = 0;
		for (const p of rain) {
			if (!p.alive) continue;
			live++;
			for (let s = 0; s < 2; s++) {
				const [nx, ny] = m.step(p.z[0], p.z[1], p.c[0], p.c[1]);
				const a = toPx(p.z[0], p.z[1]),
					b = toPx(nx, ny);
				fctx.beginPath();
				fctx.moveTo(a[0], a[1]);
				fctx.lineTo(b[0], b[1]);
				fctx.stroke();
				p.z = [nx, ny];
				if (!isFinite(nx) || !isFinite(ny) || m.gone(nx, ny)) {
					p.alive = false;
					break;
				}
			}
		}
		fctx.globalCompositeOperation = "source-over";
		if (live === 0) rain = null;
	}
	const rainBtn = document.getElementById("ot-rain");
	let rainOn = false;
	rainBtn.addEventListener("click", () => {
		rainOn = !rainOn;
		rainBtn.textContent = rainOn ? "☔ stop rain" : "☔ start rain";
		rainBtn.setAttribute("aria-pressed", rainOn);
		if (rainOn) startRain(c[0], c[1], 0.35);
	});
	document
		.getElementById("ot-rain-clear")
		.addEventListener("click", () => fctx.clearRect(0, 0, W, H));
	cv.addEventListener("click", (e) => {
		if (rainOn) {
			const r = cv.getBoundingClientRect();
			const w = toWorld(
				((e.clientX - r.left) / r.width) * W,
				((e.clientY - r.top) / r.height) * H,
			);
			startRain(w[0], w[1], 0.15);
		}
	});

	// explorer -> theater c-pick
	document.addEventListener("brot:pick-c", (e) => {
		const [x0, x1, y0, y1] = win();
		c = [
			M.max(x0, M.min(x1, e.detail.c[0])),
			M.max(y0, M.min(y1, e.detail.c[1])),
		];
		reset();
		hud.insertAdjacentHTML(
			"beforeend",
			`<b style="color:#6fc3df">· c received from explorer</b>`,
		);
	});

	// ------------------------------------------------------------- main loop
	const trailLen = document.getElementById("ot-trail");
	const speed = document.getElementById("ot-speed");
	function frame() {
		if (playing && !escaped) stepOnce(+speed.value);
		rainFrame();
		const maxAge = +trailLen.value;
		for (const s of trail) s[4]++;
		while (trail.length && trail[0][4] > maxAge) trail.shift();

		ctx.clearRect(0, 0, W, H);
		if (bg) ctx.drawImage(bg, 0, 0);
		ctx.drawImage(film, 0, 0);
		ctx.lineWidth = 1.8;
		for (const [x0, y0, x1, y1, age] of trail) {
			const a = M.max(0, 1 - age / maxAge);
			ctx.strokeStyle = `rgba(232,160,76,${0.25 + 0.65 * a})`;
			const p0 = toPx(x0, y0),
				p1 = toPx(x1, y1);
			ctx.beginPath();
			ctx.moveTo(p0[0], p0[1]);
			ctx.lineTo(p1[0], p1[1]);
			ctx.stroke();
		}
		if (!escaped) {
			const p = toPx(head[0], head[1]);
			ctx.fillStyle = "#fff";
			ctx.beginPath();
			ctx.arc(p[0], p[1], 3.4, 0, 7);
			ctx.fill();
			ctx.strokeStyle = "rgba(255,255,255,0.35)";
			ctx.beginPath();
			ctx.arc(p[0], p[1], 8 + 3 * M.sin(performance.now() / 200), 0, 7);
			ctx.stroke();
		}
		const cp = toPx(c[0], c[1]);
		ctx.fillStyle = "#6fc3df";
		ctx.beginPath();
		ctx.arc(cp[0], cp[1], 4.2, 0, 7);
		ctx.fill();
		ctx.font = "12px Cascadia Code, Consolas, monospace";
		ctx.fillStyle = "#6fc3df";
		ctx.fillText("c", cp[0] + 7, cp[1] - 6);
		hudUpdate();
		requestAnimationFrame(frame);
	}

	// interaction: drag to move c
	let dragging = false;
	const setFromEvent = (e) => {
		const r = cv.getBoundingClientRect();
		const w = toWorld(
			((e.clientX - r.left) / r.width) * W,
			((e.clientY - r.top) / r.height) * H,
		);
		const [x0, x1, y0, y1] = win();
		c = [M.max(x0, M.min(x1, w[0])), M.max(y0, M.min(y1, w[1]))];
		reset();
	};
	cv.addEventListener("pointerdown", (e) => {
		dragging = true;
		cv.setPointerCapture(e.pointerId);
		setFromEvent(e);
	});
	cv.addEventListener("pointermove", (e) => dragging && setFromEvent(e));
	cv.addEventListener("pointerup", () => (dragging = false));

	document.getElementById("ot-play").addEventListener("click", (e) => {
		playing = !playing;
		e.target.textContent = playing ? "⏸ pause" : "▶ play";
	});
	document
		.getElementById("ot-step")
		.addEventListener("click", () => stepOnce(1));
	document.getElementById("ot-reset").addEventListener("click", reset);
	mapSel.addEventListener("change", () => {
		custom = null;
		buildBG();
		reset();
	});
	document.getElementById("ot-apply").addEventListener("click", () => {
		try {
			const m = compileFormula(
				document.getElementById("ot-fx").value,
				document.getElementById("ot-fy").value,
			);
			let best = null;
			for (const w of [
				[-2.5, 2.5, -2.5, 2.5],
				[-1.5, 1.5, -1.5, 1.5],
				[-4, 4, -4, 4],
				[-1, 1, -1, 1],
			]) {
				let surv = 0;
				const N = 3000;
				for (let i = 0; i < N; i++) {
					const cx = w[0] + Math.random() * (w[1] - w[0]);
					const cy = w[2] + Math.random() * (w[3] - w[2]);
					let x = cx,
						y = cy,
						k = 0;
					for (; k < 40; k++) {
						[x, y] = m.step(x, y, cx, cy);
						if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) break;
					}
					if (k >= 40) surv++;
				}
				const frac = surv / N;
				if (frac > 0.05 && frac < 0.95) {
					best = w;
					break;
				}
				if (!best && frac >= 0.95) best = w;
			}
			custom = { ...m, win: best || [-3, 3, -3, 3] };
			buildBG();
			reset();
			hud.insertAdjacentHTML(
				"afterbegin",
				`<b style="color:#6fc3df">formula applied</b> · window auto-scouted<br>`,
			);
		} catch (err) {
			hud.insertAdjacentHTML(
				"afterbegin",
				`<b style="color:#d96a6a">formula error:</b> ${err.message}<br>`,
			);
		}
	});

	buildBG();
	reset();
	frame();
})();

/* ======================================================== MINI BUDDHA LAB */
(function () {
	const cv = document.getElementById("mb-canvas");
	if (!cv) return;
	const N = cv.width; // square
	const ctx = cv.getContext("2d");
	const mapSel = document.getElementById("mb-map");
	fillSelect(mapSel, { mandel: "anti/julia/nebula via presets below" });

	const JULIA_C = [-0.7, 0.27];
	let mode = "escape"; // "escape" | "anti" | "julia"
	if (initialMap === "anti") mode = "anti";
	if (initialMap === "julia") mode = "julia";
	if (initialMap === "nebula") document.getElementById("mb-cap").value = 400;

	let hist = new Float64Array(N * N);
	let stats = { done: 0, escaped: 0, plotted: 0 };
	let playing = true;
	let t0 = performance.now();
	let anchors = { lo: 0, hi: 1 };
	const img = ctx.createImageData(N, N);

	function win() {
		return currentMap(mapSel).win;
	}

	function anchorsRefresh() {
		const sample = [];
		for (let i = 0; i < hist.length; i += 13) {
			const v = hist[i];
			if (v > 0) sample.push(Math.log(1 + v));
		}
		if (sample.length < 50) {
			anchors = { lo: 0, hi: Math.log(1 + Math.max(1, stats.maxBin || 1)) };
			return;
		}
		sample.sort((a, b) => a - b);
		anchors = {
			lo: sample[Math.floor(sample.length * 0.3)],
			hi:
				sample[Math.floor(sample.length * 0.999)] || sample[sample.length - 1],
		};
	}

	const capEl = document.getElementById("mb-cap"),
		rateEl = document.getElementById("mb-rate"),
		gEl = document.getElementById("mb-gamma");

	function addSamples(count) {
		const m = currentMap(mapSel);
		const [x0, x1, y0, y1] = win();
		const cap = +capEl.value;
		for (let s = 0; s < count; s++) {
			let cx, cy, sx, sy;
			if (mode === "julia") {
				cx = JULIA_C[0];
				cy = JULIA_C[1];
				sx = x0 + Math.random() * (x1 - x0);
				sy = y0 + Math.random() * (y1 - y0);
			} else {
				cx = x0 + Math.random() * (x1 - x0);
				cy = y0 + Math.random() * (y1 - y0);
				sx = cx;
				sy = cy;
			}
			// phase 1: classify
			let x = sx,
				y = sy,
				esc = false,
				k = 0;
			for (; k < cap; k++) {
				[x, y] = m.step(x, y, cx, cy);
				if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) {
					esc = true;
					break;
				}
			}
			stats.done++;
			const want = mode === "anti" ? !esc : esc;
			if (!want) continue;
			stats.escaped++;
			// phase 2: replay and plot (julia starts from z1 = z0² + c; c-maps from z1 = c)
			const sxw = N / (x1 - x0),
				syw = N / (y1 - y0);
			let px0 = sx,
				py0 = sy;
			if (mode === "julia") {
				[px0, py0] = m.step(sx, sy, cx, cy);
			}
			x = px0;
			y = py0;
			const steps = mode === "anti" ? cap : k;
			for (let j = 0; j <= steps; j++) {
				const col = ((x - x0) * sxw) | 0,
					row = ((y1 - y) * syw) | 0;
				if (col >= 0 && col < N && row >= 0 && row < N) {
					hist[row * N + col] += 1;
					stats.plotted++;
				}
				[x, y] = m.step(x, y, cx, cy);
				if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) break;
			}
		}
	}

	let frameCount = 0;
	function render() {
		if (playing) addSamples(+rateEl.value);
		if (++frameCount % 20 === 0) anchorsRefresh();
		const { lo, hi } = anchors;
		const gamma = +gEl.value;
		const d = img.data;
		let maxBin = 0;
		for (let i = 0, p = 0; i < hist.length; i++, p += 4) {
			const h = hist[i];
			if (h > maxBin) maxBin = h;
			let v = (Math.log(1 + h) - lo) / M.max(hi - lo, 1e-9);
			v = v < 0 ? 0 : v > 1 ? 1 : v;
			v = v ** gamma;
			d[p] = 255 * M.min(1, v * 1.15);
			d[p + 1] = 255 * M.min(1, v * 1.05);
			d[p + 2] = 255 * v * 0.9;
			d[p + 3] = 255;
		}
		stats.maxBin = maxBin;
		ctx.putImageData(img, 0, 0);
		const secs = (performance.now() - t0) / 1000;
		document.getElementById("mb-hud").innerHTML =
			`mode <b>${mode === "anti" ? "antibuddhabrot (prisoner orbits)" : mode === "julia" ? `julia-brot · c = ${JULIA_C[0]} + ${JULIA_C[1]}i` : "buddhabrot (escaping orbits)"}</b> on <b>${currentMap(mapSel).label}</b><br>` +
			`samples <b>${stats.done.toLocaleString()}</b> · kept ${stats.escaped.toLocaleString()} · plotted ${(stats.plotted / 1e6).toFixed(1)}M points · hottest bin ${maxBin.toLocaleString()}<br>` +
			`${secs.toFixed(0)}s exposure · ${(stats.done / secs / 1000).toFixed(0)}k samples/s`;
		document.getElementById("mb-cap-v").textContent = capEl.value;
		document.getElementById("mb-rate-v").textContent = rateEl.value;
		requestAnimationFrame(render);
	}

	document.getElementById("mb-play").addEventListener("click", (e) => {
		playing = !playing;
		e.target.textContent = playing ? "⏸ pause" : "▶ play";
	});
	document.getElementById("mb-reset").addEventListener("click", () => {
		hist = new Float64Array(N * N);
		stats = { done: 0, escaped: 0, plotted: 0 };
		t0 = performance.now();
	});
	document.getElementById("mb-save").addEventListener("click", () => {
		const a = document.createElement("a");
		a.download = `brot-${mapSel.value}-${Date.now()}.png`;
		a.href = cv.toDataURL("image/png");
		a.click();
	});
	// preset buttons injected for the gallery deep-links
	const presetRow = document.createElement("div");
	presetRow.className = "controls";
	presetRow.innerHTML = `
    <span style="color:var(--muted);font-size:12.5px">presets:</span>
    <button class="btn" data-mode="escape">buddhabrot</button>
    <button class="btn" data-mode="anti">antibuddhabrot</button>
    <button class="btn" data-mode="julia">julia-brot</button>`;
	cv.closest(".panel").insertBefore(presetRow, cv.closest(".grid2"));
	presetRow.addEventListener("click", (e) => {
		const b = e.target.closest("button[data-mode]");
		if (!b) return;
		mode = b.dataset.mode;
		hist = new Float64Array(N * N);
		stats = { done: 0, escaped: 0, plotted: 0 };
		t0 = performance.now();
	});
	anchorsRefresh();
	render();
})();

/* ================================================================ EXPLORER */
(function () {
	const cv = document.getElementById("ex-canvas");
	if (!cv) return;
	const ctx = cv.getContext("2d");
	const W = cv.width,
		H = cv.height;
	const hud = document.getElementById("ex-hud");
	const view = { cx: -0.6, cy: 0, scale: 3.4 };
	const palette = [];
	for (let i = 0; i < 256; i++) {
		const t = i / 255;
		palette.push([9 + 246 * t ** 1.6, 9 + 230 * t ** 2.2, 14 + 200 * t ** 3]);
	}
	function render(res) {
		const step = res;
		const img = ctx.createImageData(Math.ceil(W / step), Math.ceil(H / step));
		const aspect = W / H;
		const half = view.scale / 2;
		const d = img.data;
		let p = 0;
		for (let py = 0; py < img.height; py++) {
			const cy = view.cy + half - ((py + 0.5) / img.height) * view.scale;
			for (let px = 0; px < img.width; px++, p += 4) {
				const cx =
					view.cx -
					half * aspect +
					((px + 0.5) / img.width) * view.scale * aspect;
				let x = cx,
					y = cy,
					k = 0;
				for (; k < 96; k++) {
					const nx = x * x - y * y + cx,
						ny = 2 * x * y + cy;
					x = nx;
					y = ny;
					if (x * x + y * y > 4) break;
				}
				if (k >= 96) {
					d[p] = 8;
					d[p + 1] = 7;
					d[p + 2] = 12;
				} else {
					const c = palette[Math.min(255, (k * 7) & 255)];
					d[p] = c[0];
					d[p + 1] = c[1];
					d[p + 2] = c[2];
				}
				d[p + 3] = 255;
			}
		}
		ctx.putImageData(img, 0, 0);
		if (step > 1) ctx.drawImage(cv, 0, 0, img.width, img.height, 0, 0, W, H);
		hud.textContent = `center ${view.cx.toFixed(5)} ${view.cy < 0 ? "−" : "+"} ${Math.abs(view.cy).toFixed(5)}i · scale ${view.scale.toPrecision(3)} · zoom ${(3.4 / view.scale).toPrecision(3)}×`;
	}
	let idleTimer = null,
		drag = null,
		moved = false;
	const fullRender = () => render(1);
	const coarseRender = () => render(4);
	function poke() {
		coarseRender();
		clearTimeout(idleTimer);
		idleTimer = setTimeout(fullRender, 220);
	}
	cv.addEventListener(
		"wheel",
		(e) => {
			e.preventDefault();
			const r = cv.getBoundingClientRect();
			const mx = (e.clientX - r.left) / r.width,
				my = (e.clientY - r.top) / r.height;
			const aspect = W / H;
			const wx = view.cx - (view.scale / 2) * aspect + mx * view.scale * aspect;
			const wy = view.cy + view.scale / 2 - my * view.scale;
			const f = e.deltaY > 0 ? 1.15 : 1 / 1.15;
			view.scale = M.min(5, M.max(1e-6, view.scale * f));
			view.cx = wx - (mx - 0.5) * view.scale * aspect;
			view.cy = wy + (my - 0.5) * view.scale;
			poke();
		},
		{ passive: false },
	);
	cv.addEventListener("pointerdown", (e) => {
		drag = { x: e.clientX, y: e.clientY };
		moved = false;
		cv.setPointerCapture(e.pointerId);
	});
	cv.addEventListener("pointermove", (e) => {
		if (!drag) return;
		const dx = e.clientX - drag.x,
			dy = e.clientY - drag.y;
		if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
		const aspect = W / H;
		view.cx -= (dx / cv.getBoundingClientRect().width) * view.scale * aspect;
		view.cy += (dy / cv.getBoundingClientRect().height) * view.scale;
		drag = { x: e.clientX, y: e.clientY };
		poke();
	});
	cv.addEventListener("pointerup", (e) => {
		drag = null;
		if (moved) return;
		// click: send c to the orbit theater
		const r = cv.getBoundingClientRect();
		const mx = (e.clientX - r.left) / r.width,
			my = (e.clientY - r.top) / r.height;
		const aspect = W / H;
		const c = [
			view.cx - (view.scale / 2) * aspect + mx * view.scale * aspect,
			view.cy + view.scale / 2 - my * view.scale,
		];
		document.dispatchEvent(new CustomEvent("brot:pick-c", { detail: { c } }));
		hud.textContent += ` · sent c = ${c[0].toFixed(4)} ${c[1] < 0 ? "−" : "+"} ${Math.abs(c[1]).toFixed(4)}i to the orbit theater ↑`;
	});
	cv.addEventListener("dblclick", () => {
		view.cx = -0.6;
		view.cy = 0;
		view.scale = 3.4;
		fullRender();
	});
	fullRender();
})();

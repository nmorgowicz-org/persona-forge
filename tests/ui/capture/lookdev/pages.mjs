// Look-dev board builders for B-P0 (docs/archive/luminous-instrument/20260923-luminous_instrument_redesign.md).
// Pure helpers: candidate CSS loading, and HTML/in-page renderers for the contact sheets,
// the D9 signal-palette board, and the D7 brand board. The scenarios in
// scenarios/lookdev/ drive the app and call these; nothing here touches frontend/src.
//
// Every board is rendered INTO the running app's document (body replaced) so it inherits the
// app's self-hosted Geist faces -- board text then matches the product's real typography.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(HERE, '..', '..', '..', '..');

export const LOOKS = [
    { id: 'graphite', label: 'L1 Graphite', ref: 'FabFilter-adjacent' },
    { id: 'obsidian', label: 'L2 Obsidian', ref: 'Xfer-adjacent' },
    { id: 'machined', label: 'L3 Machined', ref: 'UAD-adjacent' },
    { id: 'forge', label: 'L4 Forge', ref: 'Option E brand-derived' },
];
export const THEMES = ['violet', 'amber'];

const COMMON_CSS = readFileSync(join(HERE, 'common.css'), 'utf8');

export function lookCss(lookId) {
    // Candidate first, common layer second: common consumes the candidate's --ld-* variables.
    return `${readFileSync(join(HERE, `${lookId}.css`), 'utf8')}\n${COMMON_CSS}`;
}

// Surface colors for the signal board, read from the candidate CSS so the board can never
// drift from what the app shots used.
export function lookSurface(lookId) {
    const css = readFileSync(join(HERE, `${lookId}.css`), 'utf8');
    const pick = (name) => css.match(new RegExp(`--${name}:\\s*([^;]+);`))?.[1]?.trim();
    return { bg: pick('background'), card: pick('card'), border: pick('border'), muted: pick('muted-foreground'), radius: pick('radius') };
}

export function dataUri(path, mime) {
    return `data:${mime};base64,${readFileSync(path).toString('base64')}`;
}

export function repoPath(...parts) {
    return join(REPO_ROOT, ...parts);
}

/** Replace the app document with a 1440x900 board. Removes any injected look CSS first. */
export async function showBoard(page, html) {
    await page.evaluate((markup) => {
        for (const el of document.querySelectorAll('style[data-lookdev]')) el.remove();
        document.documentElement.removeAttribute('data-theme');
        document.body.className = '';
        document.body.style.cssText =
            'margin:0;background:#08080c;color:#e9e7f2;font-family:"Geist Variable",sans-serif;overflow:hidden;';
        document.body.innerHTML = markup;
        window.scrollTo(0, 0);
    }, html);
}

const BOARD_STYLE = `
  #board{width:1440px;height:900px;box-sizing:border-box;padding:18px 22px;display:flex;flex-direction:column;gap:10px}
  .hd{display:flex;align-items:baseline;gap:14px}
  .hd h1{margin:0;font-size:18px;font-weight:600;letter-spacing:-.01em}
  .hd p{margin:0;font-size:12px;color:#9b98ad}
  .lbl{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#a9a5c0}
  .mono{font-family:"Geist Mono Variable",monospace;font-variant-numeric:tabular-nums}
`;

/** 2x2 sheet of the four hero surfaces for one look (violet accent). */
export function lookSheetHtml(look, shots) {
    const cells = shots
        .map(
            (s) => `<figure style="margin:0;display:flex;flex-direction:column;gap:4px">
        <figcaption class="lbl">${s.label}</figcaption>
        <img src="${s.uri}" style="width:688px;height:430px;border-radius:6px;outline:1px solid #ffffff14;object-fit:cover;object-position:top left"/>
      </figure>`,
        )
        .join('');
    return `<style>${BOARD_STYLE}</style><div id="board">
    <div class="hd"><h1>${look.label}</h1><p>${look.ref} · violet accent · real app, candidate tokens injected (no frontend/src edits)</p></div>
    <div style="display:grid;grid-template-columns:688px 688px;gap:10px 20px">${cells}</div></div>`;
}

/**
 * 4 looks x 2 accents on one surface: proves each look survives a non-violet theme. Each cell
 * is a crop of the full shot (controls row + deck band, where accent and signal meet) at ~49%
 * scale, so the comparison is legible instead of a thumbnail wall.
 */
export function accentSheetHtml(surfaceLabel, cells, crop = { top: 440, height: 330 }) {
    const scale = 690 / 1440;
    const cell = (c) => `<figure style="margin:0;display:flex;flex-direction:column;gap:3px">
        <figcaption class="lbl">${c.look.label} · ${c.theme}</figcaption>
        <div style="width:690px;height:${Math.round(crop.height * scale)}px;overflow:hidden;border-radius:5px;outline:1px solid #ffffff14">
          <img src="${c.uri}" style="width:690px;display:block;margin-top:${-Math.round(crop.top * scale)}px"/></div>
      </figure>`;
    const rows = cells.map(cell).join('');
    return `<style>${BOARD_STYLE}</style><div id="board">
    <div class="hd"><h1>Accent check — ${surfaceLabel}</h1><p>Left: violet (default) · Right: amber. Tinted neutrals must not fight a non-violet accent; the CTA follows the accent (D3).</p></div>
    <div style="display:grid;grid-template-columns:690px 690px;gap:8px 16px">${rows}</div></div>`;
}

/** D9 signal board: one row per palette, on the chosen look's surfaces, at near-product size. */
export function signalBoardHtml(look, palettes, meta) {
    const s = look.surface;
    const row = (p) => `<div style="align-self:center;display:flex;flex-direction:column;gap:4px">
        <div class="lbl" style="color:#e9e7f2">${p.label}</div>
        <div style="font-size:11px;color:#9b98ad;line-height:1.35">${p.note}</div></div>
      <div style="background:${s.bg};padding:7px 9px;border-radius:6px">
      <div style="background:${s.card};border:1px solid ${s.border};border-radius:${s.radius};padding:8px 10px;display:flex;flex-direction:column;gap:5px;box-shadow:inset 0 1px 0 #ffffff0d">
        <canvas data-sig="wave" data-pal="${p.id}" width="1180" height="80"></canvas>
        <canvas data-sig="spec" data-pal="${p.id}" width="1180" height="100"></canvas>
        <canvas data-sig="meter" data-pal="${p.id}" width="1180" height="18"></canvas>
        <span data-readout="${p.id}" class="mono" style="font-size:10.5px;color:${s.muted};white-space:nowrap"></span>
      </div></div>`;
    return `<style>${BOARD_STYLE}</style><div id="board">
    <div class="hd"><h1>D9 — Signal palette on ${look.label}</h1><p>${meta}</p></div>
    <div style="display:grid;grid-template-columns:150px 1220px;gap:8px 14px;align-items:stretch">${palettes.map(row).join('')}</div></div>`;
}

/**
 * In-page renderer for the signal board. Passed to page.evaluate, so it must be
 * self-contained. Decodes the real fixture WAV and draws true-scale waveform (peak outline +
 * RMS body), an STFT spectrogram (log frequency 50 Hz-12 kHz), and a dBFS meter with
 * peak-hold at the playhead -- the P2/P3/P4 designs, drawn in each candidate palette.
 */
export async function renderSignalBoard({ wavBase64, playFrac }) {
    const bytes = Uint8Array.from(atob(wavBase64), (c) => c.charCodeAt(0));
    const ac = new OfflineAudioContext(1, 1, 24000);
    const buf = await ac.decodeAudioData(bytes.buffer);
    const x = buf.getChannelData(0);
    const sr = buf.sampleRate;
    const n = x.length;
    const playSample = Math.floor(n * playFrac);

    const lerp = (a, b, t) => a + (b - a) * t;
    const oklchRamp = (stops, t) => {
        let i = 0;
        while (i < stops.length - 2 && t > stops[i + 1][0]) i += 1;
        const [t0, l0, c0, h0] = stops[i];
        const [t1, l1, c1, h1] = stops[i + 1];
        const u = Math.min(1, Math.max(0, (t - t0) / (t1 - t0)));
        return [lerp(l0, l1, u), lerp(c0, c1, u), lerp(h0, h1, u)];
    };
    const BRAND = [[0, 0.74, 0.14, 235], [0.55, 0.65, 0.22, 290], [1, 0.95, 0.04, 295]];
    // S-c hybrid (owner D9): brand blue -> violet body, S-a's hot magenta top end so loud reads
    // by hue as well as lightness, amber playhead (complement of violet; today's
    // WAVEFORM_PLAYHEAD_COLOR). Canonical definition: luminous plan P1 "Signal constants".
    const HYBRID = [[0, 0.72, 0.13, 235], [0.45, 0.64, 0.22, 285], [0.8, 0.7, 0.21, 332], [1, 0.95, 0.04, 330]];
    const rampPal = (stops, playhead, spec) => ({
        played: (t) => {
            const [l, c, h] = oklchRamp(stops, t);
            return `oklch(${l} ${c} ${h} / ${0.6 + t * 0.4})`;
        },
        unplayed: (t) => {
            const [l, c, h] = oklchRamp(stops, t);
            return `oklch(${l - 0.2} ${c * 0.6} ${h} / ${0.32 + t * 0.2})`;
        },
        playhead,
        spec,
    });
    const PAL = {
        a: {
            played: (t) => `hsl(${190 + t * 140} 90% ${58 + t * 14}% / ${0.55 + t * 0.45})`,
            unplayed: (t) => `hsl(${190 + t * 140} 45% ${40 + t * 10}% / ${0.28 + t * 0.22})`,
            playhead: 'hsl(38 95% 62%)',
            spec: ['#05060a', 'hsl(200 70% 16%)', 'hsl(190 90% 45%)', 'hsl(300 85% 58%)', 'hsl(330 95% 90%)'],
        },
        b: rampPal(BRAND, 'oklch(0.96 0.03 295)', ['#07051a', 'oklch(0.28 0.12 280)', 'oklch(0.62 0.16 240)', 'oklch(0.64 0.23 290)', 'oklch(0.97 0.03 295)']),
        c: rampPal(HYBRID, 'hsl(38 95% 62%)', ['#05040f', 'oklch(0.26 0.1 275)', 'oklch(0.58 0.16 245)', 'oklch(0.62 0.23 290)', 'oklch(0.7 0.22 335)', 'oklch(0.97 0.03 330)']),
    };
    // Color intensity follows loudness in dBFS (-48..0), not linear amplitude: speech peaks near
    // -6 dBFS are only 0.5 linear, so a linear map never reaches a palette's hot end.
    const heat = (amp) => Math.min(1, Math.max(0, (20 * Math.log10(Math.max(amp, 1e-6)) + 48) / 48));
    const lut = (stops) => {
        const c = document.createElement('canvas');
        c.width = 256;
        c.height = 1;
        const g = c.getContext('2d');
        const grad = g.createLinearGradient(0, 0, 256, 0);
        stops.forEach((s, i) => grad.addColorStop(i / (stops.length - 1), s));
        g.fillStyle = grad;
        g.fillRect(0, 0, 256, 1);
        return g.getImageData(0, 0, 256, 1).data;
    };

    // STFT once (N=512 Hann, hop 128), magnitudes in dBFS-ish (reference: full-scale sine).
    const N = 512;
    const HOP = 128;
    const frames = Math.max(1, Math.floor((n - N) / HOP) + 1);
    const hann = Float64Array.from({ length: N }, (_, i) => 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (N - 1)));
    const spec = new Float32Array(frames * (N / 2));
    const re = new Float64Array(N);
    const im = new Float64Array(N);
    const bits = Math.log2(N);
    for (let f = 0; f < frames; f += 1) {
        for (let i = 0; i < N; i += 1) {
            let r = 0;
            for (let b = 0; b < bits; b += 1) r |= ((i >> b) & 1) << (bits - 1 - b);
            re[r] = (x[f * HOP + i] ?? 0) * hann[i];
            im[r] = 0;
        }
        for (let size = 2; size <= N; size <<= 1) {
            const half = size >> 1;
            const step = (-2 * Math.PI) / size;
            for (let s = 0; s < N; s += size) {
                for (let k = 0; k < half; k += 1) {
                    const wr = Math.cos(step * k);
                    const wi = Math.sin(step * k);
                    const a = s + k;
                    const b = a + half;
                    const tr = re[b] * wr - im[b] * wi;
                    const ti = re[b] * wi + im[b] * wr;
                    re[b] = re[a] - tr;
                    im[b] = im[a] - ti;
                    re[a] += tr;
                    im[a] += ti;
                }
            }
        }
        for (let k = 0; k < N / 2; k += 1) {
            const mag = Math.hypot(re[k], im[k]) / (N / 4);
            spec[f * (N / 2) + k] = 20 * Math.log10(mag + 1e-9);
        }
    }

    const dbfs = (v) => 20 * Math.log10(Math.max(v, 1e-9));
    let rmsSum = 0;
    const win = Math.floor(sr * 0.05);
    for (let i = Math.max(0, playSample - win); i < playSample; i += 1) rmsSum += x[i] * x[i];
    const rmsDb = dbfs(Math.sqrt(rmsSum / Math.max(1, Math.min(win, playSample))));
    let hold = 0;
    for (let i = Math.max(0, playSample - Math.floor(sr * 1.5)); i < playSample; i += 1) hold = Math.max(hold, Math.abs(x[i]));
    const holdDb = dbfs(hold);
    let filePeak = 0;
    for (let i = 0; i < n; i += 1) filePeak = Math.max(filePeak, Math.abs(x[i]));

    for (const canvas of document.querySelectorAll('canvas[data-sig]')) {
        const pal = PAL[canvas.dataset.pal];
        const g = canvas.getContext('2d');
        const W = canvas.width;
        const H = canvas.height;
        const playX = Math.round(W * playFrac);
        if (canvas.dataset.sig === 'wave') {
            const mid = H / 2;
            const scale = (H / 2) * 0.94; // absolute: 1.0 full scale fills the lane
            for (let c = 0; c < W; c += 1) {
                const a = Math.floor((c / W) * n);
                const b = Math.floor(((c + 1) / W) * n);
                let mn = 0;
                let mx = 0;
                let ss = 0;
                for (let i = a; i < b; i += 1) {
                    mn = Math.min(mn, x[i]);
                    mx = Math.max(mx, x[i]);
                    ss += x[i] * x[i];
                }
                const rms = Math.sqrt(ss / Math.max(1, b - a));
                const t = heat(Math.max(mx, -mn));
                const color = c < playX ? pal.played : pal.unplayed;
                g.fillStyle = color(t * 0.7);
                g.fillRect(c, mid - mx * scale, 1, Math.max(1, (mx - mn) * scale));
                g.fillStyle = color(Math.min(1, heat(rms) * 1.15));
                g.fillRect(c, mid - rms * scale, 1, Math.max(1, rms * 2 * scale));
            }
            g.save();
            g.shadowColor = pal.playhead;
            g.shadowBlur = 8;
            g.fillStyle = pal.playhead;
            g.fillRect(playX, 0, 1.5, H);
            g.restore();
        } else if (canvas.dataset.sig === 'spec') {
            const colors = lut(pal.spec);
            const img = g.createImageData(W, H);
            const fMin = 50;
            const fMax = 12000;
            for (let yy = 0; yy < H; yy += 1) {
                const freq = fMin * (fMax / fMin) ** (1 - yy / (H - 1));
                const bin = Math.min(N / 2 - 1, Math.round((freq / sr) * N));
                for (let c = 0; c < W; c += 1) {
                    const f = Math.min(frames - 1, Math.floor((c / W) * frames));
                    const db = spec[f * (N / 2) + bin];
                    // -72..-12 dB window: speech harmonics land mid/high, the TTS noise floor
                    // (~-60 dB and below) stays near black instead of reading as signal.
                    const t = Math.min(1, Math.max(0, (db + 72) / 60));
                    const li = Math.round(t * 255) * 4;
                    const o = (yy * W + c) * 4;
                    img.data[o] = colors[li];
                    img.data[o + 1] = colors[li + 1];
                    img.data[o + 2] = colors[li + 2];
                    img.data[o + 3] = 255;
                }
            }
            g.putImageData(img, 0, 0);
            g.fillStyle = pal.playhead;
            g.globalAlpha = 0.85;
            g.fillRect(playX, 0, 1.5, H);
        } else {
            const barH = 8;
            const pos = (db) => Math.min(1, Math.max(0, (db + 60) / 60));
            g.fillStyle = '#00000066';
            g.fillRect(0, 0, W, barH);
            const lvl = pos(rmsDb) * W;
            for (let c = 0; c < lvl; c += 1) {
                g.fillStyle = pal.played(c / W);
                g.fillRect(c, 0, 1, barH);
            }
            g.save();
            g.shadowColor = '#ffffff';
            g.shadowBlur = 6;
            g.fillStyle = '#ffffffee';
            g.fillRect(pos(holdDb) * W - 1, 0, 2, barH);
            g.restore();
            g.fillStyle = '#ffffff55';
            g.font = '8px "Geist Mono Variable", monospace';
            for (const tick of [-48, -36, -24, -18, -12, -6, -3, 0]) {
                const tx = pos(tick) * W;
                g.fillRect(Math.min(W - 1, tx), barH, 1, 3);
                g.fillText(String(tick), Math.min(W - 10, Math.max(0, tx - 6)), H - 1);
            }
        }
    }
    const readout = `RMS ${rmsDb.toFixed(1)} · PK-HOLD ${holdDb.toFixed(1)} · FILE PK ${dbfs(filePeak).toFixed(1)} dBFS`;
    for (const el of document.querySelectorAll('[data-readout]')) el.textContent = readout;
    return { duration: n / sr, rmsDb, holdDb, filePeakDb: dbfs(filePeak), frames };
}

/**
 * D7 brand board 1: every mark at every size, dark + light, plus in-product lockups. A mark
 * with `smallUri` is a shipping set: the small variant renders at <= 32 px, as in production.
 */
export function brandMarksHtml(marks) {
    const sizes = [64, 32, 16];
    const at = (m, s) => (s <= 32 && m.smallUri ? m.smallUri : m.uri);
    const tab = (m, bg, fg) => `<div style="display:flex;align-items:center;gap:6px;padding:7px 8px;border-radius:8px 8px 0 0;background:${bg};color:${fg};flex:1;min-width:0">
        <img src="${at(m, 16)}" style="width:16px;height:16px"/><span style="font-size:11px;white-space:nowrap">Persona Forge</span></div>`;
    const col = (m) => `<div style="display:flex;flex-direction:column;gap:10px;padding:12px;border-radius:10px;background:#0e0c1a;outline:1px solid ${m.flag ? '#ff5a6e88' : '#ffffff12'}">
      <div class="lbl" style="color:${m.flag ? '#ff8a98' : '#b9b3dd'}">${m.name}</div>
      <div style="height:170px;display:grid;place-items:center;border-radius:8px;background:radial-gradient(circle at 50% 45%,#1d1545,#0a0816 70%)">
        <img src="${m.uri}" style="width:150px;height:150px"/></div>
      <div style="display:flex;gap:6px">
        <div style="flex:1;display:flex;align-items:center;justify-content:space-around;height:78px;border-radius:6px;background:#07060d">${sizes.map((s) => `<img src="${at(m, s)}" style="width:${s}px;height:${s}px"/>`).join('')}</div>
        <div style="flex:1;display:flex;align-items:center;justify-content:space-around;height:78px;border-radius:6px;background:#f3f1fa">${sizes.map((s) => `<img src="${at(m, s)}" style="width:${s}px;height:${s}px"/>`).join('')}</div>
      </div>
      <div class="lbl" style="font-size:9px">sidebar lockup (actual size)</div>
      <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;background:#141126">
        <div style="width:32px;height:32px;border-radius:10px;display:grid;place-items:center;background:#0b0918;box-shadow:inset 0 1px 0 #ffffff14,0 0 14px #7e14ff44">
          <img src="${at(m, 24)}" style="width:24px;height:24px"/></div>
        <div style="display:flex;flex-direction:column;gap:3px"><span style="font-size:14px;font-weight:600;letter-spacing:-.01em;line-height:1">Persona Forge</span><span style="font-size:11px;color:#a29dbd">Voice Studio</span></div>
      </div>
      <div class="lbl" style="font-size:9px">browser tabs (favicon 16 px) · dark / light chrome</div>
      <div style="display:flex;gap:8px">${tab(m, '#232135', '#e9e7f2')}${tab(m, '#e8e6ef', '#1c1a26')}</div>
    </div>`;
    return `<style>${BOARD_STYLE}</style><div id="board">
    <div class="hd"><h1>D7 — Brand mark</h1><p>Signal Crucible turns many voice fields into one coherent output. The current favicon is the stock Vite scaffold logo and must be replaced (plan audit A11).</p></div>
    <div style="display:grid;grid-template-columns:repeat(${marks.length},minmax(0,1fr));gap:14px">${marks.map(col).join('')}</div></div>`;
}

/** D7 brand board 2: where the hero art lives (splash/README) with each mark in context. */
export function brandContextHtml(marks, heroUri, avatarUri) {
    const splash = (m) => `<figure style="margin:0;display:flex;flex-direction:column;gap:4px">
      <figcaption class="lbl">Startup state · ${m.name}</figcaption>
      <div style="position:relative;width:440px;height:275px;border-radius:10px;overflow:hidden;background:#07061a">
        <img src="${heroUri}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.38;filter:saturate(1.1)"/>
        <div style="position:absolute;inset:0;background:radial-gradient(circle at 50% 42%,transparent 10%,#07061acc 75%)"></div>
        <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px">
          <img src="${m.uri}" style="width:72px;height:72px;filter:drop-shadow(0 0 18px #7e14ff88)"/>
          <div style="font-size:18px;font-weight:600;letter-spacing:-.01em">Persona Forge</div>
          <div style="width:180px;height:4px;border-radius:2px;background:#ffffff1a;overflow:hidden"><div style="width:62%;height:100%;background:linear-gradient(90deg,#47bfff,#9b6bff);box-shadow:0 0 10px #9b6bff"></div></div>
          <div class="mono" style="font-size:11px;color:#b9b3dd">Loading voice model · 62%</div>
        </div></div></figure>`;
    return `<style>${BOARD_STYLE}</style><div id="board">
    <div class="hd"><h1>D7 — Brand in context</h1><p>Hero art appears only where nothing is operated: README/social banner, startup state, empty states. Never behind working controls.</p></div>
    <div style="display:flex;gap:18px;align-items:flex-start">
      <figure style="margin:0;display:flex;flex-direction:column;gap:4px"><figcaption class="lbl">README banner + GitHub social preview (github-social.jpg, 1280×640, &lt;1 MB)</figcaption>
        <img src="${heroUri}" style="width:880px;height:440px;border-radius:10px;object-fit:cover"/></figure>
      <figure style="margin:0;display:flex;flex-direction:column;gap:4px"><figcaption class="lbl">Avatar crop (reference)</figcaption>
        <img src="${avatarUri}" style="width:300px;height:300px;border-radius:10px;object-fit:cover"/></figure>
    </div>
    <div style="display:flex;gap:18px">${marks.filter((m) => !m.flag && m.splash !== false).map(splash).join('')}</div></div>`;
}

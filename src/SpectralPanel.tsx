import { useEffect, useRef, useState } from "react";
import { openGroup, HTTPStore, slice } from "zarr";

import Plotly from "plotly.js";

import { storeUrls, loadMask, REGIONS } from "./zarrSource";

//Physical constants
const H  = 6.626e-34;   // J·s
const C  = 2.998e8;     // m/s
const KB = 1.381e-23;   // J/K

//Original channel indices (0-based) shown on the quicklook maps
const HIGHLIGHT = new Set([12, 24, 30, 32]);
const HATCH = new Set([39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62]);
//Helpers
function planck(lam_um: number, T: number): number {
  const lam_m = lam_um / 1e6;
  return ((2 * H * C * C) / Math.pow(lam_m, 5)) /
    (Math.exp((H * C) / (lam_m * KB * T)) - 1) / 1e6; // → W/m²/sr/μm
}

function linspace(a: number, b: number, n: number): number[] {
  return Array.from({ length: n }, (_, i) => a + (b - a) * (i / (n - 1)));
}

function argmin(arr: ArrayLike<number>): number {
  let idx = 0;
  for (let i = 1; i < arr.length; i++) if (arr[i] < arr[idx]) idx = i;
  return idx;
}

function argmax(arr: ArrayLike<number>): number {
  let idx = 0;
  for (let i = 1; i < arr.length; i++) if (arr[i] > arr[idx]) idx = i;
  return idx;
}

function pick<T>(arr: T[], indices: number[]): T[] {
  return indices.map(i => arr[i]);
}

// Inclusive [start, end] index range of a monotonic coord array whose values
// fall inside [lo, hi]; returns [-1, -1] when nothing matches.
function rangeIndices(coord: ArrayLike<number>, lo: number, hi: number): [number, number] {
  let start = -1, end = -1;
  for (let i = 0; i < coord.length; i++) {
    const v = coord[i];
    if (v >= lo && v <= hi) { if (start < 0) start = i; end = i; }
  }
  return [start, end];
}

//Component
interface Box { latMin: number; latMax: number; lonMin: number; lonMax: number; }

interface Props {
  lat?: number;         // picked point; overrides the box and the region when set
  lon?: number;
  box?: Box | null;     // spatial-averaging box; overrides the region when set
  region?: string;      // map view code ("np", "sp", "gb", "gre"); the default average
  temporal?: boolean;   // annual (12-month) mean when true
  sat?: string;         // "sat1"
  year?: string;        // "2025"
  month?: string;       // "12"
  mode?: string;        // "month" or "season"
  season?: string;      // "DJF", "MAM", "JJA", "SON"
}

export default function SpectralPanel({
  lat, lon, box = null, region = "np", temporal = false,
  sat = "sat1", year = "2025", month = "12", mode = "month", season = "DJF"
}: Props) {
  const plotDiv = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "error" | "ready">("loading");
  const [errMsg, setErrMsg] = useState("");
  const [loadMsg, setLoadMsg] = useState("Loading zarr data…");

  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        const point = lat !== undefined && lon !== undefined ? { lat, lon } : null;
        const reg = REGIONS[region];
        setStatus("loading");
        if (!reg) throw new Error(`Unknown region "${region}"`);
        setLoadMsg(
          temporal ? "Loading annual mean (12 months)…"
                   : point ? "Loading zarr data…"
                   : box ? "Loading spatial mean…" : "Loading regional mean…");

        // Stores to aggregate: 12 months for the annual mean, the season's three
        // months (may cross a year boundary), else the selected month.
        const urls = storeUrls({ sat, year, month, mode, season, temporal });

        // Coordinates + wavelength come from the first store (shared grid).
        const root0 = await openGroup(new HTTPStore(urls[0]), "", "r");
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const ga0 = async (name: string) => ((await root0.getItem(name)) as any).get();
        const [latRaw, lonRaw, wlRaw] = await Promise.all([
          ga0("lat"), ga0("lon"), ga0("wavelength"),
        ]);
        const latData = latRaw.data as Float64Array;
        const lonData = lonRaw.data as Float64Array;
        const wlFull  = Array.from(wlRaw.data as Float32Array);
        const nSpec   = wlFull.length;

        // Resolve the spatial selection: the nearest cell to a picked point, else an
        // index range (box, or the view's region), optionally narrowed by a cell mask.
        const nLat = latData.length, nLon = lonData.length;
        const halfLat = nLat > 1 ? (latData[1] - latData[0]) / 2 : 0;
        let latSel: [number, number] = [0, nLat], lonSel: [number, number] = [0, nLon];
        let latIdx = 0, lonIdx = 0;
        let mask: Uint8Array | null = null;
        if (point) {
          latIdx = argmin(Array.from(latData).map(v => Math.abs(v - point.lat)));
          lonIdx = argmin(Array.from(lonData).map(v => Math.abs(v - point.lon)));
        } else if (box) {
          const [ls, le] = rangeIndices(latData, box.latMin, box.latMax);
          const [os, oe] = rangeIndices(lonData, box.lonMin, box.lonMax);
          if (ls < 0 || os < 0) throw new Error("No grid cells fall inside the entered box.");
          latSel = [ls, le + 1];
          lonSel = [os, oe + 1];
        } else if (reg.mask) {
          // Read only the bounding box of the mask's cells
          mask = await loadMask(reg.mask, nLat, nLon);
          let [l0, l1, o0, o1] = [nLat, -1, nLon, -1];
          for (let i = 0; i < nLat; i++) for (let j = 0; j < nLon; j++) {
            if (mask[i * nLon + j]) {
              l0 = Math.min(l0, i); l1 = Math.max(l1, i);
              o0 = Math.min(o0, j); o1 = Math.max(o1, j);
            }
          }
          if (l1 < 0) throw new Error(`The ${reg.label} mask is empty.`);
          latSel = [l0, l1 + 1];
          lonSel = [o0, o1 + 1];
        } else {
          // Match the region on cell centres (lat holds lower edges)
          const [ls, le] = rangeIndices(latData, (reg.latMin ?? -90) - halfLat, (reg.latMax ?? 90) - halfLat);
          if (ls < 0) throw new Error(`No grid cells fall inside ${reg.label}.`);
          latSel = [ls, le + 1];
        }

        // Area weight of each selected cell: cos(lat) at the cell centre, zero
        // outside the mask. A single point needs no weighting.
        const weight = (i: number, j: number) => {
          if (point) return 1;
          const li = latSel[0] + i, lj = lonSel[0] + j;
          if (mask && !mask[li * nLon + lj]) return 0;
          return Math.cos((latData[li] + halfLat) * Math.PI / 180);
        };

        // NaN-aware, area-weighted accumulation over space and time (months) per spectral channel.
        const radSum = new Float64Array(nSpec), radCnt = new Float64Array(nSpec);
        const stdSum = new Float64Array(nSpec), stdCnt = new Float64Array(nSpec);

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const accumulate = async (root: any, name: string, sum: Float64Array, cnt: Float64Array) => {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const arr = (await root.getItem(name)) as any;
          const nd  = arr.shape.length as number;
          // Axis names from metadata; fall back to "[time,] lat, lon, spectral" order.
          let names: string[] = (await arr.attrs.asObject())["_ARRAY_DIMENSIONS"] ?? [];
          if (names.length !== nd) {
            names = new Array(nd).fill("");
            names[nd - 1] = "spectral"; names[nd - 2] = "lon"; names[nd - 3] = "lat";
            if (nd >= 4) names[0] = "time";
          }
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const selection: any[] = [];
          const kept: number[] = [];
          let specAxis = -1, latAxis = -1, lonAxis = -1;
          for (let i = 0; i < nd; i++) {
            const nm = names[i];
            if (nm === "lat" && point)      { selection.push(latIdx); }
            else if (nm === "lon" && point) { selection.push(lonIdx); }
            else if (nm === "lat")          { selection.push(slice(latSel[0], latSel[1])); kept.push(i); latAxis = i; }
            else if (nm === "lon")          { selection.push(slice(lonSel[0], lonSel[1])); kept.push(i); lonAxis = i; }
            else                            { selection.push(null); kept.push(i); if (nm === "spectral") specAxis = i; }
          }
          if (specAxis < 0) specAxis = nd - 1; // spectral is the trailing axis by convention

          const raw   = await arr.getRaw(selection);
          const data  = raw.data as ArrayLike<number>;
          const shape = raw.shape as number[];
          // Index along an original axis of the element at flat position p of the
          // C-order result (always 0 for an axis that was indexed away).
          const axisIndex = (axis: number) => {
            const pos = kept.indexOf(axis);
            if (pos < 0) return () => 0;
            let stride = 1;
            for (let i = pos + 1; i < shape.length; i++) stride *= shape[i];
            const n = shape[pos];
            return (p: number) => Math.floor(p / stride) % n;
          };
          const specAt = axisIndex(specAxis), latAt = axisIndex(latAxis), lonAt = axisIndex(lonAxis);
          for (let p = 0; p < data.length; p++) {
            const v = data[p];
            if (!Number.isFinite(v)) continue;
            const w = weight(latAt(p), lonAt(p));
            if (w > 0) { const c = specAt(p); sum[c] += w * v; cnt[c] += w; }
          }
        };

        for (let s = 0; s < urls.length; s++) {
          const root = s === 0 ? root0 : await openGroup(new HTTPStore(urls[s]), "", "r");
          await Promise.all([
            accumulate(root, "spectral_radiance",     radSum, radCnt),
            accumulate(root, "spectral_radiance_std", stdSum, stdCnt),
          ]);
        }

        const radFull = Array.from(radSum, (s, i) => radCnt[i] > 0 ? s / radCnt[i] : NaN);
        const stdFull = Array.from(stdSum, (s, i) => stdCnt[i] > 0 ? s / stdCnt[i] : NaN);

        if (!alive) return;

        // Filter to finite-valued channels (removes sentinel NaNs)
        const valid: number[] = [];
        wlFull.forEach((wl, i) => {
          if (isFinite(wl) && isFinite(radFull[i])) valid.push(i);
        });
        const wl_v  = valid.map(i => wlFull[i]);
        const rad_v = valid.map(i => radFull[i]);
        const std_v = valid.map(i => stdFull[i]);
        const isHL  = valid.map(i => HIGHLIGHT.has(i));
        const isHatch = valid.map(i => HATCH.has(i));
       
        // Variable bar widths (min neighbour gap × 0.95)
        const widths = wl_v.map((wl, i) => {
          const fwd = i < wl_v.length - 1 ? wl_v[i + 1] - wl : Infinity;
          const bwd = i > 0               ? wl - wl_v[i - 1] : Infinity;
          return Math.min(fwd === Infinity ? bwd : fwd,
                          bwd === Infinity ? fwd : bwd) * 0.95;
        });

        // Peak channel → brightness temperature (inverted Planck)
        const peakFi  = argmax(rad_v);
        const peak_lam = wl_v[peakFi];
        const peak_rad = rad_v[peakFi];
        const lam_m    = peak_lam / 1e6;
        const rad_si   = peak_rad * 1e6;                   // W/m²/sr/μm → W/m²/sr/m
        const T_peak   = (H * C / KB / lam_m) /
                         Math.log(2 * H * C * C / (Math.pow(lam_m, 5) * rad_si) + 1);

        // Planck reference curve (500 points)
        const wl_dense  = linspace(Math.min(...wl_v), Math.max(...wl_v), 500);
        const planck_v  = wl_dense.map(w => planck(w, T_peak));

        // Custom hover data: [original_channel_idx, wavelength]
        const cd = valid.map((origIdx, i) => [origIdx, wl_v[i]]);

        const idx_hl = wl_v.map((_, i) => i).filter(i =>  isHL[i]);
        const idx_ot = wl_v.map((_, i) => i).filter(i => !isHL[i] && !isHatch[i]);
        const idx_hatch = wl_v.map((_, i) => i).filter(i => isHatch[i]);

        const barHov = "Channel %{customdata[0]:.0f}<br>λ = %{x:.3f} μm<br>" +
                       "L = %{y:.3f} W/m²/sr/μm<extra></extra>";
        const stdHov = "<b>Channel %{customdata[0]:.0f}</b><br>" +
                       "λ = %{customdata[1]:.4f} μm<br>Std: %{y:.4e}<extra></extra>";

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const traces: any[] = [
          // ── Row 1: highlighted radiance bars ──
          {
            type: "bar",
            x: pick(wl_v, idx_hl), y: pick(rad_v, idx_hl), width: pick(widths, idx_hl),
            marker: { color: "crimson" },
            name: "Channels available on maps",
            customdata: pick(cd, idx_hl),
            hovertemplate: barHov,
            xaxis: "x", yaxis: "y",
          },
          // ── Row 1: other radiance bars ──
          {
            type: "bar",
            x: pick(wl_v, idx_ot), y: pick(rad_v, idx_ot), width: pick(widths, idx_ot),
            marker: { color: "darkorange" },
            name: "Well-calibrated channels",
            customdata: pick(cd, idx_ot),
            hovertemplate: barHov,
            xaxis: "x", yaxis: "y",
          },
          // ── Row 1: hatched bars (not on maps) ──
          { 
            type: "bar",
            x: pick(wl_v, idx_hatch), y: pick(rad_v, idx_hatch), width: pick(widths, idx_hatch),
            marker: { color: "lightgray", pattern: { shape: "x", size: 10, fgcolor: "gray", bgcolor: "lightgray" } },
            name: "Less-calibrated channels",
            customdata: pick(cd, idx_hatch),
            hovertemplate: barHov,
            xaxis: "x", yaxis: "y",
          },
          // ── Row 1: Planck curve (secondary y) ──
          {
            type: "scatter", mode: "lines",
            x: wl_dense, y: planck_v,
            line: { color: "tomato", dash: "dash", width: 2 },
            name: `Planck B(λ, ${T_peak.toFixed(1)} K)`,
            hovertemplate: "λ = %{x:.3f} μm<br>B = %{y:.3f}<extra></extra>",
            xaxis: "x", yaxis: "y",
          },
          // ── Row 1: peak marker ──
          {
            type: "scatter", mode: "markers",
            x: [peak_lam], y: [peak_rad],
            marker: {
              color: "crimson", symbol: "star", size: 12,
              line: { color: "black", width: 1 },
            },
            name: `Peak: ${peak_lam.toFixed(2)} μm, T_b = ${T_peak.toFixed(1)} K`,
            xaxis: "x", yaxis: "y",
          },
          // ── Row 2: non-highlighted std bars ──
          {
            type: "bar",
            x: pick(wl_v, idx_ot), y: pick(std_v, idx_ot), width: pick(widths, idx_ot),
            marker: { color: "deepskyblue" },
            customdata: pick(cd, idx_ot),
            hovertemplate: stdHov,
            showlegend: false,
            xaxis: "x2", yaxis: "y3",
          },
          // ── Row 2: highlighted std bars ──
          {
            type: "bar",
            x: pick(wl_v, idx_hl), y: pick(std_v, idx_hl), width: pick(widths, idx_hl),
            marker: { color: "crimson" },
            customdata: pick(cd, idx_hl),
            hovertemplate: stdHov,
            showlegend: false,
            xaxis: "x2", yaxis: "y3",
          },
                    {
            type: "bar",
            x: pick(wl_v, idx_hatch), y: pick(std_v, idx_hatch), width: pick(widths, idx_hatch),
            marker: { color: "lightgray", pattern: { shape: "x", size: 10, fgcolor: "gray", bgcolor: "lightgray" } },
            customdata: pick(cd, idx_hatch),
            hovertemplate: stdHov,
            showlegend: false,
            xaxis: "x2", yaxis: "y3",
          },
        ];

        const fmtLat = (v: number) => v >= 0 ? `${Math.abs(v).toFixed(1)}°N` : `${Math.abs(v).toFixed(1)}°S`;
        const fmtLon = (v: number) => v >= 0 ? `${Math.abs(v).toFixed(1)}°E` : `${Math.abs(v).toFixed(1)}°W`;
        const isRegion = !point && !box;
        const locStr = point
          ? `at ${fmtLat(latData[latIdx])}, ${fmtLon(lonData[lonIdx])}`
          : box
            ? `in box ${fmtLat(box.latMin)}–${fmtLat(box.latMax)}, ${fmtLon(box.lonMin)}–${fmtLon(box.lonMax)}`
            : `(${reg.label})`;
        // A regional average leads with "Mean", which absorbs the time-mean wording
        let period = "";
        if (temporal) period = "annual";
        else if (mode !== "month") period = season;
        let titlePrefix = "";
        if (isRegion) titlePrefix = period ? `Mean ${period} ` : "Mean ";
        else if (period) titlePrefix = `${period[0].toUpperCase()}${period.slice(1)}-mean `;

        const layout: Partial<Plotly.Layout> = {
          bargap: 0,
          margin: { l: 65, r: 70, t: 40, b: 65 },
          title: {
            text: `${titlePrefix}Spectral Radiance & Planck curve fit ${locStr}`,
            x: 0.06,
            font: { size: 18, weight: "bold" },
          },
          legend: {
            orientation: "v", x: 1, y: 0.81,
            xanchor: "right", yanchor: "bottom",
          },
          // Row 1 x axis (tick labels hidden — shared range with row 2)
          xaxis: { domain: [0, 1], showticklabels: false, anchor: "y"},
          // Row 1 main y (spectral radiance)
          yaxis: { title: { text: "Spectral radiance (W/m²/sr/μm)" }, domain: [0.4, 1.0], anchor: "x" },
          // Row 1 secondary y (Planck reference)
          yaxis2: {
            title: { text: `Planck B(λ,${T_peak.toFixed(1)}K) (W/m²/sr/μm)`, font: { color: "tomato" } },
            overlaying: "y", domain: [0.4, 1.0], side: "right", showgrid: false,
          },
          // Row 2 x axis (wavelength label)
          xaxis2: { domain: [0, 1], title: { text: "Wavelength (μm)" }, anchor: "y3" },
          // Row 2 y (standard deviation)
          yaxis3: { title: { text: "Std dev of Spectral Radiance"}, domain: [0, 0.33], anchor: "x2" },
          autosize: true,
          paper_bgcolor: "#ffffff",
          plot_bgcolor:  "#ffffff",
        };

        if (plotDiv.current && alive) {
          await Plotly.newPlot(plotDiv.current, traces, layout, { responsive: true });
          setStatus("ready");
        }
      } catch (e) {
        if (alive) {
          setErrMsg(e instanceof Error ? e.message : String(e));
          setStatus("error");
        }
      }
    })();

    return () => {
      alive = false;
      if (plotDiv.current) Plotly.purge(plotDiv.current);
    };
  }, [lat, lon, box, region, temporal, sat, year, month, mode, season]);

  // Plotly's `responsive` option only listens for window resizes, so the plot
  // keeps whatever width it was drawn at when the flex row around it changes.
  // That is exactly what happens when the middle quicklook goes from
  // unavailable to available: this panel gives that width back, and without a
  // redraw the chart would stay at its full-width size and be clipped.
  useEffect(() => {
    const div = plotDiv.current;
    if (!div || typeof ResizeObserver === "undefined") return;
    let frame = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        // Plotly.Plots.resize throws on a div it has not drawn into yet.
        if (plotDiv.current && (plotDiv.current as { _fullLayout?: unknown })._fullLayout) {
          Plotly.Plots.resize(plotDiv.current);
        }
      });
    });
    ro.observe(div);
    return () => { cancelAnimationFrame(frame); ro.disconnect(); };
  }, []);

  return (
    <div
      style={{
        flex: "1 1 0",
        alignSelf: "stretch",
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        position: "relative",
      }}
    >
      
      {status !== "ready" && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.8rem",
            color: status === "error" ? "#c71616" : "#888",
            padding: "1rem",
            textAlign: "center",
          }}
        >
          {status === "loading" ? loadMsg : `Error: ${errMsg}`}
        </div>
      )}
      <div ref={plotDiv} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}

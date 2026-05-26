import { useEffect, useRef, useState } from "react";
import { openGroup, HTTPStore } from "zarr";

import Plotly from "plotly.js";

// ── Physical constants ──────────────────────────────────────────────────────
const H  = 6.626e-34;   // J·s
const C  = 2.998e8;     // m/s
const KB = 1.381e-23;   // J/K

// Original channel indices (0-based) shown on the quicklook maps
const HIGHLIGHT = new Set([12, 24, 30, 32]);

// ── Helpers ─────────────────────────────────────────────────────────────────
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

// ── Component ────────────────────────────────────────────────────────────────
interface Props {
  lat?: number;
  lon?: number;
}

export default function SpectralPanel({ lat = 65, lon = -130 }: Props) {
  const plotDiv = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "error" | "ready">("loading");
  const [errMsg, setErrMsg] = useState("");
  
  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        setStatus("loading");

        const store = new HTTPStore(`${window.location.origin}/data/trial.zarr`);
        const root  = await openGroup(store, "", "r");
        
        // Helper: get a named array's data
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const ga = async (name: string, sel: any = null) =>
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          ((await root.getItem(name)) as any).get(sel);

        // 1D coordinate arrays (each is a single chunk → 1 fetch)
        const [latRaw, lonRaw, wlRaw] = await Promise.all([
          ga("lat"), ga("lon"), ga("wavelength"),
        ]);
        const latData = latRaw.data as Float64Array;
        const lonData = lonRaw.data as Float64Array;
        const wlFull  = Array.from(wlRaw.data as Float32Array);

        // Nearest grid indices
        const latIdx = argmin(Array.from(latData).map(v => Math.abs(v - lat)));
        const lonIdx = argmin(Array.from(lonData).map(v => Math.abs(v - lon)));

        // Spectral slice at that point (4 chunk fetches each)
        const [radRaw, stdRaw] = await Promise.all([
          ga("spectral_radiance",     [latIdx, lonIdx, null]),
          ga("spectral_radiance_std", [latIdx, lonIdx, null]),
        ]);
        const radFull = Array.from(radRaw.data as Float32Array);
        const stdFull = Array.from(stdRaw.data as Float32Array);

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
        const idx_ot = wl_v.map((_, i) => i).filter(i => !isHL[i]);

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
            name: "Other channels",
            customdata: pick(cd, idx_ot),
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
            xaxis: "x", yaxis: "y2",
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
        ];

        const actualLat = latData[latIdx];
        const actualLon = lonData[lonIdx];
        const latStr = actualLat >= 0
          ? `${actualLat.toFixed(2)}°N`
          : `${Math.abs(actualLat).toFixed(2)}°S`;
        const lonStr = actualLon >= 0
          ? `${actualLon.toFixed(2)}°E`
          : `${Math.abs(actualLon).toFixed(2)}°W`;

        const layout: Partial<Plotly.Layout> = {
          bargap: 0,
          margin: { l: 65, r: 70, t: 45, b: 65 },
          title: {
            text: `Spectral Radiance & Planck curve fit at ${latStr}, ${lonStr}`,
            x: 0.06,
            font: { size: 18, weight: "bold" },
          },
          legend: {
            orientation: "v", x: 0.94, y: 0.88,
            xanchor: "right", yanchor: "bottom",
          },
          // Row 1 x axis (tick labels hidden — shared range with row 2)
          xaxis: { domain: [0, 1], showticklabels: false, anchor: "y"},
          // Row 1 main y (spectral radiance)
          yaxis: { title: { text: "Spectral radiance (W/m²/sr/μm)" }, domain: [0.4, 1.0], anchor: "x" },
          // Row 1 secondary y (Planck reference)
          yaxis2: {
            title: { text: `Planck B(λ,${T_peak.toFixed(1)}K) (W/m²/sr/μm)`, font: { color: "tomato" } },
            overlaying: "y", side: "right", showgrid: false,
          },
          // Row 2 x axis (wavelength label)
          xaxis2: { domain: [0, 1], title: { text: "Wavelength (μm)" }, anchor: "y3" },
          // Row 2 y (standard deviation)
          yaxis3: { title: { text: "Std of Spectral Radiance"}, domain: [0, 0.33], anchor: "x2" },
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
  }, [lat, lon]);

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
          {status === "loading" ? "Loading zarr data…" : `Error: ${errMsg}`}
        </div>
      )}
      <div ref={plotDiv} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}

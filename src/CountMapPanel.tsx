import { useEffect, useRef, useState } from "react";

import Plotly from "plotly.js";

import { loadCountGrid } from "./zarrSource";

// The overlay sits on top of the quicklook; the counts are drawn semi-transparent
// so both read at once.
const OVERLAY_OPACITY = 0.75;

// Sphere cartopy projects the quicklooks onto, in metres, and its degree factor.
const R = 6378137;
const DEG = Math.PI / 180;

// Longest raster axis, in cells. The counts are resampled into the projection's
// own coordinates, so this caps how many heatmap bricks one overlay can hold.
const RASTER_MAX = 400;

// ── Views ────────────────────────────────────────────────────────────────────
// Every quicklook view is drawn in its own projection, so the overlay has to be
// too or the counts land on the wrong part of the map.
//
// Both tables below were measured off the figures random/processor.py and
// random/zarr_views.py actually save, so they follow whatever those do:
//
//   limits  the axes limits in projected metres — cartopy's set_extent turns the
//           view's lon/lat window into these, and it does not simply take the
//           window's projected bounding box, so they are read from the axes
//           rather than recomputed here.
//   box     where the map axes sit inside the saved image, as a fraction of it.
//           matplotlib's tight bbox leaves room for the title, colorbar and
//           gridline labels, and how much differs per view; these came from
//           ax.get_window_extent() against the tight bbox of each figure.
//
// A view whose extent changes in those modules needs both rows redone.
interface ViewSpec {
  kind: "ortho" | "robinson";
  lat0: number;                                 // projection centre (orthographic)
  lon0: number;
  cap: [number, number] | null;                 // lat window of a circular-boundary view
  limits: [number, number, number, number];     // x0, x1, y0, y1 in metres
  box: { left: number; top: number; width: number; height: number };
}

const POLE_BOX = { left: 0.019, top: 0.092, width: 0.808, height: 0.873 };

const VIEWS: Record<string, ViewSpec> = {
  // The pole views are cut to a circular boundary (processor's `set_boundary`),
  // so `cap` drops what falls outside the 60°-pole cap the circle stands for.
  np: {
    kind: "ortho", lat0: 90, lon0: 0, cap: [60, 90],
    limits: [-3186511, 3166075, -3178842, 3189068], box: POLE_BOX,
  },
  sp: {
    kind: "ortho", lat0: -90, lon0: 0, cap: [-90, -60],
    limits: [-3186511, 3166075, -3189068, 3178842], box: POLE_BOX,
  },
  gr: {
    kind: "ortho", lat0: 72, lon0: -40, cap: null,
    limits: [-1251229, 1251229, -1654960, 1466652],
    box: { left: 0.069, top: 0.080, width: 0.735, height: 0.881 },
  },
  gb: {
    kind: "robinson", lat0: 0, lon0: 0, cap: null,
    limits: [-17005833, 17005833, -8625155, 8625155],
    box: { left: 0.048, top: 0.107, width: 0.940, height: 0.665 },
  },
};

const viewSpec = (proj: string): ViewSpec => VIEWS[proj] ?? VIEWS.np;

// ── Projections ──────────────────────────────────────────────────────────────
// Robinson's tabulated meridian length (X) and parallel spacing (Y) at 5° steps
// — the table PROJ interpolates for cartopy's ccrs.Robinson. Interpolating it
// linearly stays within 0.2% of cartopy, well under one screen pixel here.
const ROB_X = [1.0000, 0.9986, 0.9954, 0.9900, 0.9822, 0.9730, 0.9600, 0.9427, 0.9216,
               0.8962, 0.8679, 0.8350, 0.7986, 0.7597, 0.7186, 0.6732, 0.6213, 0.5722, 0.5322];
const ROB_Y = [0.0000, 0.0620, 0.1240, 0.1860, 0.2480, 0.3100, 0.3720, 0.4340, 0.4958,
               0.5571, 0.6176, 0.6769, 0.7346, 0.7903, 0.8435, 0.8936, 0.9394, 0.9761, 1.0000];
const ROB_KX = 0.8487;
const ROB_KY = 1.3523;

function robTable(absLat: number): [number, number] {
  const t = Math.min(Math.max(absLat, 0), 90) / 5;
  const i = Math.min(Math.floor(t), ROB_X.length - 2);
  const u = t - i;
  return [
    ROB_X[i] + (ROB_X[i + 1] - ROB_X[i]) * u,
    ROB_Y[i] + (ROB_Y[i + 1] - ROB_Y[i]) * u,
  ];
}

// Invert the (monotonic) Y column: parallel spacing → latitude.
function robLat(y: number): number {
  const a = Math.min(Math.abs(y), 1);
  let i = 0;
  while (i < ROB_Y.length - 2 && ROB_Y[i + 1] < a) i++;
  const span = ROB_Y[i + 1] - ROB_Y[i];
  const lat = 5 * (i + (span > 0 ? (a - ROB_Y[i]) / span : 0));
  return y < 0 ? -lat : lat;
}

// projected metres → [lat, lon]; null off the map.
function inverse(v: ViewSpec, x: number, y: number): [number, number] | null {
  if (v.kind === "robinson") {
    const Y = y / (ROB_KY * R);
    if (Math.abs(Y) > 1) return null;
    const lat = robLat(Y);
    const [X] = robTable(Math.abs(lat));
    const lon = x / (ROB_KX * R * X * DEG);
    return Math.abs(lon) > 180 ? null : [lat, lon];
  }
  const rho = Math.hypot(x, y);
  if (rho > R) return null;
  if (rho === 0) return [v.lat0, v.lon0];
  const c = Math.asin(rho / R);
  const sc = Math.sin(c), cc = Math.cos(c);
  const p0 = v.lat0 * DEG;
  const lat = Math.asin(Math.min(1, Math.max(-1, cc * Math.sin(p0) + (y * sc * Math.cos(p0)) / rho))) / DEG;
  const lon = v.lon0 + Math.atan2(x * sc, rho * cc * Math.cos(p0) - y * sc * Math.sin(p0)) / DEG;
  return [lat, ((lon + 180) % 360 + 360) % 360 - 180];
}

interface Props {
  sat: string;       // "sat1"
  year: string;      // "2025"
  month: string;     // "12"
  mode: string;      // "month" | "season"
  season: string;    // "DJF" | "MAM" | "JJA" | "SON"
  channel: string;   // "12" | "24" | "30" | "32"
  proj: string;      // "np" | "gb" | "sp" | "gr"
  timeLabel: string; // "December 2025"
}

// Colorbar ticks at powers of ten, since the color axis carries log10(count).
function logTicks(loMax: number): { tickmode: "array"; tickvals: number[]; ticktext: string[] } {
  const tickvals: number[] = [];
  const ticktext: string[] = [];
  for (let k = 0; k <= Math.ceil(loMax); k++) {
    tickvals.push(k);
    ticktext.push(k < 4 ? String(10 ** k) : `1e${k}`);
  }
  return { tickmode: "array", tickvals, ticktext };
}

// Horizontal colorbar inset into the bottom right of the map, so it hides as
// little of the quicklook showing through the transparent overlay as possible.
function colorBar(maxLog: number) {
  return {
    orientation: "h" as const, x: 1.05, xanchor: "right" as const,
    y: 0.96, yanchor: "bottom" as const, thickness: 9, len: 0.34,
    tickfont: { size: 9 }, outlinewidth: 0, 
    bgcolor: "rgba(255,255,255,0.72)", ...logTicks(maxLog),
  };
}

export default function CountMapPanel({
  sat, year, month, mode, season, channel, proj, timeLabel,
}: Props) {
  const plotDiv = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "error" | "unavailable" | "ready">("loading");
  const [errMsg, setErrMsg] = useState("");

  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        setStatus("loading");

        // Missing stores (sat2, or months outside the archived range) are skipped;
        // only a complete miss is reported as "unavailable".
        const grid = await loadCountGrid({ sat, year, month, mode, season, channel });

        if (!alive) return;
        if (!grid) { setStatus("unavailable"); return; }
        if (!plotDiv.current) return;
        const { lat: latData, lon: lonData, counts } = grid;

        // The stored coordinates are cell lower edges (-90..89, -180..179).
        const nLat = latData.length, nLon = lonData.length;
        const latStep = nLat > 1 ? latData[1] - latData[0] : 1;
        const lonStep = nLon > 1 ? lonData[1] - lonData[0] : 1;
        const lat0Edge = latData[0], lon0Edge = lonData[0];

        const view = viewSpec(proj);
        const [x0, x1, y0, y1] = view.limits;
        const cap = view.cap;

        // Resample the counts into the projection's own coordinates: one heatmap
        // is far cheaper than a marker per observed cell, and it lines the counts
        // up with the map underneath whatever the projection does to the grid.
        const xSpan = x1 - x0, ySpan = y1 - y0;
        // One raster cell per screen pixel, up to the cap, and square in
        // projected metres so the bricks stay square on the map.
        const longPx = Math.max(plotDiv.current.clientWidth, plotDiv.current.clientHeight) || 600;
        const long = Math.min(RASTER_MAX, Math.max(120, Math.round(longPx)));
        const short = Math.max(60, Math.round(long * Math.min(xSpan, ySpan) / Math.max(xSpan, ySpan)));
        const nx = xSpan >= ySpan ? long : short;
        const ny = xSpan >= ySpan ? short : long;
        const dx = xSpan / nx, dy = ySpan / ny;

        const xs = Array.from({ length: nx }, (_, j) => x0 + (j + 0.5) * dx);
        const ys = Array.from({ length: ny }, (_, i) => y0 + (i + 0.5) * dy);
        const z: (number | null)[][] = [];
        const cd: (number[] | null)[][] = [];
        let maxLog = 0;
        let filled = 0;

        for (let i = 0; i < ny; i++) {
          const zRow: (number | null)[] = new Array(nx);
          const cdRow: (number[] | null)[] = new Array(nx);
          for (let j = 0; j < nx; j++) {
            zRow[j] = null; cdRow[j] = null;
            const ll = inverse(view, xs[j], ys[i]);
            if (!ll) continue;
            const [lat, lon] = ll;
            if (cap && (lat < cap[0] || lat > cap[1])) continue;

            const li = Math.floor((lat - lat0Edge) / latStep);
            let lj = Math.floor((lon - lon0Edge) / lonStep);
            lj = ((lj % nLon) + nLon) % nLon;
            if (li < 0 || li >= nLat) continue;

            const c = counts[li * nLon + lj];
            if (!(c > 0)) continue;
            const lg = Math.log10(c);
            if (lg > maxLog) maxLog = lg;
            zRow[j] = lg;
            // Cell centres, so the readout names the grid cell the count is for.
            cdRow[j] = [lat0Edge + (li + 0.5) * latStep, lon0Edge + (lj + 0.5) * lonStep, c];
            filled++;
          }
          z.push(zRow); cd.push(cdRow);
        }

        // Nothing observed inside this view — a real answer for, say, the south
        // pole in a month the satellite only flew the north.
        if (!filled) { setStatus("unavailable"); return; }

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const traces: any[] = [{
          type: "heatmap",
          x: xs, y: ys, z,
          customdata: cd,
          zsmooth: false,
          hoverongaps: false,
          colorscale: "Viridis",
          opacity: OVERLAY_OPACITY,
          hovertemplate:
            "%{customdata[0]:.1f}°, %{customdata[1]:.1f}°<br>%{customdata[2]:,d} obs<extra></extra>",
          colorbar: colorBar(maxLog),
        }];

        // The plot div is positioned over the quicklook's map axes exactly, so
        // the axes have to fill it: no margin, and no automargin either, or a
        // colorbar or tick label would shift the map off the one underneath.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const layout: any = {
          margin: { l: 0, r: 0, t: 0, b: 0, pad: 0, autoexpand: false },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          showlegend: false,
          autosize: true,
          xaxis: { range: [x0, x1], visible: false, constrain: "range" },
          yaxis: { range: [y0, y1], visible: false, scaleanchor: "x", scaleratio: 1, constrain: "range" },
        };

        if (plotDiv.current && alive) {
          await Plotly.newPlot(plotDiv.current, traces, layout, {
            responsive: true, displayModeBar: false,
          });
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
  }, [sat, year, month, mode, season, channel, proj, timeLabel]);

  // `responsive` only listens for window resizes, so the overlay would keep the
  // width it was drawn at when the quicklook underneath is re-laid out.
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

  const box = viewSpec(proj).box;

  return (
    <>
      {status !== "ready" && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.68rem",
            color: status === "error" ? "#c71616" : "#999",
            padding: "0.5rem",
            textAlign: "center",
          }}
        >
          {status === "loading"
            ? "Loading count map…"
            : status === "unavailable"
              ? "Count data unavailable for this selection"
              : `Error: ${errMsg}`}
        </div>
      )}
      {/* Sits exactly over the map axes of the quicklook underneath. */}
      <div
        ref={plotDiv}
        style={{
          position: "absolute",
          left: `${box.left * 100}%`,
          top: `${box.top * 100}%`,
          width: `${box.width * 100}%`,
          height: `${box.height * 100}%`,
        }}
      />
    </>
  );
}

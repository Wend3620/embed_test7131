import { useEffect, useRef, useState } from "react";
import { openGroup, HTTPStore } from "zarr";

import Plotly from "plotly.js";

import { storeUrls } from "./zarrSource";

// The polar quicklooks are drawn over 60°–90° (processor.py `extent`); the small
// count map matches so the two views line up.
const POLAR_MIN_ABS_LAT = 60;
const NLAT = 180;
const NLON = 360;

interface Props {
  sat: string;       // "sat1"
  year: string;      // "2025"
  month: string;     // "12"
  mode: string;      // "month" | "season"
  season: string;    // "DJF" | "MAM" | "JJA" | "SON"
  channel: string;   // "12" | "24" | "30" | "32"
  proj: string;      // "np" | "gb" | "sp"
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

        const urls = storeUrls({ sat, year, month, mode, season });
        const chNum = parseInt(channel, 10);

        let latData: Float64Array | null = null;
        let lonData: Float64Array | null = null;
        const counts = new Float64Array(NLAT * NLON);
        let nStores = 0;

        // Missing stores (sat2, or months outside the archived range) are skipped;
        // only a complete miss is reported as "unavailable".
        const slabs = await Promise.allSettled(urls.map(async (url) => {
          const root = await openGroup(new HTTPStore(url), "", "r");
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const ga = async (name: string) => ((await root.getItem(name)) as any).get();
          const [latRaw, lonRaw] = await Promise.all([ga("lat"), ga("lon")]);

          // The channel number indexes the 63-long spectral axis directly, the same
          // convention as SpectralPanel's HIGHLIGHT set. The `spectral` coordinate is
          // int64, which zarr.js cannot decode, so it is deliberately never read.
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const arr = (await root.getItem("spectral_radiance_count")) as any;
          const nd = arr.shape.length as number;
          let names: string[] = (await arr.attrs.asObject())["_ARRAY_DIMENSIONS"] ?? [];
          if (names.length !== nd) {
            names = new Array(nd).fill("");
            names[nd - 1] = "spectral"; names[nd - 2] = "lon"; names[nd - 3] = "lat";
          }
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const selection: any[] = names.map((nm) => (nm === "spectral" ? chNum : null));
          const raw = await arr.getRaw(selection);

          return {
            lat: latRaw.data as Float64Array,
            lon: lonRaw.data as Float64Array,
            data: raw.data as ArrayLike<number>,
          };
        }));

        for (const s of slabs) {
          if (s.status !== "fulfilled") continue;
          const { lat, lon, data } = s.value;
          if (data.length !== counts.length) continue;
          latData = lat; lonData = lon;
          for (let p = 0; p < data.length; p++) {
            const v = data[p];
            if (Number.isFinite(v)) counts[p] += v;
          }
          nStores++;
        }

        if (!alive) return;
        if (!nStores || !latData || !lonData) { setStatus("unavailable"); return; }

        // The stored coordinates are cell lower edges (-90..89, -180..179); shift to
        // cell centres so markers and heatmap cells land where processor.py draws them.
        const lat = Float64Array.from(latData, (v) => v + 0.5);
        const lon = Float64Array.from(lonData, (v) => v + 0.5);
        const title = `Obs count · ch${channel} · ${timeLabel}`;

        let maxLog = 0;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let traces: any[];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const layout: any = {
          margin: { l: 4, r: 4, t: 22, b: 30 },
          title: { text: title, x: 0, xanchor: "left", font: { size: 10, family: "'IBM Plex Mono', monospace" } },
          paper_bgcolor: "#ffffff",
          plot_bgcolor: "#ffffff",
          showlegend: false,
          autosize: true,
        };

        if (proj === "gb") {
          // Equirectangular by construction — one image instead of 64 800 markers.
          const z: (number | null)[][] = [];
          const cd: (number | null)[][] = [];
          for (let i = 0; i < lat.length; i++) {
            const zRow: (number | null)[] = new Array(lon.length);
            const cdRow: (number | null)[] = new Array(lon.length);
            for (let j = 0; j < lon.length; j++) {
              const c = counts[i * lon.length + j];
              if (c > 0) {
                const lg = Math.log10(c);
                if (lg > maxLog) maxLog = lg;
                zRow[j] = lg; cdRow[j] = c;
              } else {
                zRow[j] = null; cdRow[j] = null;
              }
            }
            z.push(zRow); cd.push(cdRow);
          }
          traces = [{
            type: "heatmap",
            x: Array.from(lon), y: Array.from(lat), z,
            customdata: cd,
            colorscale: "Viridis",
            hovertemplate: "%{y:.1f}°, %{x:.1f}°<br>%{customdata:,d} obs<extra></extra>",
            colorbar: {
              orientation: "h", y: -0.02, yanchor: "top", thickness: 6, len: 0.9,
              tickfont: { size: 8 }, outlinewidth: 0, ...logTicks(maxLog),
            },
          }];
          layout.xaxis = { range: [-180, 180], showticklabels: false, ticks: "", zeroline: false, showgrid: false };
          layout.yaxis = { range: [-90, 90], showticklabels: false, ticks: "", zeroline: false, showgrid: false, scaleanchor: "x" };
        } else {
          // Orthographic pole view: square markers on the observed cells only.
          const north = proj !== "sp";
          const mLat: number[] = [], mLon: number[] = [], mVal: number[] = [];
          const mCd: number[] = [];
          for (let i = 0; i < lat.length; i++) {
            const la = lat[i];
            if (north ? la < POLAR_MIN_ABS_LAT : la > -POLAR_MIN_ABS_LAT) continue;
            for (let j = 0; j < lon.length; j++) {
              const c = counts[i * lon.length + j];
              if (!(c > 0)) continue;
              const lg = Math.log10(c);
              if (lg > maxLog) maxLog = lg;
              mLat.push(la); mLon.push(lon[j]); mVal.push(lg); mCd.push(c);
            }
          }
          if (!mLat.length) { setStatus("unavailable"); return; }
          traces = [{
            type: "scattergeo",
            lat: mLat, lon: mLon, mode: "markers",
            customdata: mCd,
            hovertemplate: "%{lat:.1f}°, %{lon:.1f}°<br>%{customdata:,d} obs<extra></extra>",
            marker: {
              symbol: "square", size: 4, color: mVal, colorscale: "Viridis",
              line: { width: 0 },
              colorbar: {
                orientation: "h", y: -0.02, yanchor: "top", thickness: 6, len: 0.9,
                tickfont: { size: 8 }, outlinewidth: 0, ...logTicks(maxLog),
              },
            },
          }];
          layout.geo = {
            projection: {
              type: "orthographic",
              rotation: { lon: 0, lat: north ? 90 : -90 },
              // Zoom the hemisphere down to the 60°-pole cap. lataxis.range does not
              // scale an orthographic geo, so the zoom has to come from projection.scale.
              scale: 1.9,
            },
            domain: { x: [0, 1], y: [0, 1] },
            showcoastlines: true, coastlinewidth: 0.5, coastlinecolor: "#666",
            showland: true, landcolor: "#f2f2f2",
            showocean: false, showframe: false,
            bgcolor: "#ffffff",
          };
        }

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
      <div ref={plotDiv} style={{ width: "100%", height: "100%" }} />
    </>
  );
}

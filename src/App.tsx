"use client";

import { Fragment, useEffect, useState } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import "./App.css";
import SpectralPanel from "./SpectralPanel";
import { loadCountGrid, countAt, type CountGrid } from "./zarrSource";
// import CountMapPanel from "./CountMapPanel";
// import { time } from "console";

// ── Types ──────────────────────────────────────────────────────────────────
type Mode = "month" | "season";

type Tier = "lite" | "pro";

type OptionKey = "sat" | "month" | "season" | "year" | "channel" | "proj" | "var" | "variable";

type Selection = Record<OptionKey, string>;

// ── Data ───────────────────────────────────────────────────────────────────
const LONGNAME: Record<string, Record<string, string>> = {
'sat': { "PREFIRE-Sat1": "sat1", "PREFIRE-Sat2": "sat2" },
'month': {'January': "1", "February": "2", "March": "3", "April": "4", "May": "5",
   "June": "6", "July": "7", "August": "8", "September": "9", "October": "10", "November": "11", "December": "12" },
'season': { "DJF": "DJF", "MAM": "MAM", "JJA": "JJA", "SON": "SON" },
'year': Object.fromEntries(Array.from({ length: new Date().getFullYear() - 2024 + 1 }, (_, i) => String(2024 + i)).map(y => [y, y])),
'channel': { "Channel 12": "12", "Channel 24": "24", "Channel 30": "30", "Channel 32": "32" },
'proj': { "North pole": "np", "Global": "gb", "South pole": "sp", "Greenland": "gr" },
'var': { "Mean": "mean", "Max": "max", "Min": "min", "Std": "std" },
};
const OPTIONS: Record<OptionKey, string[]> = {
  sat:     ["PREFIRE-Sat1", "PREFIRE-Sat2"],
  month:   ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
  season:  ["DJF","MAM","JJA","SON"],
  year:    Array.from({ length: new Date().getFullYear() - 2024 + 1 }, (_, i) => String(2024 + i)),
  channel: ["Channel 12","Channel 24","Channel 30","Channel 32"],
  proj:    ["North pole","Global","South pole", "Greenland"],
  var:     ["Mean","Max","Min","Std"],
  variable: ["Brightness temperature","Spectral radiance"],
};

const LABELS: Record<OptionKey, string> = {
  sat:     "Satellite",
  month:   "Month",
  season:  "Season",
  year:    "Year",
  channel: "Channel",
  proj:    "View",
  var:     "Data type",
  variable: "Variable",
};

const MAP_RADIUS_PX   = 600; // radius of 60°N boundary circle in 1500×1500 image px
const MAP_CENTER_X_PX = 640; // x-coordinate of circle center in 1500×1500 image px (< 750 if colorbar is on the right)
const MAP_CENTER_Y_PX = 785; // y-coordinate of circle center in 1500×1500 image px

// ── Component ──────────────────────────────────────────────────────────────
export default function App() {
  const [mode, setMode] = useState<Mode>("month");
  const [tier, setTier] = useState<Tier>("lite");
  const [sel, setSel] = useState<Selection>({
    sat: "PREFIRE-Sat1", month: "December", season: "DJF", year: "2025", channel: "Channel 12", proj: "North pole", var: "Mean",
    variable: "Brightness temperature",
  });
  const [erroredFile, setErroredFile] = useState<string | null>(null);
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);
  const [panelCoords, setPanelCoords] = useState({ lat: 65, lon: -130 });
  const [hoverCoords, setHoverCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);

  // Observation-count views: the sidebar filler, and the on-demand map overlay
  const [countImgError, setCountImgError] = useState(false);
  // const [showCounts, setShowCounts] = useState(false);
  // Per-cell observation counts for the hover readout; common to the BT and SR maps
  const [countState, setCountState] = useState<{ key: string; grid: CountGrid | null } | null>(null);

  // Spectral-panel aggregation controls
  const [temporalMean, setTemporalMean] = useState(false);
  const [showSpatialMenu, setShowSpatialMenu] = useState(false);
  const emptyBoxInputs = { latMin: "", latMax: "", lonMin: "", lonMax: "" };
  const defaultHemis = { latMin: "°N", latMax: "°N", lonMin: "°W", lonMax: "°W" } as const;
  const [boxInputs, setBoxInputs] = useState(emptyBoxInputs);
  const [boxHemis, setBoxHemis] = useState<Record<keyof typeof emptyBoxInputs, "°N" | "°S" | "°E" | "°W">>(defaultHemis);
  const [box, setBox] = useState<{ latMin: number; latMax: number; lonMin: number; lonMax: number } | null>(null);

  const toggleHemi = (key: keyof typeof emptyBoxInputs) =>
    setBoxHemis((prev) => {
      const cur = prev[key];
      const next = cur === "°N" ? "°S" : cur === "°S" ? "°N" : cur === "°W" ? "°E" : "°W";
      return { ...prev, [key]: next };
    });

  const submitBox = () => {
    const signed = (key: keyof typeof emptyBoxInputs) => {
      const m = parseFloat(boxInputs[key]);
      return boxHemis[key] === "°S" || boxHemis[key] === "°W" ? -m : m;
    };
    const v = {
      latMin: signed("latMin"), latMax: signed("latMax"),
      lonMin: signed("lonMin"), lonMax: signed("lonMax"),
    };
    if (Object.values(v).every(Number.isFinite)) {
      setBox({
        latMin: Math.min(v.latMin, v.latMax), latMax: Math.max(v.latMin, v.latMax),
        lonMin: Math.min(v.lonMin, v.lonMax), lonMax: Math.max(v.lonMin, v.lonMax),
      });
      setShowSpatialMenu(false);
    }
  };
  const clearBox = () => {
    setBox(null);
    setBoxInputs(emptyBoxInputs);
    setBoxHemis(defaultHemis);
    setShowSpatialMenu(false);
  };



  function mapClick(e: React.MouseEvent<HTMLImageElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const scale = Math.max(rect.width, rect.height) / 1470;
    const imgX = 750 + (e.clientX - rect.left - rect.width  / 2) / scale;
    const imgY = 750 + (e.clientY - rect.top  - rect.height / 2) / scale;
    const dx = imgX - MAP_CENTER_X_PX;
    const dy = imgY - MAP_CENTER_Y_PX;
    const r  = Math.sqrt(dx * dx + dy * dy);
    if (r > MAP_RADIUS_PX || r === 0) return null;
    const lat = Math.acos(r / (2 * MAP_RADIUS_PX)) * 180 / Math.PI;
    const lon = Math.atan2(dx, dy) * 180 / Math.PI;
    return { lat: Math.round(lat * 10) / 10, lon: Math.round(lon * 10) / 10 };
  }

  const handleChange = (key: OptionKey) => (val: string): void =>
    setSel((prev) => ({ ...prev, [key]: val }));

  const dropdownKeys: OptionKey[] = ["sat", mode, "year", "channel", "proj", "var"];

  const allSelected: boolean = dropdownKeys.every((k) => Boolean(sel[k]));
  // const projLabel: Record<string, string> = { "North pole": "np", "South pole": "sp", "Global": "gb" };
  const timeVal = mode === "month" ? LONGNAME.month[sel.month] : LONGNAME.season[sel.season];
  useEffect(() => {
    fetch(`use_jsons/${LONGNAME.sat[sel.sat]}_${timeVal}_${sel.year}.json`).then((r) => r.json()).then(setInfo).catch(() => null);
  }, [sel.sat, sel.year, timeVal]);

  // Observation counts come from the spectral zarr stores, whichever variable is
  // mapped. Only the north pole view maps the cursor to lat/lon, so only it loads them.
  const hoverable = sel.proj === "North pole";
  const countKey = [sel.sat, sel.year, mode, sel.month, sel.season, sel.channel].join("|");
  useEffect(() => {
    if (!hoverable) return;
    let alive = true;
    loadCountGrid({
      sat: LONGNAME.sat[sel.sat], year: sel.year, month: LONGNAME.month[sel.month], mode,
      season: LONGNAME.season[sel.season], channel: LONGNAME.channel[sel.channel],
    }).then((grid) => { if (alive) setCountState({ key: countKey, grid }); })
      .catch(() => { if (alive) setCountState({ key: countKey, grid: null }); });
    return () => { alive = false; };
  }, [hoverable, countKey, sel.sat, sel.year, sel.month, sel.season, sel.channel, mode]);

  // Counts loaded for an earlier selection read as still loading.
  const countReady = countState?.key === countKey;
  let hoverCount = "…";
  if (countReady && countState.grid && hoverCoords) {
    hoverCount = countAt(countState.grid, hoverCoords.lat, hoverCoords.lon)?.toLocaleString() ?? "—";
  } else if (countReady) {
    hoverCount = "—";
  }
  const time_name = mode === "month" ?
   `${timeVal.padStart(2, "0")}${sel.year.slice(-2)}` : 
   `${LONGNAME.season[sel.season]}${sel.year.slice(-2)}`;
  const BTfilename: string | null = allSelected
    ? `bt_pics/${mode}_plots/${time_name}/${LONGNAME.sat[sel.sat]}_${timeVal}_${
      sel.year}_${LONGNAME.proj[sel.proj]}_ch${LONGNAME.channel[sel.channel]}_${LONGNAME.var[sel.var] || sel.var}.webp`
    : null;
  const SRfilename: string | null = allSelected
    ? `sr_pics/${mode}_plots/${time_name}/${LONGNAME.sat[sel.sat]}_${timeVal}_${
      sel.year}_${LONGNAME.proj[sel.proj]}_spec${LONGNAME.channel[sel.channel]}_${LONGNAME.var[sel.var] || sel.var}.webp`
    : null;
  // Professional unlocks the spectral plot and the variable choice; Lite is brightness temperature only.
  const isPro = tier === "pro";
  const showSR = isPro && sel.variable === "Spectral radiance";
  const filename = showSR ? SRfilename : BTfilename;
  const showPlaceholder = !filename || filename === erroredFile;

  // const placeholderFname = mode === "month"
  //   ? "{Sat}_{Month}_{Year}_{Proj}_ch{Channel}_{Var}.webp"
  //   : "{Sat}_{Season}_{Year}_{Proj}_ch{Channel}_{Var}.webp";

  return (
    <div className="iv-root">

        {/* ── Header ── */}
        <div style={{ height: "7px", backgroundColor: "#b91212", width: "60px", 
          marginLeft: 22, marginTop: '1%', marginBottom: -8, zIndex:20
        }} />
        <header className="iv-header">
          <span className="iv-header-title">PREFIRE Quicklook Viewer</span>
        
        {/* ── Toolbar row 1: tier, variable, aggregation ── */}
          <div className="iv-toolbar-top iv-toolbar">

            {/* Tier toggle */}
            <div className="iv-mode-toggle">
              <button
                className={`iv-mode-btn${tier === "lite" ? " active" : ""}`}
                onClick={() => setTier("lite")}
                title="Brightness temperature maps only"
              >
                Lite
              </button>
              <button
                className={`iv-mode-btn${tier === "pro" ? " active" : ""}`}
                onClick={() => setTier("pro")}
                title="Add the spectral radiance panel and aggregation controls"
              >
                Full
              </button>
            </div>

            {/* Variable selection (Professional only — Lite is brightness temperature) */}
            {isPro && (
              <div className="iv-field">
                <span className="iv-field-label">{LABELS.variable}</span>
                <Select value={sel.variable} onValueChange={handleChange("variable")}>
                  <SelectTrigger style={{ width: "205px" }}>
                    <SelectValue placeholder={LABELS.variable} />
                  </SelectTrigger>
                  <SelectContent >
                    {OPTIONS.variable.map((opt) => (
                      <SelectItem key={opt} value={opt}>
                        {opt}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Spectral-panel aggregation controls (only meaningful when the panel is open) */}
            {isPro && (
              <>
                {/* Temporal (annual) mean toggle */}
                <button
                  className={`iv-panel-btn${temporalMean ? " active" : ""}`}
                  onClick={() => setTemporalMean((p) => !p)}
                  title="Plot the annual (temporal) mean spectral radiance"
                >
                  Annual Mean
                </button>

                {/* Spatial averaging dropdown */}
                <div style={{ position: "relative" }}>
                  <button
                    className={`iv-panel-btn${box ? " active" : ""}`}
                    onClick={() => setShowSpatialMenu((p) => !p)}
                    title="Average spectral radiance over a lat/lon box"
                  >
                    Spatial Averaging ▾
                  </button>
                  {showSpatialMenu && (
                    <div
                      style={{
                        position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 30,
                        background: "#ffffff", border: "1px solid #c71616", borderRadius: 2,
                        padding: "10px", display: "grid", gridTemplateColumns: "auto auto",
                        gap: "6px 12px", alignItems: "center", boxShadow: "0 4px 12px rgba(0,0,0,0.12)",
                        fontFamily: "'IBM Plex Sans', sans-serif", fontSize: "0.75rem", width: "max-content",
                      }}
                    >
                      {([
                        ["Lat min", "latMin"], ["Lat max", "latMax"],
                        ["Lon min", "lonMin"], ["Lon max", "lonMax"],
                      ] as const).map(([label, key]) => (
                        <Fragment key={key}>
                          <label htmlFor={`box-${key}`}>{label}</label>
                          <div style={{ display: "flex", gap: "4px" }}>
                            <input
                              id={`box-${key}`}
                              type="number"
                              min={0}
                              value={boxInputs[key]}
                              onChange={(e) => setBoxInputs((prev) => ({ ...prev, [key]: e.target.value }))}
                              style={{ width: "80px", border: "1px solid #ccc", borderRadius: 2, padding: "2px 4px" }}
                            />
                            <button
                              className="iv-panel-btn"
                              onClick={() => toggleHemi(key)}
                              title="Toggle hemisphere"
                              style={{ width: "2rem", padding: 0 }}
                            >
                              {boxHemis[key]}
                            </button>
                          </div>
                        </Fragment>
                      ))}
                      <div style={{ gridColumn: "1 / -1", display: "flex", gap: "8px", justifyContent: "flex-end", marginTop: 4 }}>
                        <button className="iv-panel-btn" onClick={submitBox}>Submit</button>
                        <button className="iv-panel-btn" onClick={clearBox}>Clear</button>
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </header>

        {/* ── Toolbar row 2: time mode and data selection ── */}
        <div className="iv-toolbar">

          {/* Mode toggle */}
          <div className="iv-mode-toggle">
            <button
              className={`iv-mode-btn${mode === "month" ? " active" : ""}`}
              onClick={() => setMode("month")}
            >
              Month
            </button>
            <button
              className={`iv-mode-btn${mode === "season" ? " active" : ""}`}
              onClick={() => setMode("season")}
            >
              Season
            </button>
          </div>

          {/* Dropdowns */}
          {dropdownKeys.map((key) => (
            <div key={key} className="iv-field">
              <span className="iv-field-label">{LABELS[key]}</span>
              <Select value={sel[key]} onValueChange={handleChange(key)} >
                <SelectTrigger style={{ width: "135px" }} >
                  <SelectValue placeholder={LABELS[key]} />
                </SelectTrigger>
                <SelectContent>
                  {OPTIONS[key].map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ))}
        </div>
        {/* Filename label */}
          <div className="iv-filename">
            <span>Available time: PREFIRE-SAT1: July 2024 - , PREFIRE-SAT2: June 2024 -</span>
          </div>
        {/* ── Viewer ── */}
        <main className="iv-content">

          {/* Image panel */}
          <div className="iv-panel">
            {isPro && (
              <SpectralPanel
                lat={panelCoords.lat}
                lon={panelCoords.lon}
                box={box}
                temporal={temporalMean}
                sat={LONGNAME.sat[sel.sat]}
                year={sel.year}
                month={LONGNAME.month[sel.month]}
                mode = {mode}
                season = {LONGNAME.season[sel.season]}
              />
            )}
            {isPro && <div className="iv-divider" />}
            {filename && !showPlaceholder && (
              <div className="iv-map-wrap">
                <img
                  src={`${filename}`}
                  alt={filename}
                  className="iv-img"
                  onError={() => setErroredFile(filename)}
                  style={{
                    ...(sel.proj === "Global" ? { maxHeight: "65vh" } : {}),
                    ...(sel.proj === "North pole" ? { cursor: "crosshair" } : {}),
                  }}
                  onMouseMove={sel.proj === "North pole"
                    ? (e) => { setHoverCoords(mapClick(e)); setMousePos({ x: e.clientX, y: e.clientY }); }
                    : undefined}
                  onMouseLeave={sel.proj === "North pole"
                    ? () => { setHoverCoords(null); setMousePos(null); }
                    : undefined}
                  onClick={sel.proj === "North pole"
                    ? (e) => { const c = mapClick(e); if (c) setPanelCoords(c); }
                    : undefined}
                />
                
                {/*DISABLED BY SEPT meeting Observation counts, computed from the zarr stores only when asked for */}
                {/***isPro && (
                  <button
                    className={`iv-panel-btn iv-map-toggle${showCounts ? " active" : ""}`}
                    onClick={() => setShowCounts((p) => !p)}
                    title="Overlay observation counts per 1° grid cell"
                  >
                    Counts
                  </button>
                )}

                {isPro && showCounts && (
                  <div className="iv-map-overlay">
                    <CountMapPanel
                      sat={LONGNAME.sat[sel.sat]}
                      year={sel.year}
                      month={LONGNAME.month[sel.month]}
                      mode={mode}
                      season={LONGNAME.season[sel.season]}
                      channel={LONGNAME.channel[sel.channel]}
                      proj={LONGNAME.proj[sel.proj]}
                      timeLabel={mode === "month" ? `${sel.month.slice(0, 3)} ${sel.year}` : `${sel.season} ${sel.year}`}
                    />
                  </div>
                )***/}
              </div>
            )}
            
            {!showPlaceholder &&<div className="iv-divider" />}
            {!showPlaceholder && (
            <div className="iv-info">
              <div className="iv-info-rows">
                {info && Object.entries(info).map(([k, v]) => (
                  <div key={k} className="iv-info-row">
                    <span className="iv-info-key">{k+':'}</span>
                    <span className="iv-info-val">
                      {Array.isArray(v) ? (v.length === 0 ? "—" : v.join(", ")) : String(v)}
                    </span>
                  </div>
                ))}
              </div>
              {/* Static reference count map; the live version is the map overlay */}
              <div className="iv-info-map">
                {countImgError ? (
                  <div className="iv-info-map-msg">Count map unavailable</div>
                ) : (
                  <img
                    src="trial_pics/count1.png"
                    alt="Observation count map"
                    className="iv-info-map-img"
                    onError={() => setCountImgError(true)}
                  />
                )}
              </div>
            </div>
            )}
            <div
              className="iv-placeholder"
              style={{ display: showPlaceholder ? "flex" : "none" }}
            >
              <div className="iv-placeholder-icon">
                <svg
                  width="28"
                  height="28"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                >
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <path d="M21 15l-5-5L5 21" />
                </svg>
              </div>
              <p className="iv-placeholder-label">
                Image not available
              </p>
              {/* <div className="iv-placeholder-fname">
                {placeholderFname}
              </div> */}
            </div>
          </div>

        </main>
        {hoverCoords && mousePos && (
          <div
            className="iv-map-tooltip"
            style={{ left: mousePos.x + 14, top: mousePos.y + 14 }}
          >
            <div>{`${hoverCoords.lat.toFixed(1)}°N  ${Math.abs(hoverCoords.lon).toFixed(1)}°${hoverCoords.lon >= 0 ? "E" : "W"}`}</div>
            <div>{`Obs. count: ${hoverCount}`}</div>
          </div>
        )}
      </div>
  );
}

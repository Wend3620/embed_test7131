import { openGroup, HTTPStore } from "zarr";

// ── Data source ──────────────────────────────────────────────────────────────
// Public assets are served from ./public, so data is available at /data.
// Use an absolute URL to avoid Invalid URL errors in URL constructors.
// BASE_URL is "/embed_test7131/" in the deployed build and "/" in dev (it always
// has a trailing slash), so this resolves to the correct subpath on GitHub Pages.
export const DATA_DIR = `${window.location.origin}${import.meta.env.BASE_URL}data`;
export const MASK_DIR = `${window.location.origin}${import.meta.env.BASE_URL}masks`;

// Files are named sat#_mmyy.zarr (e.g. sat1_1225.zarr → sat1, month 12, year 2025).
export const zarrUrl = (sat: string, yy: string, mm: string) => `${DATA_DIR}/${sat}_${mm}${yy}.zarr`;

export const monthsInSeason = (season: string) => {
  switch (season) {
    case "DJF": return ["12", "01", "02"];
    case "MAM": return ["03", "04", "05"];
    case "JJA": return ["06", "07", "08"];
    case "SON": return ["09", "10", "11"];
    default: throw new Error(`Unknown season: ${season}`);
  }};

export interface StoreSelection {
  sat: string;
  year: string;
  month: string;
  mode: string;
  season: string;
  temporal?: boolean;
}

// Stores to aggregate for a selection: 12 months for the annual mean, the three
// months of a season, or the single selected month. December of a season belongs
// to the previous year (DJF 2025 = Dec 2024, Jan 2025, Feb 2025).
export function storeUrls({ sat, year, month, mode, season, temporal = false }: StoreSelection): string[] {
  const yy = year.slice(-2);
  const months = temporal
    ? Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"))
    : mode === "month"
      ? [month.padStart(2, "0")]
      : monthsInSeason(season);
  return months.map(mm =>
    zarrUrl(sat, parseInt(mm) === 12 && mode === "season" ? `${parseInt(year) - 1}`.slice(-2) : yy, mm));
}

// ── Observation counts ───────────────────────────────────────────────────────
// Per-cell observation counts come from the spectral stores' spectral_radiance_count,
// and are shared by every view of the selection: the brightness temperature maps
// are built from the same observations, so the same count applies to them.
export interface CountGrid {
  lat: Float64Array;     // cell lower edges (-90..89)
  lon: Float64Array;     // cell lower edges (-180..179)
  counts: Float64Array;  // lat-major, summed over the selection's months
}

// Counts for one channel, summed over the selection's stores. Missing stores (sat2,
// or months outside the archived range) are skipped; null only when none load.
export async function loadCountGrid(
  { channel, ...sel }: StoreSelection & { channel: string },
): Promise<CountGrid | null> {
  const urls = storeUrls({ ...sel, temporal: false });
  const chNum = parseInt(channel, 10);

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

  let grid: CountGrid | null = null;
  for (const s of slabs) {
    if (s.status !== "fulfilled") continue;
    const { lat, lon, data } = s.value;
    if (!grid) grid = { lat, lon, counts: new Float64Array(lat.length * lon.length) };
    if (data.length !== grid.counts.length) continue;
    for (let p = 0; p < data.length; p++) {
      const v = data[p];
      if (Number.isFinite(v)) grid.counts[p] += v;
    }
  }
  return grid;
}

// Count of the grid cell holding (lat, lon), or null outside the grid.
export function countAt({ lat, lon, counts }: CountGrid, la: number, lo: number): number | null {
  const nLat = lat.length, nLon = lon.length;
  const latStep = nLat > 1 ? lat[1] - lat[0] : 1;
  const lonStep = nLon > 1 ? lon[1] - lon[0] : 1;
  const li = Math.floor((la - lat[0]) / latStep);
  let lj = Math.floor((lo - lon[0]) / lonStep);
  lj = ((lj % nLon) + nLon) % nLon;
  if (li < 0 || li >= nLat) return null;
  return counts[li * nLon + lj];
}

// ── Regions ──────────────────────────────────────────────────────────────────
// Area the spectral panel averages over for each map view, keyed by the view's
// LONGNAME.proj code. Pole caps match the maps' 60° boundary circle.
export interface Region {
  label: string;
  latMin?: number;
  latMax?: number;
  mask?: string;   // .npy file in public/masks
}

export const REGIONS: Record<string, Region> = {
  np: { label: "North pole, 60–90°N", latMin: 60 },
  sp: { label: "South pole, 60–90°S", latMax: -60 },
  gb: { label: "Global" },
  gre: { label: "Greenland", mask: "GRE_mask.npy" },
};

// A boolean .npy mask on the data grid (lat-major, 1 = inside). Masks made on the
// PREFIRE L3 grid have fewer lat rows; they are padded equally north and south,
// the same recipe as region_mask() in random/zarr_views.py.
const maskCache = new Map<string, Promise<Uint8Array>>();

export function loadMask(name: string, nLat: number, nLon: number): Promise<Uint8Array> {
  const key = `${name}|${nLat}|${nLon}`;
  let p = maskCache.get(key);
  if (!p) {
    p = fetchMask(name, nLat, nLon);
    p.catch(() => maskCache.delete(key)); // let a failed fetch be retried
    maskCache.set(key, p);
  }
  return p;
}

async function fetchMask(name: string, nLat: number, nLon: number): Promise<Uint8Array> {
  const res = await fetch(`${MASK_DIR}/${name}`);
  if (!res.ok) throw new Error(`Mask ${name}: HTTP ${res.status}`);
  const buf = await res.arrayBuffer();
  const view = new DataView(buf);

  // .npy layout: "\x93NUMPY", major, minor, header length (u16 in v1, u32 after), header dict.
  const magic = new Uint8Array(buf, 0, 6);
  if (magic[0] !== 0x93 || String.fromCharCode(...magic.slice(1)) !== "NUMPY") {
    throw new Error(`Mask ${name}: not a .npy file`);
  }
  const major = view.getUint8(6);
  const hlen = major === 1 ? view.getUint16(8, true) : view.getUint32(8, true);
  const start = major === 1 ? 10 : 12;
  const header = new TextDecoder().decode(new Uint8Array(buf, start, hlen));
  const descr = /'descr':\s*'([^']+)'/.exec(header)?.[1];
  const fortran = /'fortran_order':\s*(True|False)/.exec(header)?.[1];
  const shape = /'shape':\s*\((\d+),\s*(\d+)\)/.exec(header);
  if ((descr !== "|b1" && descr !== "|u1") || fortran !== "False" || !shape) {
    throw new Error(`Mask ${name}: expected a 2-D C-order bool array, got ${header.trim()}`);
  }
  const [mLat, mLon] = [parseInt(shape[1]), parseInt(shape[2])];
  const pad = nLat - mLat;
  if (pad < 0 || pad % 2) throw new Error(`Mask ${name}: ${mLat} lat rows cannot pad evenly to ${nLat}`);
  if (mLon !== nLon) throw new Error(`Mask ${name}: has ${mLon} lons, grid has ${nLon}`);

  const out = new Uint8Array(nLat * nLon);
  out.set(new Uint8Array(buf, start + hlen, mLat * mLon), (pad / 2) * nLon);
  return out;
}

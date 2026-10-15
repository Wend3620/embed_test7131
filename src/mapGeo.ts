// ── Map image pixel → lat/lon ────────────────────────────────────────────────
// The quicklook maps are saved with bbox_inches='tight', so where the map frame
// sits in the image varies with title and colorbar label widths. The frame boxes
// and each view's projection come from public/map_frames.json, written by
// random/map_frames.py (re-run it when new images are added).

type Box = [number, number, number, number];   // x0, y0, x1, y1 — inclusive image px

interface OrthoView {
  proj: "ortho";
  lat0: number; lon0: number; R: number;
  xlim: [number, number]; ylim: [number, number];   // frame edges in projection metres
  latMin?: number; latMax?: number;                 // polar caps end at 60°
}

interface RobinsonView {
  proj: "robinson";
  xlim: [number, number]; ylim: [number, number];
  table: { lat: number[]; y: number[]; half: number[] };  // y and x at lon 180 per lat
}

export interface MapFrames {
  views: Record<string, OrthoView | RobinsonView>;
  groups: Record<string, Box>;   // "<bt|sr>|<view>|<W>x<H>"
  files: Record<string, Box>;    // per-image exceptions
}

let framesPromise: Promise<MapFrames> | null = null;

export function loadMapFrames(): Promise<MapFrames> {
  if (!framesPromise) {
    framesPromise = fetch(`${window.location.origin}${import.meta.env.BASE_URL}map_frames.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`map_frames.json: HTTP ${r.status}`);
        return r.json() as Promise<MapFrames>;
      });
    framesPromise.catch(() => { framesPromise = null; }); // let a failed fetch be retried
  }
  return framesPromise;
}

const DEG = Math.PI / 180;

// Linear interpolation of ys at x over ascending xs (null outside the table).
function interp(x: number, xs: number[], ys: number[]): number | null {
  if (x < xs[0] || x > xs[xs.length - 1]) return null;
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] <= x) lo = mid; else hi = mid;
  }
  const t = xs[hi] === xs[lo] ? 0 : (x - xs[lo]) / (xs[hi] - xs[lo]);
  return ys[lo] + t * (ys[hi] - ys[lo]);
}

function inverseOrtho(v: OrthoView, x: number, y: number): { lat: number; lon: number } | null {
  const rho = Math.hypot(x, y);
  if (rho > v.R) return null;                       // off the visible hemisphere
  const phi0 = v.lat0 * DEG;
  let lat = v.lat0, lon = v.lon0;
  if (rho > 0) {
    const c = Math.asin(rho / v.R);
    lat = Math.asin(Math.cos(c) * Math.sin(phi0) + (y * Math.sin(c) * Math.cos(phi0)) / rho) / DEG;
    lon = v.lon0 + Math.atan2(x * Math.sin(c),
      rho * Math.cos(c) * Math.cos(phi0) - y * Math.sin(c) * Math.sin(phi0)) / DEG;
  }
  if (v.latMin !== undefined && lat < v.latMin) return null;
  if (v.latMax !== undefined && lat > v.latMax) return null;
  return { lat, lon };
}

function inverseRobinson(v: RobinsonView, x: number, y: number): { lat: number; lon: number } | null {
  const lat = interp(y, v.table.y, v.table.lat);
  if (lat === null) return null;
  const half = interp(lat, v.table.lat, v.table.half);
  if (!half) return null;
  const lon = (x / half) * 180;
  return Math.abs(lon) > 180 ? null : { lat, lon };
}

// Lat/lon under natural-image pixel (px, py) of the map image at imgPath
// ("bt_pics/…webp"), or null off the map or for an uncalibrated image size.
export function pixelToLatLon(
  frames: MapFrames, imgPath: string, view: string,
  natW: number, natH: number, px: number, py: number,
): { lat: number; lon: number } | null {
  const v = frames.views[view];
  const product = imgPath.startsWith("sr_pics") ? "sr" : "bt";
  const box = frames.files[imgPath] ?? frames.groups[`${product}|${view}|${natW}x${natH}`];
  if (!v || !box) return null;
  const [x0, y0, x1, y1] = box;
  if (px < x0 || px > x1 + 1 || py < y0 || py > y1 + 1) return null;
  // Frame edges ↔ projection limits; image y runs down
  const x = v.xlim[0] + ((px - x0) / (x1 + 1 - x0)) * (v.xlim[1] - v.xlim[0]);
  const y = v.ylim[1] - ((py - y0) / (y1 + 1 - y0)) * (v.ylim[1] - v.ylim[0]);
  const ll = v.proj === "ortho" ? inverseOrtho(v, x, y) : inverseRobinson(v, x, y);
  if (!ll) return null;
  const lon = ((ll.lon + 540) % 360) - 180;          // wrap to [-180, 180)
  return { lat: ll.lat, lon };
}

// Natural-image pixel under a client point on an <img> drawn with object-fit: cover
// (scaled to fill its box, centred, overflow cropped).
export function clientToNatural(img: HTMLImageElement, clientX: number, clientY: number) {
  const rect = img.getBoundingClientRect();
  const scale = Math.max(rect.width / img.naturalWidth, rect.height / img.naturalHeight);
  const offX = (rect.width - img.naturalWidth * scale) / 2;
  const offY = (rect.height - img.naturalHeight * scale) / 2;
  return {
    px: (clientX - rect.left - offX) / scale,
    py: (clientY - rect.top - offY) / scale,
  };
}

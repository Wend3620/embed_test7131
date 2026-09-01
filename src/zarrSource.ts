// ── Data source ──────────────────────────────────────────────────────────────
// Public assets are served from ./public, so data is available at /data.
// Use an absolute URL to avoid Invalid URL errors in URL constructors.
// BASE_URL is "/embed_test7131/" in the deployed build and "/" in dev (it always
// has a trailing slash), so this resolves to the correct subpath on GitHub Pages.
export const DATA_DIR = `${window.location.origin}${import.meta.env.BASE_URL}data`;

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

interface StoreSelection {
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

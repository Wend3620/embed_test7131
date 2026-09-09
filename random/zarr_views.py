#!/usr/bin/env python3
"""
Map views straight off the gridded zarr months in ../data.

Each month sits in its own store, ``sat{#}_{mmyy}.zarr``, holding the mean, std,
count, min and max of spectral radiance binned to the same 1° global grid
processor.py plots on — ``ds.lat``/``ds.lon`` are the bin *edges*, so the cell
centres are exactly processor's ``lat_mids``/``lon_mids``.  Pick a satellite, a
period (one month, or a season), a statistic and a channel; the 180×360 field
goes to processor's plotting functions, so these maps come out looking like the
ones built from the raw granules.

    # one month, north pole
    python zarr_views.py --sat 1 --year 2025 --month 1 --channel 12 --stat mean

    # a season, several views and statistics at once
    python zarr_views.py --sat 2 --year 2025 --season DJF --channel 24 \
        --stat mean std --view north greenland

    # what is on disk, and which wavelength each channel is
    python zarr_views.py --list

or from a notebook next to this file:

    from zarr_views import make_view, available_months
    make_view(sat=1, year=2025, season='DJF', channel=12, stat='mean', view='north')

Note on units: the zarr attributes say W/m²/sr/nm, but the magnitudes are
per-µm (a Planck fit at the peak channel lands on a sensible T_b only that way),
which is how greenland.ipynb reads them too — hence RADIANCE_UNITS below.
"""

import argparse
import re
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# processor.py lives next to this file; keep the import working from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent))
from processor import (  # noqa: E402
    SEASON_MONTHS,
    create_global_plot,
    create_orthographic_plot,
    lat_mids,
    lon_mids,
)

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
MASK_FILE = DATA_DIR / 'GRE_mask.npy'
OUT_DIR = Path(__file__).resolve().parent.parent / 'gallery' / 'zarr_views'

MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

RADIANCE_UNITS = 'W/m²/sr/µm'

# statistic -> (zarr variable, title text, default colormap, colorbar label)
STATS = {
    'mean':  ('spectral_radiance',       'Mean Spectral Radiance',
              'inferno', f'Spectral radiance ({RADIANCE_UNITS})'),
    'min':   ('spectral_radiance_min',   'Min Spectral Radiance',
              'inferno', f'Spectral radiance ({RADIANCE_UNITS})'),
    'max':   ('spectral_radiance_max',   'Max Spectral Radiance',
              'inferno', f'Spectral radiance ({RADIANCE_UNITS})'),
    'std':   ('spectral_radiance_std',   'Std of Spectral Radiance',
              'viridis', f'σ ({RADIANCE_UNITS})'),
    'count': ('spectral_radiance_count', 'Observation Count',
              'cividis', 'Observations per cell'),
}

# view -> how to draw it.  'pole' and 'global' go to processor; 'region' is the
# orthographic close-up from greenland.ipynb.
VIEWS = {
    'north':     dict(kind='pole', pole='north', name='North Pole'),
    'south':     dict(kind='pole', pole='south', name='South Pole'),
    'global':    dict(kind='global', name='Global'),
    'greenland': dict(kind='region', name='Greenland', mask='greenland',
                      central_lat=72, central_lon=-40,
                      extent=(-75, -10, 50, 90)),
}


# ── which files a request covers ─────────────────────────────────────────────
def _full_year(year):
    """2-digit → 20yy.  Filenames carry only yy, so 2000–2099 is the whole range."""
    y = int(year)
    y = y if y > 99 else 2000 + y
    if not 2000 <= y <= 2099:
        raise ValueError(f'year {year} outside 2000-2099 — '
                         f'sat{{#}}_{{mmyy}} filenames carry only 2 digits')
    return y


def month_file(year, month, sat=1, data_dir=None):
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    return data_dir / f'sat{sat}_{month:02d}{_full_year(year) % 100:02d}.zarr'


def available_months(sat=1, data_dir=None):
    """Sorted [(year, month), ...] actually present on disk for one satellite."""
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    found = []
    for p in data_dir.glob(f'sat{sat}_*.zarr'):
        m = re.fullmatch(rf'sat{sat}_(\d{{2}})(\d{{2}})', p.stem)
        if m:
            found.append((2000 + int(m.group(2)), int(m.group(1))))
    return sorted(found)


def resolve_period(year, month=None, season=None):
    """(months, label, tag) for a request.

    A month is itself: month=1, year=2025 → Jan 2025.
    A season is labelled by the year it ENDS in — the convention greenland.ipynb
    uses — so December comes from the year before: season='DJF', year=2025 →
    Dec 2024, Jan 2025, Feb 2025.
    """
    if month is not None and season is not None:
        raise ValueError('give a month or a season, not both')
    year = _full_year(year)

    if month is not None:
        month = int(month)
        if not 1 <= month <= 12:
            raise ValueError(f'month {month} out of range 1-12')
        return ([(year, month)],
                f'{MONTH_ABBR[month - 1]} {year}',
                f'{month:02d}{year % 100:02d}')

    if season is None:
        raise ValueError('give either month= or season=')
    season = str(season).upper()
    if season not in SEASON_MONTHS:
        raise ValueError(f'season must be one of {sorted(SEASON_MONTHS)} — got {season!r}')

    months = [(year - 1 if mo == 12 else year, mo) for mo in SEASON_MONTHS[season]]
    y0, y1 = months[0][0], months[-1][0]
    label = f'{season} {y1}' if y0 == y1 else f'{season} {y0}/{y1 % 100:02d}'
    return months, label, f'{season}{year % 100:02d}'


def missing_months(months, sat=1, data_dir=None):
    """['2024-12', ...] for requested months with no store on disk."""
    return [f'{y}-{m:02d}' for y, m in months
            if not month_file(y, m, sat, data_dir).exists()]


# ── cells → one field on the 1° grid ─────────────────────────────────────────
def load_field(sat, channel, stat, months, data_dir=None, allow_partial=False):
    """(field, count, wavelength, months_used) for one statistic on the 1° grid.

    Months pool the way the cells themselves were pooled: every cell already
    holds a mean/std/count over its own observations, so

        n = Σᵢ nᵢ,   μ = Σᵢ nᵢmᵢ / n,   σ² = Σᵢ nᵢ(sᵢ² + mᵢ²)/n − μ²

    and min/max simply take the extreme across the months.  One month is the
    same arithmetic with a single term.  A season whose months are not all on
    disk raises unless allow_partial — averaging over whatever happens to be
    there would quietly change what the map means.
    """
    if stat not in STATS:
        raise ValueError(f'stat must be one of {sorted(STATS)} — got {stat!r}')

    absent = missing_months(months, sat, data_dir)
    present = [(y, m) for y, m in months
               if f'{y}-{m:02d}' not in absent]
    if absent and not allow_partial:
        raise FileNotFoundError(
            f'sat{sat}: no data for {", ".join(absent)} — '
            f'refusing an incomplete period (pass allow_partial=True to override)')
    if not present:
        raise FileNotFoundError(f'sat{sat}: none of the requested months are on disk')
    if absent:
        print(f'  ! averaging without {", ".join(absent)}')

    n_tot = sum_nm = sum_nsq = None      # count-weighted accumulators
    extreme = None                       # running min/max, for those stats
    wavelengths = []

    for y, m in present:
        ds = xr.open_zarr(month_file(y, m, sat, data_dir)).isel(spectral=channel)
        _check_grid(ds, month_file(y, m, sat, data_dir))

        n = ds.spectral_radiance_count.values.astype('float64')
        mean = ds.spectral_radiance.values.astype('float64')
        std = ds.spectral_radiance_std.values.astype('float64')
        wavelengths.append(float(ds.wavelength.values))

        good = (n > 0) & np.isfinite(mean)
        n = np.where(good, n, 0.0)
        mean = np.where(good, mean, 0.0)
        std = np.where(good & np.isfinite(std), std, 0.0)   # std is NaN where count == 1

        if n_tot is None:
            n_tot = np.zeros_like(n)
            sum_nm = np.zeros_like(n)
            sum_nsq = np.zeros_like(n)
        n_tot += n
        sum_nm += n * mean
        sum_nsq += n * (std ** 2 + mean ** 2)

        if stat in ('min', 'max'):
            v = np.where(good, ds[STATS[stat][0]].values.astype('float64'), np.nan)
            if extreme is None:
                extreme = v
            else:                                            # fmin/fmax skip NaN
                extreme = np.fmin(extreme, v) if stat == 'min' else np.fmax(extreme, v)

    with np.errstate(invalid='ignore', divide='ignore'):
        n_ok = np.where(n_tot > 0, n_tot, np.nan)
        mu = sum_nm / n_ok
        var = np.clip(sum_nsq / n_ok - mu ** 2, 0, None)

    if stat == 'mean':
        field = mu
    elif stat == 'std':
        field = np.sqrt(var)
    elif stat == 'count':
        field = n_ok
    else:
        field = extreme

    wl = float(np.round(np.mean(wavelengths), 2))
    return field, n_tot, wl, present


def _check_grid(ds, path):
    """The zarr coords are bin edges; their centres must be processor's grid."""
    if (ds.sizes['lat'], ds.sizes['lon']) != (len(lat_mids), len(lon_mids)):
        raise ValueError(f'{path}: grid is {ds.sizes["lat"]}x{ds.sizes["lon"]}, '
                         f'processor plots {len(lat_mids)}x{len(lon_mids)}')
    if not (np.allclose(ds.lat.values + 0.5, lat_mids)
            and np.allclose(ds.lon.values + 0.5, lon_mids)):
        raise ValueError(f'{path}: lat/lon do not line up with processor\'s 1° grid')


def region_mask(shape, mask_file=None):
    """GRE_mask.npy padded onto the data grid (same recipe as greenland.ipynb)."""
    m = np.load(Path(mask_file) if mask_file else MASK_FILE)
    n_pad = shape[0] - m.shape[0]
    if n_pad % 2:
        raise ValueError('asymmetric padding needed — check the mask lat bounds')
    if m.shape[1] != shape[1]:
        raise ValueError(f'mask has {m.shape[1]} lons, grid has {shape[1]}')
    return np.pad(m, ((n_pad // 2, n_pad // 2), (0, 0)), constant_values=0).astype(bool)


# ── the one view processor does not already draw ─────────────────────────────
def create_region_plot(
    data,
    output_path,
    count_mask,
    title,
    cbar_label,
    central_lat=72,
    central_lon=-40,
    extent=(-75, -10, 50, 90),
    vmin=None,
    vmax=None,
    cmap='inferno',
    save=True
):
    """Orthographic close-up on a region — the Greenland plot from greenland.ipynb,
    with processor's hatching and colorbar so it matches the polar maps."""
    mpl.rcParams['hatch.linewidth'] = 0.3
    lon2d, lat2d = np.meshgrid(lon_mids, lat_mids)

    plt.figure(figsize=(9, 9))
    ax = plt.axes(projection=ccrs.Orthographic(central_latitude=central_lat,
                                               central_longitude=central_lon))
    ax.set_extent(list(extent), crs=ccrs.PlateCarree())

    mesh = ax.pcolormesh(lon2d, lat2d, data, transform=ccrs.PlateCarree(),
                         cmap=cmap, vmin=vmin, vmax=vmax, shading='auto')
    ax.contourf(lon2d, lat2d, count_mask.astype(float), levels=[0.5, 1.5],
                hatches=['...'], colors='none', transform=ccrs.PlateCarree())

    ax.coastlines(linewidth=0.6)
    ax.add_feature(cfeature.BORDERS, linewidth=0.5)
    gl = ax.gridlines(draw_labels=True, linewidth=0.5, alpha=0.5)
    gl.right_labels = False
    gl.top_labels = False

    ax.set_title(title, fontsize=17)
    cbar = plt.colorbar(mesh, shrink=0.7, pad=0.05, aspect=30)
    cbar.set_label(cbar_label, fontsize=15, labelpad=15)
    if vmin is not None and vmax is not None:
        cbar.set_ticks(np.linspace(vmin, vmax, 5))
    cbar.ax.tick_params(labelsize=12)

    if save:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f'Saved: {output_path}')  


# ── one call per map ─────────────────────────────────────────────────────────
def make_view(sat=1, year=2025, month=None, season=None, channel=12, stat='mean',
              view='north', out_dir=None, vmin=None, vmax=None, cmap=None,
              min_count=None, data_dir=None, mask_file=None, allow_partial=False,
              filename=None, save=True):
    """Render one map and return the path it was written to.

    sat        1 or 2
    year       2025 or 25
    month      1-12; or leave it out and give a season instead
    season     'DJF' | 'MAM' | 'JJA' | 'SON', labelled by the year it ends in
    channel    spectral index 0-62 (the maps in processor use 12, 24, 30, 32)
    stat       'mean' | 'min' | 'max' | 'std' | 'count'
    view       'north' | 'south' | 'global' | 'greenland'
    vmin/vmax  None auto-scales to the 2nd/98th percentile of what is drawn
    min_count  hatch cells with fewer than this many observations; None hatches
               nothing.  (processor's own main() hatches the cells ABOVE its
               threshold instead — this way round marks the thin sampling.)
    """
    if view not in VIEWS:
        raise ValueError(f'view must be one of {sorted(VIEWS)} — got {view!r}')
    spec = VIEWS[view]

    months, period_label, tag = resolve_period(year, month, season)
    field, count, wl, used = load_field(sat, channel, stat, months,
                                        data_dir=data_dir, allow_partial=allow_partial)

    var_name, stat_title, default_cmap, cbar_label = STATS[stat]

    # restrict to the region the view is about, if it has one
    if spec.get('mask') == 'greenland':
        keep = region_mask(field.shape, mask_file)
        field = np.where(keep, field, np.nan)
        count = np.where(keep, count, 0)

    if vmin is None or vmax is None:
        lo, hi = _auto_limits(field, stat)
        vmin = lo if vmin is None else vmin
        vmax = hi if vmax is None else vmax

    # hatch the thinly-sampled cells; an empty mask draws nothing
    count_mask = (count < min_count) if min_count else np.zeros(field.shape, bool)

    wl_text = f'{wl:.2f} µm' if np.isfinite(wl) else 'wavelength n/a'
    how = '' if len(used) == 1 else f'  ({len(used)} months)'
    title = (f'Sat{sat} ch{channel} · {wl_text} · {stat_title}\n'
             f'{spec["name"]} — {period_label}{how}')

    out_dir = Path(out_dir) if out_dir else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    name = filename or f'sat{sat}_{tag}_ch{channel}_{stat}_{view}.png'
    out_path = out_dir / name

    common = dict(vmin=vmin, vmax=vmax, cmap=cmap or default_cmap,
                  title=title, cbar_label=cbar_label, save=save)

    if spec['kind'] == 'pole':
        create_orthographic_plot(field, stat, spec['pole'], wl, str(out_path),
                                 count_mask, f'Sat{sat}', period_label, **common)
    elif spec['kind'] == 'global':
        create_global_plot(field, stat, wl, str(out_path), count_mask,
                           f'Sat{sat}', period_label, **common)
    else:
        create_region_plot(field, str(out_path), count_mask,
                           central_lat=spec['central_lat'],
                           central_lon=spec['central_lon'],
                           extent=spec['extent'], **common)
    return out_path


def _auto_limits(field, stat):
    """Robust colour limits — the 2nd/98th percentile of the cells actually drawn.

    Radiance spans orders of magnitude across the 63 channels, so a fixed scale
    like processor's per-channel table cannot carry over here.
    """
    v = field[np.isfinite(field)]
    if v.size == 0:
        return 0.0, 1.0
    lo, hi = np.percentile(v, [2, 98])
    if stat in ('std', 'count'):
        lo = 0.0
    if hi <= lo:
        hi = lo + (abs(lo) * 0.1 or 1.0)
    return float(lo), float(hi)


# ── CLI ──────────────────────────────────────────────────────────────────────
def _print_inventory(data_dir=None):
    """Months on disk and the channel wavelengths — per satellite, since the two
    instruments do not put their channels at the same wavelengths."""
    for sat in (1, 2):
        avail = available_months(sat, data_dir)
        if not avail:
            print(f'sat{sat}: nothing on disk')
            print()
            continue
        print(f'sat{sat}: {len(avail)} months, '
              f'{avail[0][0]}-{avail[0][1]:02d} → {avail[-1][0]}-{avail[-1][1]:02d}')
        for y in sorted({y for y, _ in avail}):
            got = sorted(m for yy, m in avail if yy == y)
            print(f'   {y}: ' + ' '.join(MONTH_ABBR[m - 1] for m in got))

        wl = xr.open_zarr(month_file(*avail[0], sat, data_dir)).wavelength.values
        print(f'   channels 0-{len(wl) - 1} (wavelength, µm):')
        for i in range(0, len(wl), 8):
            print('      ' + '  '.join(
                f'{c:2d}:{wl[c]:6.2f}' if np.isfinite(wl[c]) else f'{c:2d}:   n/a'
                for c in range(i, min(i + 8, len(wl)))))
        print()


def main():
    p = argparse.ArgumentParser(
        description='Generate map views from the gridded zarr months in ../data',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--sat', type=int, default=1, choices=[1, 2], help='satellite')
    p.add_argument('--year', type=int, default=2025, help='year (2025 or 25)')
    p.add_argument('--month', type=int, choices=range(1, 13), metavar='1-12',
                   help='calendar month; omit it to use --season')
    p.add_argument('--season', choices=sorted(SEASON_MONTHS),
                   help='season, labelled by the year it ends in (DJF 2025 = Dec 2024-Feb 2025)')
    p.add_argument('--channel', type=int, nargs='+', default=[12],
                   help='spectral channel index/indices')
    p.add_argument('--stat', nargs='+', default=['mean'], choices=sorted(STATS),
                   help='statistic(s) to map')
    p.add_argument('--view', nargs='+', default=['north'], choices=sorted(VIEWS),
                   help='view(s) to draw')
    p.add_argument('--out-dir', default=str(OUT_DIR), help='where the PNGs go')
    p.add_argument('--vmin', type=float, help='colour scale minimum (auto if unset)')
    p.add_argument('--vmax', type=float, help='colour scale maximum (auto if unset)')
    p.add_argument('--cmap', help='colormap (per-statistic default if unset)')
    p.add_argument('--min-count', type=int,
                   help='hatch cells with fewer observations than this')
    p.add_argument('--data-dir', default=str(DATA_DIR), help='directory of the zarr stores')
    p.add_argument('--allow-partial', action='store_true',
                   help='draw a season even if some of its months are missing')
    p.add_argument('--list', action='store_true',
                   help='print the months on disk and the channel wavelengths, then exit')
    args = p.parse_args()

    if args.list:
        _print_inventory(args.data_dir)
        return

    if args.month is None and args.season is None:
        p.error('give --month or --season')
    if args.month is not None and args.season is not None:
        p.error('give --month or --season, not both')

    for channel in args.channel:
        for stat in args.stat:
            for view in args.view:
                make_view(sat=args.sat, year=args.year, month=args.month,
                          season=args.season, channel=channel, stat=stat, view=view,
                          out_dir=args.out_dir, vmin=args.vmin, vmax=args.vmax,
                          cmap=args.cmap, min_count=args.min_count,
                          data_dir=args.data_dir, allow_partial=args.allow_partial)


if __name__ == '__main__':
    main()

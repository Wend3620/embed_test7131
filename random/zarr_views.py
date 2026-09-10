#!/usr/bin/env python3
"""
Map views straight off the gridded months in ../data.

Two products, same 1° global grid, same mean/std/count/min/max per cell:

  radiance  ``sat{#}_{mmyy}.zarr`` — spectral radiance, all 63 channels.
            ``ds.lat``/``ds.lon`` are the bin *edges*, so the cell centres are
            processor's ``lat_mids``/``lon_mids``.
  bt        ``BT/sat{#}_{mmyy}_ch{n}.nc`` — brightness temperature, one file per
            channel, only 12 / 24 / 30 / 32.  Its coords are already the centres.

Pick a product, a satellite, a period (one month, or a season), a statistic and
a channel; the 180×360 field goes to processor's plotting functions, so these
maps come out looking like the ones built from the raw granules.

Output lands under the out-dir laid out the way the viewer reads it — see
view_path() — so the tree can be copied straight into public/:

    sr_pics/month_plots/1225/sat1_12_2025_gr_spec12_mean.webp
    pics/season_plots/JJA25/sat1_JJA_2025_np_ch12_std.webp

    # one month, north pole
    python zarr_views.py --sat 1 --year 2025 --month 1 --channel 12 --stat mean

    # a season, several views and statistics at once
    python zarr_views.py --sat 2 --year 2025 --season DJF --channel 24 \
        --stat mean std --view north greenland

    # the same map in brightness temperature
    python zarr_views.py --product bt --sat 1 --year 2025 --month 1 --channel 12

    # straight into the viewer's assets
    python zarr_views.py --sat 1 --year 2025 --month 12 --view north south global \
        --channel 12 24 30 32 --stat mean min max std --out-dir ../public

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

STATS = ('mean', 'min', 'max', 'std', 'count')

# count is about sampling, not the quantity, so it keeps its own colormap in
# both products; every other statistic takes the product's cmap below.
COUNT_CMAP = 'gist_heat_r'

PRODUCTS = {
    'radiance': dict(
        quantity='Spectral Radiance',      # for the title
        cbar_quantity='Spectral radiance',  # for the colorbar
        units=RADIANCE_UNITS,
        cmap='viridis',
        pics_dir='sr_pics',                 # where the viewer looks for it
        channel_tag='spec',                 # sat1_12_2025_np_spec12_mean.webp
        channels=None,                      # all 63
        vars={'mean':  'spectral_radiance',
              'min':   'spectral_radiance_min',
              'max':   'spectral_radiance_max',
              'std':   'spectral_radiance_std',
              'count': 'spectral_radiance_count'},
    ),
    'bt': dict(
        quantity='Brightness Temperature',
        cbar_quantity='Brightness temperature',
        units='K',
        cmap='inferno',
        pics_dir='pics',
        channel_tag='ch',                   # sat1_12_2025_np_ch12_mean.webp
        channels=(12, 24, 30, 32),          # the only ones gridded to BT
        vars={'mean':  'mean_tb',
              'min':   'min_tb',
              'max':   'max_tb',
              'std':   'std_tb',
              'count': 'count_tb'},
    ),
}

STAT_PREFIX = {'mean': 'Mean', 'min': 'Min', 'max': 'Max', 'std': 'Std of'}


def _stat_labels(product, stat):
    """(title text, colorbar label) for one statistic of one product."""
    p = PRODUCTS[product]
    if stat == 'count':
        return 'Observation Count', 'Observations per cell'
    unit = p['units']
    cbar = f'σ ({unit})' if stat == 'std' else f'{p["cbar_quantity"]} ({unit})'
    return f'{STAT_PREFIX[stat]} {p["quantity"]}', cbar


def _cmap_for(product, stat):
    return COUNT_CMAP if stat == 'count' else PRODUCTS[product]['cmap']


def _check_request(product, stat, channel):
    if product not in PRODUCTS:
        raise ValueError(f'product must be one of {sorted(PRODUCTS)} — got {product!r}')
    if stat not in STATS:
        raise ValueError(f'stat must be one of {list(STATS)} — got {stat!r}')
    allowed = PRODUCTS[product]['channels']
    if allowed is not None and channel not in allowed:
        raise ValueError(f'{product}: channel must be one of {list(allowed)} — '
                         f'got {channel}')


# view -> how to draw it.  'pole' and 'global' go to processor; 'region' is the
# orthographic close-up from greenland.ipynb.
# 'code' is the viewer's abbreviation for the view, straight from LONGNAME.proj
# in src/App.tsx.
VIEWS = {
    'north':     dict(kind='pole', pole='north', name='North Pole', code='np'),
    'south':     dict(kind='pole', pole='south', name='South Pole', code='sp'),
    'global':    dict(kind='global', name='Global', code='gb'),
    'greenland': dict(kind='region', name='Greenland', mask='greenland', code='gr',
                      central_lat=72, central_lon=-40,
                      extent=(-60, -20, 55, 85)),
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


def month_file(year, month, sat=1, data_dir=None, product='radiance', channel=None):
    """Path to one month of one product.  Radiance keeps every channel in a
    single zarr per month; BT is a NetCDF per month AND channel."""
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    stem = f'sat{sat}_{month:02d}{_full_year(year) % 100:02d}'
    if product == 'bt':
        if channel is None:
            raise ValueError('BT files are per channel — pass channel=')
        return data_dir / 'BT' / f'{stem}_ch{channel}.nc'
    return data_dir / f'{stem}.zarr'


def available_months(sat=1, data_dir=None, product='radiance', channel=None):
    """Sorted [(year, month), ...] on disk for one satellite (and, for BT, one
    channel — the channels are gridded independently of each other)."""
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    if product == 'bt':
        if channel is None:
            raise ValueError('BT files are per channel — pass channel=')
        paths = (data_dir / 'BT').glob(f'sat{sat}_*_ch{channel}.nc')
        pattern = rf'sat{sat}_(\d{{2}})(\d{{2}})_ch{channel}'
    else:
        paths = data_dir.glob(f'sat{sat}_*.zarr')
        pattern = rf'sat{sat}_(\d{{2}})(\d{{2}})'
    found = []
    for p in paths:
        m = re.fullmatch(pattern, p.stem)
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


def view_path(sat=1, year=2025, month=None, season=None, channel=12, stat='mean',
              view='north', product='radiance', ext='webp'):
    """Where one map goes, relative to the output root — the layout the viewer
    reads, built the same way src/App.tsx builds it:

        {pics_dir}/{mode}_plots/{period}/sat{#}_{when}_{YYYY}_{proj}_{tag}{ch}_{stat}.{ext}

        sr_pics/month_plots/1225/sat1_12_2025_gr_spec12_mean.webp
        pics/season_plots/JJA25/sat1_JJA_2025_np_ch12_std.webp

    Note the month appears twice in two shapes: zero-padded with the 2-digit
    year in the directory (1225), bare in the filename (12) — that is what
    App.tsx does, so it is what we write.
    """
    if product not in PRODUCTS:
        raise ValueError(f'product must be one of {sorted(PRODUCTS)} — got {product!r}')
    if view not in VIEWS:
        raise ValueError(f'view must be one of {sorted(VIEWS)} — got {view!r}')

    _, _, period = resolve_period(year, month, season)     # 1225 / DJF25
    mode = 'month' if month is not None else 'season'
    when = str(int(month)) if month is not None else str(season).upper()
    p = PRODUCTS[product]

    name = (f'sat{sat}_{when}_{_full_year(year)}_{VIEWS[view]["code"]}_'
            f'{p["channel_tag"]}{channel}_{stat}.{ext}')
    return Path(p['pics_dir']) / f'{mode}_plots' / period / name


def missing_months(months, sat=1, data_dir=None, product='radiance', channel=None):
    """['2024-12', ...] for requested months with no store on disk."""
    return [f'{y}-{m:02d}' for y, m in months
            if not month_file(y, m, sat, data_dir, product, channel).exists()]


# ── cells → one field on the 1° grid ─────────────────────────────────────────
def load_field(sat, channel, stat, months, data_dir=None, allow_partial=False,
               product='radiance'):
    """(field, count, wavelength, months_used) for one statistic on the 1° grid.

    Months pool the way the cells themselves were pooled: every cell already
    holds a mean/std/count over its own observations, so

        n = Σᵢ nᵢ,   μ = Σᵢ nᵢmᵢ / n,   σ² = Σᵢ nᵢ(sᵢ² + mᵢ²)/n − μ²

    and min/max simply take the extreme across the months.  One month is the
    same arithmetic with a single term.  A season whose months are not all on
    disk raises unless allow_partial — averaging over whatever happens to be
    there would quietly change what the map means.
    """
    _check_request(product, stat, channel)

    absent = missing_months(months, sat, data_dir, product, channel)
    present = [(y, m) for y, m in months
               if f'{y}-{m:02d}' not in absent]
    if absent and not allow_partial:
        raise FileNotFoundError(
            f'sat{sat} {product} ch{channel}: no data for {", ".join(absent)} — '
            f'refusing an incomplete period (pass allow_partial=True to override)')
    if not present:
        raise FileNotFoundError(f'sat{sat} {product} ch{channel}: '
                                f'none of the requested months are on disk')
    if absent:
        print(f'  ! averaging without {", ".join(absent)}')

    n_tot = sum_nm = sum_nsq = None      # count-weighted accumulators
    extreme = None                       # running min/max, for those stats
    wavelengths = []

    for y, m in present:
        fields, wl = _open_month(y, m, sat, channel, product, data_dir)
        wavelengths.append(wl)

        n, mean, std = fields['count'], fields['mean'], fields['std']

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
            v = np.where(good, fields[stat], np.nan)
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


def _open_month(year, month, sat, channel, product, data_dir=None):
    """(statistics, wavelength) for one month of one product.

    The five statistics come back as plain arrays under the common names, so
    everything downstream is blind to which product it is looking at.
    """
    f = month_file(year, month, sat, data_dir, product, channel)
    if product == 'bt':
        ds = xr.open_dataset(f)
        wl = float(ds.attrs.get('wavelength', np.nan))
        lat, lon = ds.lat.values, ds.lon.values            # already cell centres
    else:
        ds = xr.open_zarr(f).isel(spectral=channel)
        wl = float(ds.wavelength.values)
        lat, lon = ds.lat.values + 0.5, ds.lon.values + 0.5   # coords are bin edges
    _check_grid(lat, lon, f)
    return ({k: ds[v].values.astype('float64')
             for k, v in PRODUCTS[product]['vars'].items()}, wl)


def _check_grid(lat, lon, path):
    """Cell centres must be the grid processor draws on."""
    if (len(lat), len(lon)) != (len(lat_mids), len(lon_mids)):
        raise ValueError(f'{path}: grid is {len(lat)}x{len(lon)}, '
                         f'processor plots {len(lat_mids)}x{len(lon_mids)}')
    if not (np.allclose(lat, lat_mids) and np.allclose(lon, lon_mids)):
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
    cmap='viridis',
    pil_kwargs=None,
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
        plt.savefig(output_path, dpi=150, bbox_inches='tight',
                    **({'pil_kwargs': pil_kwargs} if pil_kwargs else {}))
        plt.close()
        print(f'Saved: {output_path}')  


# ── one call per map ─────────────────────────────────────────────────────────
def make_view(sat=1, year=2025, month=None, season=None, channel=12, stat='mean',
              view='north', product='radiance', out_dir=None, vmin=None, vmax=None,
              cmap=None, min_count=None, data_dir=None, mask_file=None,
              allow_partial=False, filename=None, ext='webp', quality=None,
              save=True):
    """Render one map and return the path it was written to.

    sat        1 or 2
    year       2025 or 25
    month      1-12; or leave it out and give a season instead
    season     'DJF' | 'MAM' | 'JJA' | 'SON', labelled by the year it ends in
    channel    spectral index; 0-62 for radiance, 12/24/30/32 for bt
    stat       'mean' | 'min' | 'max' | 'std' | 'count'
    view       'north' | 'south' | 'global' | 'greenland'
    product    'radiance' (the zarr months) or 'bt' (the NetCDFs in data/BT)
    ext        image format; 'webp' is what the viewer serves
    quality    webp/jpg encoder quality; None keeps webp lossless
    filename   escape hatch — put the image straight in out_dir under this name
               instead of the viewer's {pics_dir}/{mode}_plots/{period}/ layout
    vmin/vmax  None auto-scales to the 2nd/98th percentile of what is drawn
    min_count  hatch cells with fewer than this many observations; None hatches
               nothing.  (processor's own main() hatches the cells ABOVE its
               threshold instead — this way round marks the thin sampling.)
    """
    if view not in VIEWS:
        raise ValueError(f'view must be one of {sorted(VIEWS)} — got {view!r}')
    spec = VIEWS[view]

    months, period_label, _ = resolve_period(year, month, season)
    field, count, wl, used = load_field(sat, channel, stat, months, data_dir=data_dir,
                                        allow_partial=allow_partial, product=product)

    stat_title, cbar_label = _stat_labels(product, stat)

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
    out_path = out_dir / (filename or view_path(sat, year, month, season, channel,
                                                stat, view, product, ext))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    common = dict(vmin=vmin, vmax=vmax, cmap=cmap or _cmap_for(product, stat),
                  title=title, cbar_label=cbar_label, save=save,
                  pil_kwargs=_encoder(out_path.suffix.lstrip('.').lower(), quality))

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


def _encoder(ext, quality=None):
    """Pillow options for one format.

    webp defaults to LOSSLESS: these are colour-coded data figures read against
    a colorbar, and lossy webp at Pillow's default moves single pixels by up to
    ~90/255.  Lossless still lands at about half the size of the equivalent PNG.
    Pass quality=85-95 for the smaller lossy files if the size matters more.
    """
    if ext == 'webp':
        return {'quality': quality, 'method': 6} if quality else {'lossless': True}
    if ext in ('jpg', 'jpeg'):
        return {'quality': quality or 95}
    return None


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
    """Months on disk per satellite and product, and the channel wavelengths —
    the two instruments do not put their channels at the same wavelengths."""
    def _span(avail):
        return (f'{len(avail)} months, {avail[0][0]}-{avail[0][1]:02d} → '
                f'{avail[-1][0]}-{avail[-1][1]:02d}')

    for sat in (1, 2):
        avail = available_months(sat, data_dir)
        if not avail:
            print(f'sat{sat}: no radiance months on disk')
            print()
            continue
        print(f'sat{sat} radiance: {_span(avail)}')
        for y in sorted({y for y, _ in avail}):
            got = sorted(m for yy, m in avail if yy == y)
            print(f'   {y}: ' + ' '.join(MONTH_ABBR[m - 1] for m in got))

        wl = xr.open_zarr(month_file(*avail[0], sat, data_dir)).wavelength.values
        print(f'   channels 0-{len(wl) - 1} (wavelength, µm):')
        for i in range(0, len(wl), 8):
            print('      ' + '  '.join(
                f'{c:2d}:{wl[c]:6.2f}' if np.isfinite(wl[c]) else f'{c:2d}:   n/a'
                for c in range(i, min(i + 8, len(wl)))))

        for ch in PRODUCTS['bt']['channels']:
            bt = available_months(sat, data_dir, product='bt', channel=ch)
            print(f'sat{sat} bt ch{ch}: ' + (_span(bt) if bt else 'nothing on disk'))
        print()


def main():
    p = argparse.ArgumentParser(
        description='Generate map views from the gridded months in ../data '
                    '(spectral radiance, or brightness temperature from data/BT)',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--sat', type=int, default=1, choices=[1, 2], help='satellite')
    p.add_argument('--year', type=int, default=2025, help='year (2025 or 25)')
    p.add_argument('--month', type=int, choices=range(1, 13), metavar='1-12',
                   help='calendar month; omit it to use --season')
    p.add_argument('--season', choices=sorted(SEASON_MONTHS),
                   help='season, labelled by the year it ends in (DJF 2025 = Dec 2024-Feb 2025)')
    p.add_argument('--channel', type=int, nargs='+', default=[12],
                   help='spectral channel index/indices (bt has only 12, 24, 30, 32)')
    p.add_argument('--stat', nargs='+', default=['mean'], choices=sorted(STATS),
                   help='statistic(s) to map')
    p.add_argument('--view', nargs='+', default=['north'], choices=sorted(VIEWS),
                   help='view(s) to draw')
    p.add_argument('--product', default='radiance', choices=sorted(PRODUCTS),
                   help='radiance (the zarr months) or bt (the NetCDFs in data/BT, '
                        'channels 12/24/30/32 only)')
    p.add_argument('--out-dir', default=str(OUT_DIR),
                   help='root of the {pics_dir}/{mode}_plots/{period}/ tree written under it')
    p.add_argument('--ext', default='webp', choices=['webp', 'png', 'jpg', 'pdf', 'svg'],
                   help='image format (webp is what the viewer serves)')
    p.add_argument('--quality', type=int,
                   help='webp/jpg encoder quality 1-100; omit to keep webp lossless')
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
                          product=args.product, out_dir=args.out_dir,
                          ext=args.ext, quality=args.quality,
                          vmin=args.vmin, vmax=args.vmax,
                          cmap=args.cmap, min_count=args.min_count,
                          data_dir=args.data_dir, allow_partial=args.allow_partial)


if __name__ == '__main__':
    main()

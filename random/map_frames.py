"""
Calibrate the quicklook map images for click-to-lat/lon in the viewer.

The maps are saved with bbox_inches='tight', so the map frame's pixel position
shifts with the title and colorbar label widths. This script finds the frame in
every image and writes public/map_frames.json, which src/mapGeo.ts reads:

  views:  per view code (np, sp, gb, gre), the projection and its axes limits
          in projection metres, computed with cartopy the same way the plots are
  groups: "<product>|<view>|<W>x<H>" -> [x0, y0, x1, y1] frame box in image px,
          shared by every image of that size
  files:  "<image path under public/>" -> frame box, only for images whose
          frame disagrees with the rest of their size group

The frame is the bounding box of the largest connected non-white region: the
filled disc / rectangle / Robinson oval with its outline. Titles, tick labels
and the colorbar are separate regions.

Re-run whenever new quicklook images are added:  python3 random/map_frames.py
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

import cartopy.crs as ccrs
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public'
OUT = PUBLIC / 'map_frames.json'
VIEWS = ('np', 'sp', 'gb', 'gre')
NAME_RE = re.compile(r'_(np|sp|gb|gre)_')


# ── projections (must match random/processor.py and the Greenland notebook) ──
def ortho_view(lat0, lon0, extent):
    crs = ccrs.Orthographic(central_longitude=lon0, central_latitude=lat0)
    fig = plt.figure(figsize=(4, 4))
    ax = plt.axes(projection=crs)
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    plt.close(fig)
    return {'proj': 'ortho', 'lat0': lat0, 'lon0': lon0,
            'R': crs.proj4_params['a'], 'xlim': list(xlim), 'ylim': list(ylim)}


def robinson_view():
    crs = ccrs.Robinson(central_longitude=0)
    geo = ccrs.PlateCarree()
    lats = np.arange(-90, 90.01, 0.5)
    # y and half-width (x at lon 180) along each latitude, for the inverse
    y = [crs.transform_point(0, la, geo)[1] for la in lats]
    half = [crs.transform_point(180, la, geo)[0] for la in lats]
    return {'proj': 'robinson',
            'xlim': list(crs.x_limits), 'ylim': list(crs.y_limits),
            'table': {'lat': lats.tolist(), 'y': y, 'half': half}}


# The Greenland maps were not made by any script in this repo (gre1.ipynb's
# Orthographic(72, -40) puts the pole ~30 px off), so their projection was fitted
# to where the labelled gridlines cross the frame of
# bt_pics/month_plots/1225/sat1_12_2025_gre_ch12_mean.webp: 60-15°W meridians on
# the bottom edge, 50/60°N on the sides, 70/80°N on the top. RMS 0.2 px.
GRE_FIT = dict(lat0=70.0, lon0=-42.5,
               m_per_px=4850.251, cx=542.856, cy=607.317,   # projection origin, px
               frame=(88, 156, 997, 1047))                  # that image's frame


def fitted_ortho_view(fit):
    x0, y0, x1, y1 = fit['frame']
    s, cx, cy = fit['m_per_px'], fit['cx'], fit['cy']
    return {'proj': 'ortho', 'lat0': fit['lat0'], 'lon0': fit['lon0'], 'R': 6378137.0,
            # frame edges in projection metres (box is inclusive px, so +1)
            'xlim': [(x0 - cx) * s, (x1 + 1 - cx) * s],
            'ylim': [(cy - (y1 + 1)) * s, (cy - y0) * s]}


def projections():
    return {
        'np': {**ortho_view(90, 0, [-180, 180, 60, 90]), 'latMin': 60},
        'sp': {**ortho_view(-90, 0, [-180, 180, -90, -60]), 'latMax': -60},
        'gb': robinson_view(),
        'gre': fitted_ortho_view(GRE_FIT),
    }


# ── frame detection ─────────────────────────────────────────────────────────
def frame_box(path):
    rgb = np.asarray(Image.open(path).convert('RGB'))
    nonwhite = rgb.min(axis=2) < 220          # inferno's pale yellow still counts
    labels, n = ndimage.label(nonwhite)
    if n == 0:
        return None
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    sl = ndimage.find_objects((labels == sizes.argmax()).astype(np.int32))[0]
    return [sl[1].start, sl[0].start, sl[1].stop - 1, sl[0].stop - 1]


def main():
    images = sorted(p for d in ('bt_pics', 'sr_pics') for kind in ('month_plots', 'season_plots')
                    for p in (PUBLIC / d / kind).rglob('*.webp') if NAME_RE.search(p.name))
    by_group = defaultdict(list)
    failed = []
    for i, p in enumerate(images):
        view = NAME_RE.search(p.name).group(1)
        product = p.relative_to(PUBLIC).parts[0].split('_')[0]   # bt / sr
        w, h = Image.open(p).size
        box = frame_box(p)
        if box is None:
            failed.append(p)
            continue
        by_group[f'{product}|{view}|{w}x{h}'].append((p.relative_to(PUBLIC).as_posix(), box))
        if i % 500 == 0:
            print(f'  {i}/{len(images)}', file=sys.stderr)

    groups, files = {}, {}
    for key, items in sorted(by_group.items()):
        common = Counter(tuple(b) for _, b in items).most_common(1)[0][0]
        groups[key] = list(common)
        odd = [(f, b) for f, b in items if max(abs(a - c) for a, c in zip(b, common)) > 1]
        for f, b in odd:
            files[f] = b
        print(f'{key:24s} {len(items):4d} images  frame {list(common)}'
              + (f'  ({len(odd)} differ)' if odd else ''))

    OUT.write_text(json.dumps({'views': projections(), 'groups': groups, 'files': files},
                              separators=(',', ':')))
    print(f'\n{len(images)} images, {len(groups)} groups, {len(files)} per-file frames, '
          f'{len(failed)} undetected -> {OUT.relative_to(ROOT)}')
    for p in failed:
        print('  no frame:', p.relative_to(PUBLIC))


if __name__ == '__main__':
    main()

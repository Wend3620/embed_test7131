#!/usr/bin/env python3
#--granule-dirs /path/to/sat1_09_24 /path/to/sat1_10_24 #/path/to/sat1_11_24 READ FROM DIRECTORIESS
#--channel 24 #The channel to process: 12, 24, 30, or 32
#--output-base /path/to/output
#--vmin 190 #See line 344
#--vmax 270
#See line 344
"""
Script to generate seasonal plots for North Pole, South Pole, and Global
brightness temperature statistics (mean, min, max, std) for channel 12, 24, 30, or 32.
"""

import glob
import os
import sys
import datetime
import argparse
import copy
from pathlib import Path
import xarray as xr
from scipy.stats import binned_statistic_2d
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
import numpy as np
import netCDF4 as nc
import matplotlib as mpl

# Bin edges and midpoints
lat_edges = np.arange(-90, 91, 1)
lon_edges = np.arange(-180, 181, 1)
lat_mids = lat_edges[:-1] + 0.5
lon_mids = lon_edges[:-1] + 0.5

# Threshold for count mask
THRESHOLD = 1000

# Season definitions
SEASON_MONTHS = {
    'SON': [9, 10, 11],   # Sep-Oct-Nov
    'DJF': [12, 1, 2],    # Dec-Jan-Feb
    'MAM': [3, 4, 5],     # Mar-Apr-May
    'JJA': [6, 7, 8],     # Jun-Jul-Aug
}


def detect_satellite_and_season(granule_dirs):
    """
    Detect satellite and season from directory names.
    Returns satellite (SAT1 or SAT2) and season (SON, DJF, MAM, JJA).
    """
    satellites = set()
    months = []
    
    for granule_dir in granule_dirs:
        # Extract directory name (e.g., 'sat1_09_24' or 'sat2_03_25')
        dir_name = os.path.basename(granule_dir.rstrip('/'))
        
        # Detect satellite (sat1 or sat2)
        if dir_name.startswith('sat1'):
            satellites.add('Sat1')
        elif dir_name.startswith('sat2'):
            satellites.add('Sat2')
        else:
            # Try to detect from filename
            for filename in os.listdir(granule_dir):
                if filename.endswith('.nc'):
                    if 'SAT1' in filename:
                        satellites.add('Sat1')
                    elif 'SAT2' in filename:
                        satellites.add('Sat2')
                    break
        
        # Extract month and year from directory name (e.g., 'sat1_09_24' -> month=09, year=24)
        parts = dir_name.split('_')
        if len(parts) >= 3:
            try:
                month = int(parts[1])
                year = int(parts[2])
                months.append((month, year))
            except ValueError:
                pass
    
    # Determine satellite
    if len(satellites) == 1:
        satellite = satellites.pop()
    elif 'Sat1' in satellites:
        satellite = 'Sat1'  # Default to SAT1 if mixed
    elif 'Sat2' in satellites:
        satellite = 'Sat2'
    else:
        satellite = 'Sat1'  # Default
    
    # Determine season from months
    month_set = set(m[0] for m in months)
    season = None
    
    # First, try to find an exact match where all months belong to one season
    for season_name, season_months in SEASON_MONTHS.items():
        season_month_set = set(season_months)
        if month_set.issubset(season_month_set) and len(month_set) > 0:
            # Check if we have a good match (at least 2 months from the season)
            if len(month_set) >= 2 or len(month_set) == len(season_month_set):
                season = season_name
                break
    
    # If no exact match, try to find if all months belong to one season
    if season is None:
        for season_name, season_months in SEASON_MONTHS.items():
            if month_set.issubset(set(season_months)):
                season = season_name
                break
    
    # If still no match, try to infer from most common months
    if season is None and months:
        month_counts = {}
        for month, _ in months:
            month_counts[month] = month_counts.get(month, 0) + 1
        if month_counts:
            most_common_month = max(month_counts.items(), key=lambda x: x[1])[0]
            
            for season_name, season_months in SEASON_MONTHS.items():
                if most_common_month in season_months:
                    season = season_name
                    break
    
    if season is None:
        season = 'UNKNOWN'
    
    return satellite, season


def get_statistic_display_name(statistic_name):
    """Convert statistic name to display name."""
    names = {
        'mean': 'Mean Brightness Temperature',
        'min': 'Min Brightness Temperature',
        'max': 'Max Brightness Temperature',
        'std': 'Standard Deviation of Brightness Temperature'
    }
    return names.get(statistic_name, statistic_name.capitalize())


def extract_valid_tb_lat_lon(
    granule_path, 
    channel_index=12, 
    pass_direction="both"
):
    """Extract valid brightness temperature, latitude, and longitude from a granule."""
    with nc.Dataset(granule_path, 'r') as ds:
        bt_full = ds.groups['BT']['spectral_BT'][:]
        lat = ds.groups['Geometry']['latitude'][:]
        lon = ds.groups['Geometry']['longitude'][:]
        quality_raw = ds.groups['BT']['BT_quality_flag'][:]
        quality = quality_raw[:, :, channel_index] if quality_raw.ndim == 3 else quality_raw
        
        min_atrack = min(bt_full.shape[0], lat.shape[0], lon.shape[0], quality.shape[0])
        bt = bt_full[:min_atrack, :, channel_index]
        lat = lat[:min_atrack, :]
        lon = lon[:min_atrack, :]
        quality = quality[:min_atrack, :]

        valid_mask = (
            np.isfinite(bt) & np.isfinite(lat) & np.isfinite(lon)
            & np.isin(quality, [0, 1])
        )
        # Get wavelength
        wavelengths = ds.groups['Radiance']['wavelength'][:]  # [xtrack, spectral]
        mean_wavelength = wavelengths[:, channel_index].mean()

        # Filter by pass direction
        pass_type = ds['Geometry']['satellite_pass_type'][:]
        if pass_direction == "ascending":
            direction_mask = pass_type == 1
        elif pass_direction == "descending":
            direction_mask = pass_type == -1
        else:
            direction_mask = np.ones(pass_type.shape, dtype=bool)  # keep all

        # Apply direction mask along the first axis (atrack)
        lat = lat[direction_mask, :]
        lon = lon[direction_mask, :]
        bt = bt[direction_mask, :]
        valid_mask = valid_mask[direction_mask, :]

        return bt[valid_mask], lat[valid_mask], lon[valid_mask], mean_wavelength


def process_granule_directory(granule_dirs, channel_index=12):
    """
    Loops through all NetCDF granules in the directory.
    Collects all valid Tb, lat, lon data into lists.
    
    Parameters:
    -----------
    granule_dirs : list
        List of directories containing granule files
    channel_index : int
        Channel index to extract (default: 12)
    """
    all_tb = []
    all_lat = []
    all_lon = []
    wavelength = []
    
    for granule_dir in granule_dirs:
        for filename in sorted(os.listdir(granule_dir)):
            if filename.endswith(".nc"):
                path = os.path.join(granule_dir, filename)
                try:
                    bt, lat, lon, mean_wavelength = extract_valid_tb_lat_lon(path, channel_index=channel_index)
                    all_tb.append(bt)
                    all_lat.append(lat)
                    all_lon.append(lon)
                    wavelength.append(mean_wavelength)
                except Exception as e:
                    print(f"Failed to process {filename}: {e}")

    # Concatenate arrays
    tb_all = np.concatenate(all_tb)
    lat_all = np.concatenate(all_lat) 
    lon_all = np.concatenate(all_lon) 
    wavelength = np.round(np.mean(wavelength), decimals=2)

    # Mask out unrealistic brightness temperature values
    # Remove values below 100 K and above 500 K
    realistic_mask = (tb_all >= 100) & (tb_all <= 500)
    
    # Apply mask to keep arrays in sync
    tb_all = tb_all[realistic_mask]
    lat_all = lat_all[realistic_mask]
    lon_all = lon_all[realistic_mask]
    
    print(f"Masked out {np.sum(~realistic_mask)} unrealistic values")
    print(f"Remaining data points: {len(tb_all)}")
    print(f"tb_all range: {tb_all.min():.2f} K to {tb_all.max():.2f} K")

    return tb_all, lat_all, lon_all, wavelength


def compute_statistics(tb_all, lat_all, lon_all):
    """Compute mean, min, max, std, and count statistics."""
    mean_tb, _, _, _ = binned_statistic_2d(
        lat_all, lon_all, tb_all,
        statistic='mean',
        bins=[lat_edges, lon_edges]
    )

    count_tb, _, _, _ = binned_statistic_2d(
        lat_all, lon_all, tb_all,
        statistic='count',
        bins=[lat_edges, lon_edges]
    )

    std_tb, _, _, _ = binned_statistic_2d(
        lat_all, lon_all, tb_all,
        statistic='std',
        bins=[lat_edges, lon_edges]
    )

    max_tb, _, _, _ = binned_statistic_2d(
        lat_all, lon_all, tb_all,
        statistic='max',
        bins=[lat_edges, lon_edges]
    )

    min_tb, _, _, _ = binned_statistic_2d(
        lat_all, lon_all, tb_all,
        statistic='min',
        bins=[lat_edges, lon_edges]
    )

    count_mask = (count_tb > THRESHOLD)
    
    return mean_tb, min_tb, max_tb, std_tb, count_mask


def create_orthographic_plot(
    data, 
    statistic_name, 
    pole, 
    wavelength, 
    output_path,
    count_mask,
    satellite,
    season,
    vmin=None,
    vmax=None,
    cmap='inferno'
):
    """
    Create an orthographic projection plot for North or South Pole.
    
    Parameters:
    -----------
    data : array
        2D array of data to plot
    statistic_name : str
        Name of statistic ('mean', 'min', 'max', 'std')
    pole : str
        'north' or 'south'
    wavelength : float
        Wavelength in micrometers
    output_path : str
        Full path to save the plot
    count_mask : array
        2D boolean array for hatching areas with low counts
    satellite : str
        Satellite name (SAT1 or SAT2)
    season : str
        Season name (SON, DJF, MAM, JJA)
    vmin, vmax : float
        Color scale limits
    cmap : str
        Colormap name
    """
    mpl.rcParams['hatch.linewidth'] = 0.3
    
    # Determine projection center and extent based on pole
    if pole == 'north':
        central_lat = 90
        central_lon = 0
        extent = [-180, 180, 60, 90]
        lat_range = np.arange(60, 91, 10)
        lat_label_range = np.arange(70, 90, 10)  # Exclude 90°N
        circle_lats = [70, 80]
        lat_suffix = 'N'
    else:  # south
        central_lat = -90
        central_lon = 0
        extent = [-180, 180, -60, -90]
        lat_range = np.arange(-60, -90, -10)
        lat_label_range = np.arange(-70, -90, -10)
        circle_lats = [-70, -80]
        lat_suffix = 'S'
    
    # Create meshgrid
    lon2d, lat2d = np.meshgrid(lon_mids, lat_mids)
    
    # Create figure and axis
    plt.figure(figsize=(10, 10))
    ax = plt.axes([0, 0, 1, 1], projection=ccrs.Orthographic(
        central_latitude=central_lat, 
        central_longitude=central_lon
    ))
    
    # Plot the data
    # Change the colorbar setting here
    
    mesh = ax.pcolormesh(
        lon2d, lat2d, data,
        cmap=cmap, 
        shading='auto',
        transform=ccrs.PlateCarree(),
        vmin=vmin, 
        vmax=vmax
    )
    
    # Add hatching over areas with low counts
    hatch_overlay = ax.contourf(
        lon2d, lat2d, count_mask.astype(float),
        levels=[0.5, 1.5], 
        hatches=['...'],   
        colors='none',
        transform=ccrs.PlateCarree()
    )
    
    # Add coastlines and features
    ax.coastlines()
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.BORDERS, linewidth=0.5)
    ax.add_feature(cfeature.STATES, linewidth=0.5)
    
    # Add latitude circles
    for lat in circle_lats:
        circle = plt.Circle((0, 0), abs(90 - abs(lat))/30, fill=False, 
                           color='white', alpha=0.5, linestyle=':')
        ax.add_patch(circle)
    
    # Add gridlines
    gl = ax.gridlines(draw_labels=True, linewidth=1, color='white', alpha=0.7)
    gl.xlabel_style = {'size': 11, 'color': 'black', 'weight': 'bold'}
    gl.ylabel_style = {'size': 11, 'color': 'black', 'weight': 'bold'}
    gl.xlocator = plt.FixedLocator(np.arange(-180, 181, 60))
    gl.ylocator = plt.FixedLocator(lat_range)
    
    # Add latitude labels
    for lat in lat_label_range:
        proj_coords = ax.projection.transform_point(0, lat, ccrs.PlateCarree())
        if ax.get_xlim()[0] <= proj_coords[0] <= ax.get_xlim()[1]:
            ax.text(
                0, lat, f"{abs(lat)}°{lat_suffix}",
                transform=ccrs.PlateCarree(),
                ha='left', va='center',
                fontsize=11, fontweight='bold',
                color='white',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.7)
            )
    
    # Set circular boundary
    theta = np.linspace(0, 2*np.pi, 100)
    center, radius = [0.5, 0.5], 0.5
    verts = np.vstack([np.sin(theta), np.cos(theta)]).T
    circle = mpl.path.Path(verts*radius+center)
    ax.set_boundary(circle, transform=ax.transAxes)
    
    # Set title
    pole_name = "North" if pole == 'north' else "South"
    statistic_display = get_statistic_display_name(statistic_name)
    ax.set_title(f"{satellite} {wavelength}µm {statistic_display}\n{pole_name} Pole - {season}", 
                 fontsize=17)
    
    # Add colorbar
    cbar = plt.colorbar(mesh, shrink=0.7, pad=0.05, aspect=30)
    cbar.set_label("Brightness Temperature (K)", fontsize=15, labelpad=15)
    if vmin is not None and vmax is not None:
        cbar.set_ticks(np.linspace(vmin, vmax, 5))  # 5 evenly spaced ticks including vmin and vmax
    cbar.ax.tick_params(labelsize=12)
    
    # Save plot
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")

def create_global_plot(
    data,
    statistic_name,
    wavelength,
    output_path,
    count_mask,
    satellite,
    season,
    vmin=None,
    vmax=None,
    cmap='inferno'
):
    """
    Create a global Robinson projection plot.
    
    Parameters:
    -----------
    data : array
        2D array of data to plot
    statistic_name : str
        Name of statistic ('mean', 'min', 'max', 'std')
    wavelength : float
        Wavelength in micrometers
    output_path : str
        Full path to save the plot
    count_mask : array
        2D boolean array for hatching areas with low counts
    satellite : str
        Satellite name (SAT1 or SAT2)
    season : str
        Season name (SON, DJF, MAM, JJA)
    vmin, vmax : float
        Color scale limits
    cmap : str
        Colormap name
    """
    mpl.rcParams['hatch.linewidth'] = 0.3
    
    # Create meshgrid
    lon2d, lat2d = np.meshgrid(lon_mids, lat_mids)
    
    # Create figure and axis
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.Robinson(central_longitude=0))
    
    # Plot the data
    mesh = ax.pcolormesh(
        lon2d, lat2d, data,
        cmap=cmap,
        shading='auto',
        transform=ccrs.PlateCarree(),
        vmin=vmin,
        vmax=vmax
    )
    
    # Add hatching over areas with low counts
    hatch_overlay = ax.contourf(
        lon2d, lat2d, count_mask.astype(float),
        levels=[0.5, 1.5],
        hatches=['...'],
        colors='none',
        transform=ccrs.PlateCarree()
    )
    
    # Add coastlines and features
    ax.coastlines()
    ax.add_feature(cfeature.BORDERS, linewidth=0.5)
    
    # Global gridlines for Robinson projection
    gl = ax.gridlines(
        draw_labels=False,
        linewidth=1,
        color='gray',
        alpha=0.7
    )
    gl.xlocator = plt.FixedLocator(np.arange(-150, 181, 60))
    gl.ylocator = plt.FixedLocator(np.arange(-90, 91, 30))
    
    # Setup formatters
    lon_formatter = LongitudeFormatter(degree_symbol='°', dateline_direction_label=True)
    lat_formatter = LatitudeFormatter(degree_symbol='°')
    
    # Label positions
    lons = np.arange(-150, 181, 60)
    lats = np.arange(-60, 61, 30)  # usually cleaner than including ±90 on Robinson
    
    def _data_to_axes_coords(ax, x, y):
        """Convert data coords -> axes coords (0..1)."""
        disp = ax.transData.transform((x, y))
        return ax.transAxes.inverted().transform(disp)
    
    # Bottom longitude labels
    label_lat = -85
    for lon in lons:
        x, y = ax.projection.transform_point(lon, label_lat, ccrs.PlateCarree())
        xa, ya = _data_to_axes_coords(ax, x, y)
        ax.text(
            xa, ya - 0.03,
            lon_formatter(lon),
            transform=ax.transAxes,
            ha='center', va='top',
            fontsize=9, color='black',
            clip_on=False
        )
    
    # Left latitude labels
    label_lon = -175
    for lat in lats:
        x, y = ax.projection.transform_point(label_lon, lat, ccrs.PlateCarree())
        xa, ya = _data_to_axes_coords(ax, x, y)
        ax.text(
            xa - 0.03, ya,
            lat_formatter(lat),
            transform=ax.transAxes,
            ha='right', va='center',
            fontsize=9, color='black',
            clip_on=False
        )
    
    # Set title
    statistic_display = get_statistic_display_name(statistic_name)
    ax.set_title(f"{satellite} {wavelength}µm {statistic_display}\n{season}",
                 fontsize=17)
    
    # Add colorbar
    cbar = plt.colorbar(mesh, shrink=0.8, pad=0.05, aspect=30, orientation='horizontal')
    cbar.set_label("Brightness Temperature (K)", fontsize=15, labelpad=15)
    if vmin is not None and vmax is not None:
        cbar.set_ticks(np.linspace(vmin, vmax, 5))  # 5 evenly spaced ticks including vmin and vmax
    cbar.ax.tick_params(labelsize=12)
    
    # Save plot
    plt.savefig(output_path, dpi=150, bbox_inches='tight', pad_inches=0.1)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate seasonal plots for North Pole, South Pole, and Global brightness temperature statistics'
    )
    parser.add_argument(
        '--granule-dirs',
        nargs='+',
        required=True,
        help='List of granule directories to process'
    )
    parser.add_argument(
        '--output-base',
        default= '/home/wdu36/research/plots/seasonal_plots', #'/home/lepique/research/plots/seasonal_plots',
        help='Base directory for output plots'
    )

    parser.add_argument(
        '--channel',
        type=int,
        default=12,
        choices=[12, 24, 30, 32],
        help='Channel index to process (12, 24, 30, or 32, default: 12)'
    )
    
    args = parser.parse_args()
    
    # Create output directories based on channel
    channel_str = f'ch{args.channel}'
    np_dir = os.path.join(args.output_base, f'np_{channel_str}')
    sp_dir = os.path.join(args.output_base, f'sp_{channel_str}')
    global_dir = os.path.join(args.output_base, f'global_{channel_str}')
    os.makedirs(np_dir, exist_ok=True)
    os.makedirs(sp_dir, exist_ok=True)
    os.makedirs(global_dir, exist_ok=True)
    
    # Detect satellite and season from directory names
    print("Detecting satellite and season from directory names...")
    satellite, season = detect_satellite_and_season(args.granule_dirs)
    print(f"Detected: {satellite}, Season: {season}")
    
    print(f"Processing granule directories for channel {args.channel}...")
    tb_all, lat_all, lon_all, wavelength = process_granule_directory(args.granule_dirs, channel_index=args.channel)
    
    print("Computing statistics...")
    mean_tb, min_tb, max_tb, std_tb, count_mask = compute_statistics(tb_all, lat_all, lon_all)
    
    # Define plot configurations based on channel
    if args.channel == 24:
        # Channel 24: vmin=190, vmax=270 for mean/min/max
        plot_configs = [
            ('mean', mean_tb, 190, 270, 'inferno'),
            ('min', min_tb, 190, 270, 'inferno'),
            ('max', max_tb, 190, 270, 'inferno'),
            ('std', std_tb, 0, 10, 'viridis'),
        ]
    elif args.channel == 30:
        # Channel 30: vmin=185, vmax=265 for mean/min/max
        plot_configs = [
            ('mean', mean_tb, 185, 265, 'inferno'),
            ('min', min_tb, 185, 265, 'inferno'),
            ('max', max_tb, 185, 265, 'inferno'),
            ('std', std_tb, 0, 10, 'viridis'),
        ]
    elif args.channel == 32:
        # Channel 32: vmin=190, vmax=260 for mean/min/max
        plot_configs = [
            ('mean', mean_tb, 190, 260, 'inferno'),
            ('min', min_tb, 190, 260, 'inferno'),
            ('max', max_tb, 190, 260, 'inferno'),
            ('std', std_tb, 0, 10, 'viridis'),
        ]
    else:  # channel 12
        # Channel 12: vmin=200, vmax=300 for mean/min/max
        plot_configs = [
            ('mean', mean_tb, 200, 300, 'inferno'),
            ('min', min_tb, 200, 300, 'inferno'),
            ('max', max_tb, 200, 300, 'inferno'),
            ('std', std_tb, 0, 12, 'viridis'),
        ]
    
    # Generate plots for both poles and global
    for statistic_name, data, vmin, vmax, cmap in plot_configs:
        # North Pole
        np_output = os.path.join(np_dir, f'{satellite.lower()}_{season}_np_{channel_str}_{statistic_name}.png')
        create_orthographic_plot(
            data, statistic_name, 'north', wavelength, np_output, count_mask,
            satellite, season, vmin=vmin, vmax=vmax, cmap=cmap
        )
        
        # South Pole
        sp_output = os.path.join(sp_dir, f'{satellite.lower()}_{season}_sp_{channel_str}_{statistic_name}.png')
        create_orthographic_plot(
            data, statistic_name, 'south', wavelength, sp_output, count_mask,
            satellite, season, vmin=vmin, vmax=vmax, cmap=cmap
        )
        
        # Global
        global_output = os.path.join(global_dir, f'{satellite.lower()}_{season}_global_{channel_str}_{statistic_name}.png')
        create_global_plot(
            data, statistic_name, wavelength, global_output, count_mask,
            satellite, season, vmin=vmin, vmax=vmax, cmap=cmap
        )
    
    print("All plots generated successfully!")


if __name__ == '__main__':
    main()

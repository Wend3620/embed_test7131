import os

from pathlib import Path
import xarray as xr
from scipy.stats import binned_statistic_2d

import numpy as np
import netCDF4 as nc
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
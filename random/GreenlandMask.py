"""
PREFIRE All-Channels Emissivity Seasonal Comparison
Permanent Land Ice Analysis with 3-Step Filtering

STEP 1: Geographic boundary (Natural Earth accurate polygons)
STEP 2: Elevation ≥500m (applied during merge)
STEP 3: Surface type = permanent land ice (index 3, flag 4)
        Applied during emissivity calculation
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import netCDF4


def load_prefire_all_channels_data(p_fpath, sat_num):
    """
    Load PREFIRE L3 data for ALL channels
    INCLUDES ELEVATION DATA
    """
    print(f"Loading PREFIRE L3 all-channel data from: {os.path.basename(p_fpath)}")
    
    with netCDF4.Dataset(p_fpath, 'r') as ds:
        sfc_group = ds.groups["Sfc-Sorted"]
        
        lat2d = sfc_group.variables["latitude"][...]
        lon2d = sfc_group.variables["longitude"][...]
        
        wavelength = sfc_group.variables["wavelength"][...]
        wavelength_mean = np.mean(wavelength, axis=0)
        
        print(f"  SAT{sat_num}: All {len(wavelength_mean)} channels")
        print(f"  Wavelength range: {np.min(wavelength_mean):.3f} to {np.max(wavelength_mean):.3f} μm")
        
        surface_types = sfc_group.variables["surface_type_for_sorting"][...]
        surface_meanings = sfc_group.variables["surface_type_for_sorting"].flag_meanings
        
        surface_type_names = {}
        for i, meaning in enumerate(surface_meanings.split(', ')):
            parts = meaning.strip().split('] ')
            number = int(parts[0].replace('[', ''))
            name = parts[1]
            surface_type_names[number] = name
        
        emis_sum_all = sfc_group.variables["sp_emis_sum"][...]
        emis_count_all = sfc_group.variables["sp_emis_count"][...]
        
        emis_sum_all = np.where(emis_sum_all < 0, 0.0, emis_sum_all)
        emis_count_all = np.where(emis_count_all < 0, 0, emis_count_all)
        
        emis_count_all = emis_count_all.astype(np.int64)
        emis_sum_all = emis_sum_all.astype(np.float64)
        
        xtsum_emis_sum = np.sum(emis_sum_all, axis=0, dtype=np.float64)
        xtsum_emis_count = np.sum(emis_count_all, axis=0, dtype=np.int64)
        
        # ====================================================================
        # LOAD ELEVATION DATA from L3_Context-Sorted group
        # ====================================================================
        context_group = ds.groups["L3_Context-Sorted"]
        
        # Shape: (xtrack=8, sort_metric=9, lat=168, lon=360)
        elev_mean_raw = context_group.variables["elev_mean"][...]
        
        print(f"  Loading elevation data from L3_Context-Sorted/elev_mean")
        print(f"    Raw elevation shape: {elev_mean_raw.shape}")
        
        # Mask fill values (-9999.0) as NaN
        elev_mean_raw = np.ma.masked_equal(elev_mean_raw, -9999.0).filled(np.nan)
        
        # Average across xtrack and sort_metric dimensions to get (lat, lon)
        with np.errstate(invalid='ignore', divide='ignore'):
            elev_mean_2d = np.nanmean(elev_mean_raw, axis=(0, 1))
        
        # Filter out remaining invalid values (< -1000 or non-finite)
        # This keeps the sign convention but removes bad data
        elev_mean_2d = np.where((elev_mean_2d < -1000) | ~np.isfinite(elev_mean_2d), 
                               np.nan, elev_mean_2d)
        
        print(f"    Processed elevation shape: {elev_mean_2d.shape}")
        print(f"    Elevation range: {np.nanmin(elev_mean_2d):.1f} to {np.nanmax(elev_mean_2d):.1f} meters")
        print(f"    Valid elevation cells: {np.sum(np.isfinite(elev_mean_2d))}")
        
        return {
            'lat2d': lat2d,
            'lon2d': lon2d,
            'elevation': elev_mean_2d,  # NEW: Elevation array (lat, lon)
            'emis_sum_all': xtsum_emis_sum,
            'emis_count_all': xtsum_emis_count,
            'wavelengths': wavelength_mean,
            'surface_types': surface_types,
            'surface_type_names': surface_type_names,
            'satellite': sat_num,
            'filename': p_fpath
        }

def merge_monthly_all_channels_data(data_list, min_elevation=500):
    """
    Merge raw data from multiple months with ELEVATION FILTERING DURING MERGE
    
    CRITICAL: For each month, we filter by elevation BEFORE adding to the sum.
    This prevents the temporal mismatch bug where:
    - Month 1: elevation=100m, has partial sea ice observations
    - Month 2: elevation=2200m, has permanent ice observations
    - Old bug: MAX elevation=2200m, but SUM includes sea ice from Month 1
    - New fix: Only sum data from months where elevation >= threshold
    
    Parameters:
    -----------
    data_list : list of dicts
        Monthly data to merge
    min_elevation : float
        Minimum elevation threshold (default 500m for pure ice sheet)
    """
    print(f"\nMerging all-channel data from {len(data_list)} months...")
    print(f"ELEVATION FILTER: Only including data where elevation >= {min_elevation}m")
    print(f"This ensures counts only include observations from high-elevation months")
    
    template = data_list[0]
    n_channels = len(template['wavelengths'])
    
    merged_emis_sum = np.zeros_like(template['emis_sum_all'], dtype=np.float64)
    merged_emis_count = np.zeros_like(template['emis_count_all'], dtype=np.int64)
    
    # Merge elevation by taking MAX across months (preserves ice sheet elevations)
    merged_elevation = np.full_like(template['elevation'], -np.inf, dtype=np.float64)
    
    # Track how many months contribute to each pixel
    months_contributing = np.zeros_like(template['elevation'], dtype=np.int32)
    
    for i, data in enumerate(data_list):
        print(f"  Month {i+1}: {os.path.basename(data['filename'])}")
        
        # Create elevation mask for THIS month
        elev_mask = (data['elevation'] >= min_elevation) & np.isfinite(data['elevation'])
        
        # Count pixels passing elevation filter this month
        n_valid_pixels = np.sum(elev_mask)
        print(f"    Pixels with elevation >= {min_elevation}m: {n_valid_pixels}")
        
        # Expand mask to match emissivity data dimensions: (sfc_type, lat, lon, channel)
        # Shape: (lat, lon) -> (1, lat, lon, 1) -> broadcasts to (sfc_type, lat, lon, channel)
        elev_mask_expanded = elev_mask[np.newaxis, :, :, np.newaxis]
        
        # Apply elevation filter: zero out data where elevation < threshold
        # This is THE KEY FIX: only include data from months where pixel was at high elevation
        masked_emis_sum = np.where(elev_mask_expanded, data['emis_sum_all'], 0)
        masked_emis_count = np.where(elev_mask_expanded, data['emis_count_all'], 0)
        
        # Add filtered data to merged totals
        merged_emis_sum += masked_emis_sum.astype(np.float64)
        merged_emis_count += masked_emis_count.astype(np.int64)
        
        # Track elevation (MAX) and which months contributed
        valid_elev = np.isfinite(data['elevation'])
        merged_elevation = np.where(valid_elev, 
                                    np.maximum(merged_elevation, data['elevation']),
                                    merged_elevation)
        months_contributing += elev_mask.astype(np.int32)
    
    # Set -inf values to NaN
    merged_elevation[merged_elevation == -np.inf] = np.nan
    
    # Calculate mean emissivity from filtered sums
    emis_mean_calculated = np.divide(merged_emis_sum, merged_emis_count,
                                    out=np.full_like(merged_emis_sum, np.nan),
                                    where=merged_emis_count > 0)
    
    print(f"\n  MERGE SUMMARY:")
    print(f"  Merged emissivity shape: {emis_mean_calculated.shape}")
    print(f"  Merged elevation shape: {merged_elevation.shape}")
    print(f"  Total observations (filtered): {np.sum(merged_emis_count):,}")
    print(f"  Elevation range: {np.nanmin(merged_elevation):.1f} to {np.nanmax(merged_elevation):.1f} m")
    print(f"  Pixels with data from all {len(data_list)} months: {np.sum(months_contributing == len(data_list))}")
    print(f"  Pixels with data from 1+ months: {np.sum(months_contributing > 0)}")
    print(f"  ✓ All counts are from months where elevation >= {min_elevation}m")
    
    return {
        'lat2d': template['lat2d'],
        'lon2d': template['lon2d'],
        'elevation': merged_elevation,
        'emis_mean_all': emis_mean_calculated,
        'count_all': merged_emis_count,
        'wavelengths': template['wavelengths'],
        'surface_types': template['surface_types'],
        'surface_type_names': template['surface_type_names'],
        'satellite': template['satellite'],
        'filename': template['filename'],
        'merged_months': [os.path.basename(d['filename']) for d in data_list],
        'min_elevation': min_elevation,
        'months_contributing': months_contributing
    }


def create_greenland_boundary_mask(lat2d, lon2d):
    """Create Greenland mask using Natural Earth land polygons"""
    from cartopy.io import shapereader
    import matplotlib.path as mpath
    
    land_shp = shapereader.natural_earth(resolution='50m', category='physical', name='land')
    
    if lat2d.ndim == 2:
        lats_flat = lat2d.flatten()
        lons_flat = lon2d.flatten()
    else:
        lons_mesh, lats_mesh = np.meshgrid(lon2d, lat2d)
        lats_flat = lats_mesh.flatten()
        lons_flat = lons_mesh.flatten()
    
    mask_flat = np.zeros(len(lats_flat), dtype=bool)
    
    for record in shapereader.Reader(land_shp).records():
        geom = record.geometry
        
        if hasattr(geom, 'bounds'):
            minx, miny, maxx, maxy = geom.bounds
            if (minx >= -80 and maxx <= 0 and miny >= 55 and maxy <= 90):
                if hasattr(geom, 'exterior'):
                    coords = list(geom.exterior.coords)
                    path = mpath.Path(coords)
                    points = np.column_stack([lons_flat, lats_flat])
                    inside = path.contains_points(points)
                    mask_flat |= inside
                    
                elif hasattr(geom, 'geoms'):
                    for subgeom in geom.geoms:
                        if hasattr(subgeom, 'exterior'):
                            coords = list(subgeom.exterior.coords)
                            path = mpath.Path(coords)
                            points = np.column_stack([lons_flat, lats_flat])
                            inside = path.contains_points(points)
                            mask_flat |= inside
    
    if lat2d.ndim == 2:
        greenland_mask = mask_flat.reshape(lat2d.shape)
        iceland_exclude = ((lon2d >= -25) & (lon2d <= -13) & (lat2d >= 63) & (lat2d <= 67))
        greenland_mask = greenland_mask & (~iceland_exclude)
    else:
        greenland_mask = mask_flat.reshape(len(lat2d), len(lon2d))
        lon_mesh, lat_mesh = np.meshgrid(lon2d, lat2d)
        iceland_exclude = ((lon_mesh >= -25) & (lon_mesh <= -13) & (lat_mesh >= 63) & (lat_mesh <= 67))
        greenland_mask = greenland_mask & (~iceland_exclude)
    
    return greenland_mask

def create_regional_mask_with_elevation(lat2d, lon2d, elevation, region, 
                                        min_elevation=500):
    """
    Create spatial mask with 3-step filtering approach:
    
    STEP 1: Geographic boundary (Natural Earth accurate polygons)
    STEP 2: Elevation ≥500m (within geographic boundary)
    STEP 3: Surface type filtering (permanent land ice) - done separately in emissivity calculation
    
    NOTE: Elevation data filtering has ALREADY been applied during merge to prevent
    temporal mismatch. This function creates the spatial mask showing which grid cells
    to include in the analysis.
    
    Parameters:
    -----------
    lat2d, lon2d : array (lat, lon)
        Grid coordinates
    elevation : array (lat, lon)
        Surface elevation (MAX across merged months)
    region : str
        'greenland' or 'antarctica'
    min_elevation : float
        Elevation threshold in meters (default: 500m)
    
    Returns:
    --------
    combined_mask : boolean array (lat, lon)
        Spatial mask = Geographic boundary AND Elevation ≥500m
    """
    
    print(f"\n{'='*80}")
    print(f"Creating Spatial Mask: {region.upper()}")
    print(f"3-Step Filtering Approach:")
    print(f"  STEP 1: Geographic boundary (Natural Earth accurate polygons)")
    print(f"  STEP 2: Elevation ≥{min_elevation}m mask")
    print(f"  STEP 3: Surface type filtering (permanent land ice) - applied during emissivity calculation")
    print(f"{'='*80}")
    
    # STEP 1: Create geographic boundary mask using Natural Earth polygons
    print(f"\nSTEP 1: Geographic Boundary")
    if region == 'greenland':
        print("  Using Natural Earth 50m polygon for Greenland (excludes Iceland)...")
        geographic_mask = create_greenland_boundary_mask(lat2d, lon2d)
    elif region == 'antarctica':
        print("  Using Natural Earth 50m polygon for Antarctica...")
        geographic_mask = create_antarctic_continent_boundary_mask(lat2d, lon2d)
    else:
        raise ValueError(f"Unknown region: {region}")
    
    print(f"  ✓ Geographic mask: {np.sum(geographic_mask)} grid cells")
    
    # STEP 2: Create elevation mask (≥500m within geographic boundary)
    print(f"\nSTEP 2: Elevation Mask (≥{min_elevation}m)")
    print(f"  Note: Elevation data filtering already applied during merge to prevent temporal mismatch")
    print(f"  This step creates the spatial mask showing which cells have elevation ≥{min_elevation}m")
    
    # Create elevation mask
    elevation_mask = elevation >= min_elevation
    
    # Show elevation statistics in geographic region
    region_elevation = elevation[geographic_mask]
    valid_region_elev = region_elevation[np.isfinite(region_elevation)]
    
    if len(valid_region_elev) > 0:
        print(f"\n  Elevation distribution within geographic boundary:")
        print(f"    Min elevation: {np.min(valid_region_elev):.1f} m")
        print(f"    25th percentile: {np.percentile(valid_region_elev, 25):.1f} m")
        print(f"    Median: {np.median(valid_region_elev):.1f} m")
        print(f"    75th percentile: {np.percentile(valid_region_elev, 75):.1f} m")
        print(f"    Max elevation: {np.max(valid_region_elev):.1f} m")
        print(f"    Mean elevation: {np.mean(valid_region_elev):.1f} m")
    
    # Count cells meeting elevation threshold
    high_elev_in_region = np.sum(geographic_mask & elevation_mask)
    total_in_region = np.sum(geographic_mask)
    pct_high_elev = 100 * high_elev_in_region / total_in_region if total_in_region > 0 else 0
    
    print(f"\n  Cells with elevation ≥{min_elevation}m: {high_elev_in_region} / {total_in_region} ({pct_high_elev:.1f}%)")
    print(f"  ✓ Elevation mask: {np.sum(elevation_mask)} grid cells globally")
    
    # Combine geographic and elevation masks
    combined_mask = geographic_mask & elevation_mask
    
    print(f"\nCombined Mask (Geographic AND Elevation ≥{min_elevation}m):")
    print(f"  Final spatial mask: {np.sum(combined_mask)} cells")
    print(f"  ✓ These cells define the analysis region")
    
    print(f"\nSTEP 3: Surface Type Filtering")
    print(f"  Surface type filtering (permanent land ice only) is applied separately")
    print(f"  during emissivity calculation using surface type index 3 (flag 4)")
    
    print(f"{'='*80}\n")
    
    return combined_mask



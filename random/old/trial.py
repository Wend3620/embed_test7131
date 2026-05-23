from pathlib import Path
import xarray as xr
from scipy.stats import binned_statistic_2d
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
  # From other external Python packages:
from datetime import datetime, timedelta, date 
import os
import numpy as np
import netCDF4 as nc
import json
import matplotlib as mpl
from processor import retrieve_list, process_granule_months, create_orthographic_plot, create_global_plot

start = datetime.strptime("06_24", "%m_%y")
end = datetime.strptime("02_26", "%m_%y")

months = []
current = start

while current <= end:
    months.append(current.strftime("%m_%y"))
    if current.month == 12:
        current = current.replace(year=current.year + 1, month=1)
    else:
        current = current.replace(month=current.month + 1)

bins = [months[i:i + 3] for i in range(0, len(months), 3)]
seasons = ['JJA', 'SON', 'DJF', 'MAM', 'JJA', 'SON', 'DJF', 'MAM']
bins
def full_log_gen():
    all_sat = {}
    visited = {} #Check if there are duplicate versions
    for sat in ['sat1', 'sat2']:
        data_folder = f"/data/ops/PREFIRE-{sat.upper()}/1B-RAD"
        dates = {}
        for file in os.listdir(data_folder):
            if file.endswith('.nc'):
                time = datetime.strptime(file.split('_')[5], '%Y%m%d%H%M%S')
                time_full = time.strftime('%Y%m%d%H%M%S') #store the full timestamp to check for duplicates
                month_str = time.strftime('%Y-%m')
                r_version = int(file.split('_')[3][1:])
                if month_str not in dates:
                    dates[month_str] = {}
                    visited[month_str] = {}
                time_str = time.strftime('%Y-%m-%d')
                if time_str not in dates[month_str]:
                    dates[month_str][time_str] = 1
                    visited[month_str][time_full] = r_version
                else:
                    if time_full not in visited[month_str]:
                        dates[month_str][time_str] += 1 #only count the day once, even if there are multiple versions
                        visited[month_str][time_full] = r_version #add the version to visited to check for duplicates

                    if r_version > visited[month_str][time_full]:
                        visited[month_str][time_full] = r_version #update to the latest version if there are duplicates
                    else:
                        continue
        all_sat[sat] = dates
    json.dump(all_sat, open('./all_sat.json', 'w'))

def seasonal_json(start_year, end_year, full_log = 'all_sat.json', export_dir = './quick_data'):
    '''
    Exports seasonal JSON files containing the satellite data for the specified year range.
    Parameters:
    - start_year (int): Start year (e.g., 2026).
    - end_year (int): End year (e.g., 2026).
    - full_log (str): Path to the full JSON log file containing all satellite data.
    - export_dir (str): Directory where the seasonal JSON files will be saved.
    '''
    errors1 = []
    with open(full_log, "r") as f:
        jfile = json.load(f)
        for sattlite in ['sat1', 'sat2']:
            # season = 'SON'
            for year in range(start_year, end_year+1):
                for season in ['MAM', 'JJA', 'SON', 'DJF']: # 
                    try:
                        actual = 0
                        year_short = str(year)[-2:]               
                        if season == 'DJF':
                            names = [f'{sattlite}_12_{year_short}', f'{sattlite}_01_{int(year_short)+1}', f'{sattlite}_02_{int(year_short)+1}']
                        elif season == 'MAM':
                            names = [f'{sattlite}_03_{year_short}', f'{sattlite}_04_{year_short}', f'{sattlite}_05_{year_short}']
                        elif season == 'JJA':
                            names = [f'{sattlite}_06_{year_short}', f'{sattlite}_07_{year_short}', f'{sattlite}_08_{year_short}']
                        elif season == 'SON':
                            names = [f'{sattlite}_09_{year_short}', f'{sattlite}_10_{year_short}', f'{sattlite}_11_{year_short}']
                        month = int(names[0].split("_")[1])
                        start = date(year, month, 1)
                        end_year = year if month != 12 else year+1
                        end_month = int(month)+2 if month != 12 else 2
                        if end_month == 2:
                            end = date(end_year, end_month, 28)
                        elif end_month in [1, 3, 5, 7, 8, 10, 12]:
                            end = date(end_year, end_month, 31)
                        else:
                            end = date(end_year, end_month, 30)
                        try:
                            all_days = [str(start + timedelta(d)) for d in range((end - start).days + 1)]
                            complete = 15*len(all_days)+3 #+3 for days with 1 more granue
                        except:
                            print(f"Error: Invalid month {month} or year {year}")
                        for file in names:
                            month_name = datetime.strptime(file[5:], '%m_%y').strftime('%Y-%m')
                            month_dict = jfile[sattlite][month_name]
                            month_file = int(file.split("_")[1])
                            for day in month_dict:
                                month_data = int(day.split("-")[1])
                                if month_data != month_file:
                                    continue
                                actual += month_dict[day]
                                print(day, month_dict[day])
                                all_days.remove(day)
                        result = {'Days missing': all_days, 'Percentage of anticipated granules completed': f'{actual}/{complete} = {actual/complete:.2%}'}
                        output = file.split(".")[0].split("_")
                        output_file = f"{output[0]}_{season}_20{output[2]}.json"
                        with open(f"{export_dir}/{output_file}", "w") as f:
                            json.dump(result, f, indent=4)
                        print(f'Days missing: {all_days}\nPercentage of anticipated granules completed: {actual}/{complete} = {actual/complete:.2%}')
                    except Exception as e:
                        errors1.append(f"{sattlite} {season} {year}: {str(e)}")
                        continue

def monthly_json(start_mmyy, end_mmyy, full_log = 'all_sat.json', export_dir = './quick_data/month'):
    '''
    Exports monthly JSON files containing the satellite data for the specified date range.
    Parameters:
    - start_mmyy: Start date in "MMYY format (e.g., "0226" for February 2026).
    - end_mmyy: End date in "MMYY"
    - full_log: Path to the full JSON log file containing all satellite data.
    - export_dir: Directory where the monthly JSON files will be saved.
    '''
    start_month = datetime.strptime(start_mmyy,'%Y-%m').month
    start_year = datetime.strptime(start_mmyy,'%Y-%m').year
    end_month = datetime.strptime(end_mmyy,'%Y-%m').month
    end_year = datetime.strptime(end_mmyy,'%Y-%m').year
    with open(full_log, "r") as f:
        jfile = json.load(f)
        for sattlite in ['sat1', 'sat2']:
            for file in jfile[sattlite]:
                year = int(file.split("-")[0])
                month = int(file.split("-")[1])
                start = date(year, month, 1)
                if year < start_year or year > end_year:
                    continue
                elif year == start_year and month < start_month:
                    continue
                elif year == end_year and month > end_month:
                    continue

                if month == 2:
                    end = date(year, month, 28)
                elif month in [1, 3, 5, 7, 8, 10, 12]:
                    end = date(year, month, 31)
                else:
                    end = date(year, month, 30)
                try:
                    all_days = [str(start + timedelta(d)) for d in range((end - start).days + 1)]
                    complete = 15*len(all_days)+3 #+3    for days with 1 more granue
                except:
                    print(f"Error: Invalid month {month} or year {year}")
                actual = 0
                month_file = int(file.split("-")[1])
                for day in jfile[sattlite][file]:
                    month_data = int(day.split("-")[1])
                    if month_data != month_file:
                        continue
                    actual += jfile[sattlite][file][day]
                    # print(day, jfile[sattlite][file][day])
                    all_days.remove(day)
                result = {'Days missing': all_days, 'Percentage of anticipated granules completed': f'{actual}/{complete} = {actual/complete:.2%}'}
                output_file = f"{sattlite}_{file.split('-')[1]}_{file.split('-')[0]}.json"
                with open(f"{export_dir}/{output_file}", "w") as f:
                    json.dump(result, f, indent=4)
                # print(f'Days missing: {all_days}\nPercentage of anticipated granules completed: {actual}/{complete} = {actual/complete:.2%}')

def monthly_data_gen(start_mmyy, end_mmyy, export_folder = "/data/users/wdu",satellite = 'sat1'):
    '''
    Exports monthly JSON files containing the satellite data for the specified date range.
    Parameters:
    - start_mmyy: Start date in "MMYY format (e.g., "0226" for February 2026).
    - end_mmyy: End date in "MMYY"
    - export_folder: Directory where the monthly JSON files will be saved.
    - satellite: name of the satellite, either 'sat1' or 'sat2'
    '''
    filelist = retrieve_list(start_mmyy, end_mmyy, satellite)
    data_folder = export_folder

    source_dir = f"/data/ops/PREFIRE-{satellite.upper()}/1B-RAD"
    for channel_idx in [12, 24, 30, 32]:
        all_missed = []
        for granule_month in filelist:
            mmyy = datetime.strptime(granule_month,'%Y-%m').strftime( "%m%y")
            try:
                tb_all, lat_all, lon_all, wavelength = process_granule_months(source_dir, filelist[granule_month], channel_index = channel_idx)
            except Exception as e:
                print(f"Error processing directory {filelist[granule_month]}: {e}")
                all_missed.append(filelist[granule_month])
                continue
                

            lat_edges = np.arange(-90,91,1)
            lon_edges = np.arange(-180,181,1)

            lat_mids = lat_edges[:-1] + 0.5
            lon_mids = lon_edges[:-1] + 0.5
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
            lon2d, lat2d = np.meshgrid(lon_mids, lat_mids)
            threshold=1000
            count_mask = (count_tb > threshold)
            ds = xr.Dataset(
                {
                    'mean_tb': (['lat', 'lon'], mean_tb, {'short_name': 'Mean BT', 'long_name': 'Mean Brightness Temperature', 'units': 'K'}),
                    'count_tb': (['lat', 'lon'], count_tb, {'short_name': 'Count TB', 'long_name': 'Count of  Observations', 'units': 'count'}),
                    'std_tb': (['lat', 'lon'], std_tb, {'short_name': 'Std BT', 'long_name': 'Standard Deviation of Brightness Temperature', 'units': 'K'}),
                    'max_tb': (['lat', 'lon'], max_tb, {'short_name': 'Max BT', 'long_name': 'Maximum Brightness Temperature', 'units': 'K'}),
                    'min_tb': (['lat', 'lon'], min_tb, {'short_name': 'Min BT', 'long_name': 'Minimum Brightness Temperature', 'units': 'K'}),
                    'count_mask': (['lat', 'lon'], count_mask.astype(float), {'short_name': 'Count Mask', 'long_name': 'Count Mask', 'units': 'count'})
                },
                coords={
                    'lat': (['lat'], lat_mids, {'units': 'degrees_north'}), 
                    'lon': (['lon'], lon_mids, {'units': 'degrees_east'})
                },
                attrs={
                    'time': mmyy,
                    'channel': channel_idx,
                    'wavelength': wavelength,
                    'wavelength_units': 'µm',
                    'description': f'{satellite.upper()} brightness temperature statistics for channel {channel_idx} for {mmyy}',
                }
            )
            ds.to_netcdf(f'{data_folder}/{satellite}_{mmyy}_ch{channel_idx}.nc')

def seasonal_plot_gen(start_year, end_year, satellites = ['sat1', 'sat2'], 
                      data_folder = "/data/users/wdu", export_folder = f'./plots/season_plots', pic_type = 'webp'):
    '''
    Exports seasonal pictures containing the satellite data for the specified date range.
    Parameters:
    - start_year: Start year (YYYY).
    - end_year: End year (YYYY)"
    - satellites:List of satellites to generate pictures. Default is ['sat1', 'sat2']
    - data_folder: Directory of the data (sat#_mmyy_ch##.nc).
    - export_folder: Directory where the seasonal plots will be saved.
    - pic_type: Format of the exported picture. Default is .webp
    '''
    errors1 = []
    attr = pic_type
    folder = f'{export_folder}/'
    for channel in [12, 24, 30, 32]:
        for sattlite in satellites:
            for year in range(start_year, end_year):
                for season in ['MAM', 'JJA', 'SON', 'DJF']:
                    year_short = str(year)[-2:]
                    try:
                        ds_test = []
                        if season == 'DJF':
                            names = [f'{sattlite}_12{year_short}', f'{sattlite}_01{int(year_short)+1}', f'{sattlite}_02{int(year_short)+1}']
                        elif season == 'MAM':
                            names = [f'{sattlite}_03{year_short}', f'{sattlite}_04{year_short}', f'{sattlite}_05{year_short}']
                        elif season == 'JJA':
                            names = [f'{sattlite}_06{year_short}', f'{sattlite}_07{year_short}', f'{sattlite}_08{year_short}']
                        elif season == 'SON':
                            names = [f'{sattlite}_09{year_short}', f'{sattlite}_10{year_short}', f'{sattlite}_11{year_short}']

                        wavelength = 0

                        for name in names:
                            ds = xr.load_dataset(f'{data_folder}/{name}_ch{channel}.nc')
                            ds = ds.assign_coords(time=datetime.strptime(name.split('_')[1], '%m%y'))
                            ds_test.append(ds)
                            wavelength = ds.wavelength
                        ds_test = xr.concat(ds_test, dim='time')
                        ds_test = ds_test.assign_attrs({'wavelength': wavelength})
                        ds_test = ds_test.mean(dim='time')

                        if f'sp_ch{channel}' not in os.listdir(f'{folder}'):
                            os.mkdir(f'{folder}sp_ch{channel}')
                        if f'gb_ch{channel}' not in os.listdir(f'{folder}'):
                            os.mkdir(f'{folder}gb_ch{channel}')
                        if f'np_ch{channel}' not in os.listdir(f'{folder}'):
                            os.mkdir(f'{folder}np_ch{channel}')
                        for var in ['mean_tb', 'std_tb', 'min_tb', 'max_tb']:
                            # ds_test[var] = ds_test[var].where(count_mask > 0)
                            var_name = var.split('_')[0]
                            #sat1_1_2024_np_ch12_mean.png
                            file = f"{sattlite}_{season}_{year}_np_ch{channel}_{var_name}.{attr}"
                            data = ds_test[var].sel(lat = slice(60, 85))
                            vmin = np.floor(np.nanpercentile(data.values, 3) / 10) * 10
                            vmax = np.ceil(np.nanpercentile(data.values, 97) / 10) * 10
                            create_orthographic_plot(ds_test[var], statistic_name=var_name, pole='north', 
                                wavelength=wavelength, output_path=f'{folder}np_ch{channel}/{file}', 
                                count_mask=ds_test.count_mask, satellite=sattlite.capitalize(), season=season, vmin=vmin, vmax=vmax)
                            
                            file = f"{sattlite}_{season}_{year}_sp_ch{channel}_{var_name}.{attr}"
                            data = ds_test[var].sel(lat = slice(-85, -60))#.sel(lat = slice(60, 85))
                            vmin = np.floor(np.nanpercentile(data.values, 3) / 10) * 10
                            vmax = np.ceil(np.nanpercentile(data.values, 97) / 10) * 10
                            create_orthographic_plot(ds_test[var], statistic_name=var_name, pole='south', 
                                wavelength=wavelength, output_path=f'{folder}sp_ch{channel}/{file}', 
                                count_mask=ds_test.count_mask, satellite=sattlite.capitalize(), season=season, vmin=vmin, vmax=vmax)
                            
                            file = f"{sattlite}_{season}_{year}_gb_ch{channel}_{var_name}.{attr}"
                            data = ds_test[var]
                            vmin = np.floor(np.nanpercentile(data.values, 3) / 10) * 10
                            vmax = np.ceil(np.nanpercentile(data.values, 97) / 10) * 10
                            create_global_plot(ds_test[var], statistic_name=var_name, 
                                wavelength=wavelength, output_path=f'{folder}gb_ch{channel}/{file}', 
                                count_mask=ds_test.count_mask, satellite=sattlite.capitalize(), season=season, vmin=vmin, vmax=vmax)
                    except:
                        errors1.append(f"Error processing {sattlite} {season} ch{channel}")

def monthly_plot_gen(start_mmyy, end_mmyy, satellites = ['sat1', 'sat2'], 
                      data_folder = "/data/users/wdu", export_folder = f'./plots/month_plots', pic_type = 'webp'):
    '''
    Exports monthly pictures containing the satellite data for the specified date range.
    Parameters:
    - start_mmyy: Start date in "MMYY format (e.g., "0226" for February 2026).
    - end_mmyy: End date in "MMYY"
    - satellites: List of satellites to generate pictures. Default is ['sat1', 'sat2']
    - data_folder: Directory of the data (sat#_mmyy_ch##.nc).
    - export_folder: Directory where the monthly plots will be saved.
    - pic_type: Format of the exported picture. Default is .webp
    '''
    start = datetime.strptime(start_mmyy, "%m%y")
    end = datetime.strptime(end_mmyy, "%m%y")

    months = []
    current = start

    while current <= end:
        months.append(current.strftime("%m%y"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    errors = []
    attr = pic_type
    folder = f'{export_folder}/'
    for channel in [12, 24, 30, 32]:
        for sattlite in satellites:
            # month = 'SON'
            for month in months:
                try:
                    ds_test = []
                    name = f'{sattlite}_{month}'
                    wavelength = 0

                    ds = xr.load_dataset(f'{data_folder}/{name}_ch{channel}.nc')
                    ds_test=ds
                    wavelength = ds.wavelength
                    ds_test = ds_test.assign_attrs({'wavelength': wavelength})

                    if f'sp_ch{channel}' not in os.listdir(f'{folder}'):
                        os.mkdir(f'{folder}sp_ch{channel}')
                    if f'gb_ch{channel}' not in os.listdir(f'{folder}'):
                        os.mkdir(f'{folder}gb_ch{channel}')
                    if f'np_ch{channel}' not in os.listdir(f'{folder}'):
                        os.mkdir(f'{folder}np_ch{channel}')
                    for var in ['mean_tb', 'std_tb', 'min_tb', 'max_tb']:
                        # ds_test[var] = ds_test[var].where(count_mask > 0)
                        var_name = var.split('_')[0]
                        dt = datetime.strptime(month, "%m%y")
                        file = f"{sattlite}_{dt.month}_{dt.year}_np_ch{channel}_{var_name}.{attr}"
                        data = ds_test[var].sel(lat = slice(60, 85))
                        vmin = np.floor(np.nanpercentile(data.values, 3) / 10) * 10
                        vmax = np.ceil(np.nanpercentile(data.values, 97) / 10) * 10
                        month_str = datetime.strptime(month, "%m%y").strftime("%b %Y")
                        create_orthographic_plot(ds_test[var], statistic_name=var_name, pole='north', 
                            wavelength=wavelength, output_path=f'{folder}np_ch{channel}/{file}', 
                            count_mask=ds_test.count_mask, satellite=sattlite.capitalize(), season=month_str, vmin=vmin, vmax=vmax)
                        
                        file = f"{sattlite}_{dt.month}_{dt.year}_sp_ch{channel}_{var_name}.{attr}"
                        data = ds_test[var].sel(lat = slice(-85, -60))#.sel(lat = slice(60, 85))
                        vmin = np.floor(np.nanpercentile(data.values, 3) / 10) * 10
                        vmax = np.ceil(np.nanpercentile(data.values, 97) / 10) * 10
                        month_str = datetime.strptime(month, "%m%y").strftime("%b %Y")
                        create_orthographic_plot(ds_test[var], statistic_name=var_name, pole='south', 
                            wavelength=wavelength, output_path=f'{folder}sp_ch{channel}/{file}', 
                            count_mask=ds_test.count_mask, satellite=sattlite.capitalize(), season=month_str, vmin=vmin, vmax=vmax)
                        
                        file = f"{sattlite}_{dt.month}_{dt.year}_gb_ch{channel}_{var_name}.{attr}"
                        data = ds_test[var]
                        vmin = np.floor(np.nanpercentile(data.values, 3) / 10) * 10
                        vmax = np.ceil(np.nanpercentile(data.values, 97) / 10) * 10
                        month_str = datetime.strptime(month, "%m%y").strftime("%b %Y")
                        create_global_plot(ds_test[var], statistic_name=var_name, 
                            wavelength=wavelength, output_path=f'{folder}gb_ch{channel}/{file}', 
                            count_mask=ds_test.count_mask, satellite=sattlite.capitalize(), season=month_str, vmin=vmin, vmax=vmax)
                except:
                    errors.append(f"Error processing {sattlite} {month} ch{channel}")


def main(
    month_range: tuple = None,       # e.g. ("0124", "0226") — overrides past-month default
    season_years: tuple = None,      # e.g. (2024, 2026) — if provided, also run seasonal plots
    satellites: list = None,
    data_folder: str = "/data/users/wdu",
    plot_folder_month: str = "./plots/month_plots",
    plot_folder_season: str = "./plots/season_plots",
    pic_type: str = "webp",
):
    """
    Entry point for automated plot generation.

    - Past month:   always generated (the calendar month before today).
    - Month range:  generated when month_range=(start_mmyy, end_mmyy) is supplied.
    - Seasons:      generated when season_years=(start_year, end_year) is supplied.

    Data (.nc files) is produced first via monthly_data_gen, then plots are rendered.
    """
    if satellites is None:
        satellites = ["sat1", "sat2"]

    today = datetime.today()
    # Roll back one month
    first_of_this_month = today.replace(day=1)
    last_month_dt = first_of_this_month - timedelta(days=1)
    past_month_mmyy = last_month_dt.strftime("%m%y")          # e.g. "0226"f

    print(f"=== Generating plots for past month: {last_month_dt.strftime('%b %Y')} ===")
    for sat in satellites:
        monthly_data_gen(past_month_mmyy, past_month_mmyy, export_folder=data_folder, satellite=sat)
    monthly_plot_gen(
        past_month_mmyy, past_month_mmyy,
        satellites=satellites,
        data_folder=data_folder,
        export_folder=plot_folder_month,
        pic_type=pic_type,
    )

    if month_range is not None:
        start_mmyy, end_mmyy = month_range
        print(f"=== Generating plots for month range: {start_mmyy} → {end_mmyy} ===")
        for sat in satellites:
            monthly_data_gen(start_mmyy, end_mmyy, export_folder=data_folder, satellite=sat)
        monthly_plot_gen(
            start_mmyy, end_mmyy,
            satellites=satellites,
            data_folder=data_folder,
            export_folder=plot_folder_month,
            pic_type=pic_type,
        )

    if season_years is not None:
        start_year, end_year = season_years
        print(f"=== Generating seasonal plots: {start_year} → {end_year} ===")
        seasonal_plot_gen(
            start_year, end_year,
            satellites=satellites,
            data_folder=data_folder,
            export_folder=plot_folder_season,
            pic_type=pic_type,
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate monthly and/or seasonal brightness-temperature plots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    examples:
    # past month only (default)
    python trial.py

    # custom month range
    python trial.py --month-range 0624 0226

    # seasonal plots for 2024-2025
    python trial.py --season-years 2024 2025

    # all three, sat1 only, png output
    python trial.py --month-range 0624 0226 --season-years 2024 2025 --satellites sat1 --pic-type png
    """,
    )
    parser.add_argument(
        "--month-range", nargs=2, metavar=("START_MMYY", "END_MMYY"),
        help="Generate plots for a month range, e.g. --month-range 0624 0226",
    )
    parser.add_argument(
        "--season-years", nargs=2, type=int, metavar=("START_YEAR", "END_YEAR"),
        help="Generate seasonal plots, e.g. --season-years 2024 2026",
    )
    parser.add_argument(
        "--satellites", nargs="+", default=["sat1", "sat2"],
        metavar="SAT", help="Satellites to process (default: sat1 sat2)",
    )
    parser.add_argument(
        "--data-folder", default="/data/users/wdu",
        help="Directory containing .nc data files (default: /data/users/wdu)",
    )
    parser.add_argument(
        "--plot-folder-month", default="./plots/month_plots",
        help="Output directory for monthly plots",
    )
    parser.add_argument(
        "--plot-folder-season", default="./plots/season_plots",
        help="Output directory for seasonal plots",
    )
    parser.add_argument(
        "--pic-type", default="webp",
        help="Image format: webp, png, jpg … (default: webp)",
    )

    args = parser.parse_args()

    main(
        month_range=tuple(args.month_range) if args.month_range else None,
        season_years=tuple(args.season_years) if args.season_years else None,
        satellites=args.satellites,
        data_folder=args.data_folder,
        plot_folder_month=args.plot_folder_month,
        plot_folder_season=args.plot_folder_season,
        pic_type=args.pic_type,
    )

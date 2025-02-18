#!/usr/bin/env python
# ~*~ coding: utf8 ~*~
# pylint: disable=invalid-name
"""Find marginal covariances in space and time."""
from __future__ import print_function, division
import itertools
import datetime
import inspect

import numpy as np
from numpy import exp, sin, cos, square, newaxis
import matplotlib.pyplot as plt
import pandas as pd
import scipy.optimize

import pyproj
import cartopy.crs as ccrs
import xarray
from statsmodels.tsa.stattools import acovf, acf
from statsmodels.tools.eval_measures import aic, aicc, bic, hqic
from bottleneck import nansum

MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY
DAYS_PER_DAY = 1
DAYS_PER_YEAR = 365.2425
DAYS_PER_WEEK = 7

GLOBE = ccrs.Globe(semimajor_axis=6370000, semiminor_axis=6370000)
PROJECTION = ccrs.LambertConformal(
    standard_parallels=(30, 60),
    central_latitude=40,
    central_longitude=-96,
    globe=GLOBE,
)
GEOD = pyproj.Geod(sphere=True, a=6370000)

PI_OVER_DAY = np.pi / DAYS_PER_DAY
TWO_PI_OVER_DAY = 2 * PI_OVER_DAY
PI_OVER_YEAR = np.pi / DAYS_PER_YEAR
TWO_PI_OVER_YEAR = 2 * PI_OVER_YEAR
FOUR_PI_OVER_YEAR = 4 * PI_OVER_YEAR

MIN_DIFFERENCES_IN_FIT = HOURS_PER_DAY * DAYS_PER_YEAR * 2

amf_ds = xarray.open_dataset(
    "/abl/s0/Continent/dfw5129/ameriflux_netcdf/"
    "AmeriFlux_single_value_per_tower_half_hour_data.nc4"
)
casa_ds = xarray.open_mfdataset(
    ("/mc1s2/s4/dfw5129/casa_downscaling/"
     "200?-??_downscaled_CASA_L2_Ensemble_Mean_Biogenic_NEE_Ameriflux.nc4"),
    combine="by_coords"
)

sites_in_both = sorted(set(casa_ds.coords["Site_Id"].values) &
                       set(amf_ds.coords["site"].values))
times_in_both = sorted(set(casa_ds.coords["time"].values) &
                       set(amf_ds.coords["TIMESTAMP_START"].values))
amf_data = amf_ds["ameriflux_carbon_dioxide_flux_estimate"].sel(
    site=sites_in_both, TIMESTAMP_START=times_in_both
).stack(
    data_point=("site", "TIMESTAMP_START")
).dropna("data_point")

casa_data = casa_ds["NEE"].set_index(
    ameriflux_tower_location="Site_Id"
).sel(
    ameriflux_tower_location=amf_data.coords["site"], time=amf_data.coords["TIMESTAMP_START"]
).dropna("data_point")
difference = (amf_data - casa_data).dropna("data_point")
print("Have difference data")

coords = np.empty((difference.shape[0], 3), dtype=np.float32)
values = np.array(difference.values, dtype=np.float32)

data_times_int = difference.coords["TIMESTAMP_START"].values.astype("M8[m]").astype("i8")
data_times_int -= data_times_int[0]
coords[:, 0] = data_times_int.astype(np.float32)
coords[:, 0] /= MINUTES_PER_DAY
# Set to map coordinates in meters
coords[:, 1:] = PROJECTION.transform_points(
    PROJECTION.as_geodetic(),
    difference.coords["Longitude"].values,
    difference.coords["Latitude"].values
)[:, :2]
# Convert to kilometers
coords[:, 1:] /= 1e3

to_delete = [
    coord_name for coord_name in difference.coords
    if (coord_name not in difference.dims and
        "LOCATION" not in coord_name and
        "lat" not in coord_name.lower()
        and "lon" not in coord_name.lower())
]
for coord_name in to_delete:
    del difference.coords[coord_name]

hour_data = np.column_stack([coords, values.astype(np.float32)])
# assert amf_data.attrs["units"] == "umol/m2/s"
# assert casa_data.attrs["units"] == "umol/m2/s"
hour_df = pd.DataFrame(hour_data, columns=["time_days", "x_km", "y_km", "flux_diff_umol_m2_s"])
hour_df.to_csv("ameriflux_minus_casa_hour_towers.csv")

difference_df_rect = difference.to_dataframe(
    name="ameriflux_minus_casa_hour_towers_umol_m2_s"
)["ameriflux_minus_casa_hour_towers_umol_m2_s"].unstack(0)
difference_df_rect.to_csv("ameriflux-minus-casa-half-hour-towers-difference-data-rect.csv")

############################################################
# Create and save a netcdf fiel

difference_xarray = difference.to_dataset(name="ameriflux_minus_casa_carbon_dioxide_flux")
difference_rect_xarray = difference_xarray.unstack("data_point")
for name in ("LOCATION_LAT", "LOCATION_LONG", "LOCATION_ELEV", "Longitude", "Latitude"):
    difference_rect_xarray.coords[name] = difference_rect_xarray.coords[name].mean("TIMESTAMP_START")

difference_rect_xarray["ameriflux_minus_casa_carbon_dioxide_flux"] = (
    difference_rect_xarray["ameriflux_minus_casa_carbon_dioxide_flux"].astype(np.float32)
)
difference_rect_xarray["ameriflux_minus_casa_carbon_dioxide_flux"].attrs.update(dict(
    units="umol/m2/s",
    long_name="ameriflux_minus_casa_surface_upward_mole_flux_of_carbon_dioxide",
    coverage_content_type="modelResult",
))
for name in ("LOCATION_LAT", "Latitude"):
    difference_rect_xarray.coords[name].attrs.update(dict(
        units="degrees_north",
        standard_name="latitude",
        long_name="latitude",
        valid_range=(0., 90.),
    ))

for name in ("LOCATION_LONG", "Longitude"):
    difference_rect_xarray.coords[name].attrs.update(dict(
        units="degrees_east",
        standard_name="longitude",
        long_name="longitude",
        valid_range=(-180., 360.),
    ))

difference_rect_xarray.coords["site_id"] = difference_rect_xarray.coords["site"]
difference_rect_xarray.coords["site_id"].attrs.update(dict(
    cf_role="timeseries_id",
    long_name="AmeriFlux_station_id",
))
difference_rect_xarray.coords["site"] = np.arange(difference_rect_xarray.dims["site"])
difference_rect_xarray.coords["TIMESTAMP_START"].attrs.update(dict(
    axis="T",
    standard_name="time",
    long_name="start_of_ameriflux_averaging_window",
    bounds="time_bnds",
))

for name in ("IGBP", "CLIMATE_KOEPPEN", "SITE_NAME", "IGBP_COMMENT",
             "LOCATION_ELEV", "TERRAIN", "SITE_DESC", "time_bnds"):
    difference_rect_xarray.coords[name] = amf_ds.coords[name]

for name in ("SITE_FUNDING", "ACKNOWLEDGEMENT"):
    difference_rect_xarray.coords["AMERIFLUX_" + name] = amf_ds.coords[name]

PSU = "Pennsylvania State University Department of Meteorology and Atmospheric Science"
UTC = datetime.timezone.utc
NOW = datetime.datetime.now(UTC)
NOW_ISO = NOW.isoformat()
difference_rect_xarray.attrs.update(dict(
    history="""created from processed Ameriflux data files and 500m CASA outputs downscaled using ERA5
ameriflux_history={ameriflux_history}
casa_history={casa_history}
""".format(
    ameriflux_history=amf_ds.attrs["history"],
    casa_history=casa_ds.attrs["history"],
),
    institution=PSU,
    title="Ameriflux minus CASA carbon dioxide flux differences",
    acknowledgement="CASA: ACT-America\nERA5: ECMWF\nAmeriFlux Towers: {ameriflux_sources:s}"
    .format(ameriflux_sources=""),
    cdm_data_type="Station",
    Conventions="CF-1.7,ACDD-1.3",
    creator_email="dfw5129@psu.edu",
    creator_institution=PSU,
    creator_name="Daniel Wesloh",
    creator_type="person",
    date_metadata_modified=NOW_ISO,
    date_modified=NOW_ISO,
    date_created=NOW_ISO,
    date_written=NOW.date().isoformat(),
    time_written=NOW.time().replace(microsecond=0).isoformat(),
    geospatial_lat_min=difference_rect_xarray.coords["Latitude"].min().values,
    geospatial_lat_max=difference_rect_xarray.coords["Latitude"].max().values,
    geospatial_lat_units="degrees_north",
    geospatial_lon_min=difference_rect_xarray.coords["Longitude"].min().values,
    geospatial_lon_max=difference_rect_xarray.coords["Longitude"].max().values,
    geospatial_lon_units="degrees_east",
    product_version=1,
    program="NASA EVS",
    project="Atmospheric Carbon and Transport-America",
    source="CASA from Yu et al. (2020), retrieved from ORNL; AmeriFlux data from various contributors",
    standard_name_vocabulary="CF Standard Name table v70",
    time_coverage_start=difference_rect_xarray.indexes["TIMESTAMP_START"][0].isoformat(),
    time_coverage_end=difference_rect_xarray.indexes["TIMESTAMP_START"][-1].isoformat(),
    time_coverage_duration=(
        difference_rect_xarray.indexes["TIMESTAMP_START"][-1] -
        difference_rect_xarray.indexes["TIMESTAMP_START"][0]
    ).isoformat(),
    # "P0006-08-30T00:00:00",
    time_coverage_resolution="PT1H",
    ncei_template_version="NCEI_NetCDF_TimeSeries_Orthogonal_Template_v2.0",
    featureType="timeSeries",
))

encoding = {name: {"_FillValue": -99, "zlib": True}
            for name in difference_rect_xarray.data_vars}
encoding.update({name: {"_FillValue": None}
                 for name in difference_rect_xarray.data_vars})

difference_rect_xarray.to_netcdf("ameriflux_minus_casa_half_hour_tower_data.nc4",
                                 encoding=encoding, format="NETCDF4_CLASSIC")


# Will be in meters
distance_matrix = pd.DataFrame(
    index=difference_df_rect.columns,
    columns=difference_df_rect.columns,
    dtype=np.float64
)
site_coords = amf_ds.coords["site"].sel(
    site=difference_df_rect.columns
)
for site1, site2 in itertools.product(site_coords, site_coords):
    distance_matrix.loc[site1.values[()], site2.values[()]] = GEOD.line_length(
        [site1.coords["LOCATION_LONG"], site2.coords["LOCATION_LONG"]],
        [site1.coords["LOCATION_LAT"], site2.coords["LOCATION_LAT"]]
    )

# Convert distance to kilometers
# Will improve conditioning of later problems
distance_matrix /= 1000
distance_matrix.to_csv("ameriflux-half-hour-towers-distance-matrix-km.csv")

length_opt = scipy.optimize.minimize_scalar(
    fun=lambda length, corr, dist: nansum(square(corr - np.exp(-dist / length))),
    args=(difference_df_rect.corr().values, distance_matrix.values),
    bounds=(1, 1e3), method="bounded"
)
print("Optimizing length alone:\n", length_opt)

length_with_nugget_opt = scipy.optimize.minimize(
    fun=lambda params, corr, dist: nansum(square(
        corr - (
            params[0] * exp(-dist / params[1]) +
            (1 - params[0])
        )
    )),
    # Nondimensional, meters
    x0=[.8, 200],
    args=(difference_df_rect.corr().values, distance_matrix.values),
)
print("Optimizing length with nugget effect:",
      "\nWeight on correlated part:", length_with_nugget_opt.x[0],
      "\nCorrelation length:", length_with_nugget_opt.x[1],
      "\nConvergence:", length_with_nugget_opt.success, length_with_nugget_opt.message,
      "\nInverse Hessian:\n", length_with_nugget_opt.hess_inv)


def count_pairs(col):
    """Count the number of pairs for each lag.

    Parameters
    ----------
    col: pd.Series

    Returns
    -------
    n_pairs: np.ndarray
    """
    have_data = ~col.isnull()
    n_data = len(col)
    embedded = np.zeros(2 * n_data - 1)
    embedded[:n_data] = have_data
    spectrum = np.fft.fft(embedded)
    pair_count = np.round(np.fft.ifft(spectrum.conj() * spectrum).real).astype(int)
    return pair_count

print("Starting temporal autocorrelation analysis")
acovf_index = pd.timedelta_range(start=0, freq="1H", periods=24 * 365 * 8)
acovf_data = pd.DataFrame(index=acovf_index)
acf_data = pd.DataFrame(index=acovf_index)
pair_counts = pd.DataFrame(index=acovf_index)

for column in difference_df_rect.columns:
    col_data = difference_df_rect.loc[:, column].dropna()
    if col_data.shape[0] == 0:
        continue
    col_data = col_data.resample("1H").mean()
    acovf_col = acovf(col_data, missing="conservative")
    nlags = len(acovf_col)
    acovf_data.loc[acovf_index[:nlags], column] = acovf_col
    acf_col = acf(col_data, missing="conservative", nlags=nlags, unbiased=True)
    acf_data.loc[acovf_index[:nlags], column] = acf_col
    pair_counts.loc[acovf_index[:nlags], column] = count_pairs(col_data)[:nlags]

to_fit = acf_data.loc[~acf_data.isna().all(axis=1), :]
time_in_days = to_fit.index.values.astype("m8[h]").astype(np.int64) / 24

acf_data.to_csv("ameriflux-minus-casa-half-hour-towers-autocorrelation-functions.csv")
pair_counts.to_csv("ameriflux-minus-casa-half-hour-towers-pair-counts.csv")
acovf_data.to_csv("ameriflux-minus-casa-half-hour-towers-autocovariance-functions.csv")

# corr_to_fit, time_in_days = np.broadcast_arrays(to_fit.values, time_in_days[:, newaxis])
# not_nan = np.isfinite(corr_to_fit)
# corr_to_fit = corr_to_fit[not_nan]
# time_in_days = time_in_days[not_nan]

single_time_opt = scipy.optimize.minimize_scalar(
    lambda length, acorr, times: nansum(square(
            acorr - exp(-times / length)[:, newaxis]
    )), args=(to_fit.values, time_in_days),
    method="bounded", bounds=(0, 365*5)
)
# Returns just over the lower bound if I make the lower bound more
# than one.
print("Parameters for exp(-dt/T):")
print(single_time_opt.x)

two_time_opt = scipy.optimize.minimize(
    fun=lambda params, acorr, times: nansum(square(
            acorr - 
            (
                params[0] * exp(-times / (params[1] * DAYS_PER_WEEK)) +
                (1 - params[0]) * exp(-times / (params[2] / HOURS_PER_DAY))
            )[:, np.newaxis]
    )),
    x0=(.8, 3., 3.),
    args=(to_fit.values, time_in_days),
    method="L-BFGS-B"
)
# Around a twenty-day correlation period, with most weight on EC error
print("Parameters for a exp(-dt/T) + (1 - a) exp(-dt/Tec): [a, T, Tec]")
print(two_time_opt)
print("Units: unitless, weeks, hours")
# print("EC time in hours:", two_time_opt.x[2] * HOURS_PER_DAY)

cos_opt = scipy.optimize.minimize(
    fun=lambda params, acorr, times: nansum(square(
            # [a, b0, b1, b2, c, d, Td, Ta, To, Tec]
            acorr - 
            (
                params[0] * cos(TWO_PI_OVER_DAY * times) * exp(-times / (params[6] * DAYS_PER_WEEK)) +
                (
                    params[1] / 10 +
                    params[2] / 10 * cos(TWO_PI_OVER_YEAR * times) +
                    params[3] / 10 * cos(2 * TWO_PI_OVER_YEAR * times)
                ) * exp(-times / (params[7] * DAYS_PER_YEAR)) +
                params[4] * exp(-times / (params[8] * DAYS_PER_WEEK)) +
                params[5] * exp(-times / (params[9] / HOURS_PER_DAY))
            )#[:, np.newaxis]
    )),
    x0=(.2, .2, .2, .2, .2, .2, 2, 3, 5, 3.),
    args=(to_fit.mean(axis=1).values, time_in_days),
    method="L-BFGS-B",
    # options=dict(maxiter=100, disp=True),
)

print("Parameters for cosine:",
      "\nDaily coefficient and timescale (weeks):", cos_opt.x[[0, 6]],
      "\nAnnual coefficients * 10 and timescale (years):", cos_opt.x[[1, 2, 3, 7]],
      # "\nAnnual timescale in years:", cos_opt.x[7] / DAYS_PER_YEAR,
      "\nResidual coefficient and timescale (weeks):", cos_opt.x[[4, 8]],
      "\nEddy Covariance coefficient and timescale (hours):", cos_opt.x[[5, 9]],
      # "\nEC timescale in hours:", cos_opt.x[9] * HOURS_PER_DAY,
      "\nConverged:", cos_opt.success, cos_opt.message)

exp_sin2_opt = scipy.optimize.minimize(
    fun=lambda params, acorr, times: nansum(square(
            # [a, b, c, d, ld, la, Td, Ta, To, Tec]
            acorr - 
            (
                params[0] * exp(-(sin(TWO_PI_OVER_DAY * times) / params[4]) ** 2) *
                  exp(-times / (params[6] * DAYS_PER_WEEK)) +
                params[1] * exp(-(sin(TWO_PI_OVER_YEAR * times) / params[5]) ** 2) *
                  exp(-times / (params[7] * DAYS_PER_YEAR)) +
                params[2] * exp(-times / (params[8] * DAYS_PER_WEEK)) +
                params[3] * exp(-times / (params[9] / HOURS_PER_DAY))
            )[:, np.newaxis]
    )),
    x0=(.2, .2, .2, .2, 10, 10, 2, 3, 5, 3.),
    args=(to_fit.values, time_in_days),
    method="L-BFGS-B"
)

print("Parameters for exponential sin-squared:",
      "\nDaily coefficient, dieoff, and timescale:", exp_sin2_opt.x[[0, 4, 6]],
      "\nAnnual coefficient, dieoff, and timescale:", exp_sin2_opt.x[[1, 5, 7]],
      "\nAnnual timescale in years:", exp_sin2_opt.x[7] / DAYS_PER_YEAR,
      "\nResidual coefficient and timescale:", exp_sin2_opt.x[[2, 8]],
      "\nEddy Covariance coefficient and timescale:", exp_sin2_opt.x[[3, 9]],
      "\nEC timescale in hours:", exp_sin2_opt.x[9] * HOURS_PER_DAY,
      "\nConverged:", exp_sin2_opt.success, exp_sin2_opt.message)

acf_data.plot(
    subplots=True, sharex=True, sharey=True,
    xlim=(0, 1e9 * 3600 * 24 * 365.2425 * 5), ylim=(-.5, 1),
    xticks=pd.timedelta_range(start=0, freq="365D", periods=6).to_numpy().astype(float)
)
plt.savefig("ameriflux_minus_casa_half_hour_tower_data_long.pdf")

plt.xlim(0, 1e9 * 3600 * 24 * 60)
plt.xticks(pd.timedelta_range(start=0, freq="7D", periods=8).to_numpy().astype(float))
plt.savefig("ameriflux_minus_casa_half_hour_tower_data_short.pdf")


# Functions for errors correlated over only a few days


def exp_only(tdata, resid_coef, To, Tec):
    """Current practice: Decaying exponential

    d_0 dm_0 a_0
    """
    Tec /= HOURS_PER_DAY
    To *= DAYS_PER_WEEK
    exp = np.exp
    result = resid_coef * exp(-tdata / To)
    result += (1 - resid_coef) * exp(-tdata / Tec)
    return result


def exp_cos_daily(tdata, daily_coef, Td, resid_coef, To, ec_coef, Tec):
    """Errors in daily cycle are correlated day-night

    d_c dm_0 a_0
    """
    Tec /= HOURS_PER_DAY
    To *= DAYS_PER_WEEK
    Td *= DAYS_PER_WEEK
    exp = np.exp
    result = daily_coef * np.cos(TWO_PI_OVER_DAY * tdata) * exp(-tdata / Td)
    result += resid_coef * exp(-tdata / To)
    result += ec_coef * exp(-tdata / Tec)
    return result


# Functions where errors in the daily cycle are correlated over a few
# days and errors in the seasonal cycle are correlated over years


def exp_cos_daily_annual(tdata, daily_coef, Td, ann_coef0, ann_coef1, ann_coef2, Ta, resid_coef, To, ec_coef, Tec):
    """Errors in daily cycle are correlated day-night, Correlated errors in seasonal cycle

    d_c dm_0 a_c
    """
    Tec /= HOURS_PER_DAY
    Td *= DAYS_PER_WEEK
    Ta *= DAYS_PER_YEAR
    To *= DAYS_PER_WEEK
    exp = np.exp
    cos = np.cos
    result = daily_coef * cos(TWO_PI_OVER_DAY * tdata) * exp(-tdata / Td)
    result += (ann_coef0 + ann_coef1 * cos(TWO_PI_OVER_YEAR * tdata) +
               ann_coef2 * cos(FOUR_PI_OVER_YEAR * tdata)) * exp(-tdata / Ta)
    result += resid_coef * exp(-tdata / To)
    result += ec_coef * exp(-tdata / Tec)
    return result


def exp_cos_daily_expsin2_annual(tdata, daily_coef, Td, ann_coef, ann_width, Ta, resid_coef, To, ec_coef, Tec):
    """Errors in daily cycle correlated day-night + Correlated errors in seasonal cycle are only positive

    d_c dm_0 a_p
    """
    Tec /= HOURS_PER_DAY
    Td *= DAYS_PER_WEEK
    Ta *= DAYS_PER_YEAR
    To *= DAYS_PER_WEEK
    cos = np.cos
    exp = np.exp
    result = daily_coef * cos(TWO_PI_OVER_DAY * tdata) * exp(-tdata / Td)
    result += ann_coef * exp(-(np.sin(PI_OVER_YEAR * tdata) / ann_width) ** 2 - tdata / Ta)
    result += resid_coef * exp(-tdata / To)
    result += ec_coef * exp(-tdata / Tec)
    return result


# Functions where the daily cycle is off the same way for years


def exp_cos_daily_times_annual(
    tdata,
    dann_coef0, dann_coef1, dann_coef2, Tad,
    resid_coef, To,
    ec_coef, Tec):
    """Errors in daily cycle correlated day-night, recur same time next year

    d_c dm_c a_0
    """
    Tec /= HOURS_PER_DAY
    Tad *= DAYS_PER_YEAR
    To *= DAYS_PER_WEEK
    cos = np.cos
    exp = np.exp
    result = (
        cos(TWO_PI_OVER_DAY * tdata) *
        (dann_coef0 + dann_coef1 * cos(TWO_PI_OVER_YEAR * tdata) +
         dann_coef2 * cos(FOUR_PI_OVER_YEAR * tdata)) * exp(-tdata / Tad)
    )
    result += resid_coef * exp(-tdata / To)
    result += ec_coef * exp(-tdata / Tec)
    return result


def exp_expsin2_daily_times_cos_annual(
    tdata, daily_width,
    dann_coef0, dann_coef1, dann_coef2, Tad,
    resid_coef, To,
    ec_coef, Tec
):
    """Errors in daily cycle not correlated day-night, may be anticorrelated at some lags

    d_p dm_c a_0
    """
    Tec /= HOURS_PER_DAY
    Tad *= DAYS_PER_YEAR
    To *= DAYS_PER_WEEK
    cos = np.cos
    exp = np.exp
    result = (
        exp(-(np.sin(PI_OVER_DAY * tdata) / daily_width) ** 2) *
        (dann_coef0 + dann_coef1 * cos(TWO_PI_OVER_YEAR * tdata) +
         dann_coef2 * cos(FOUR_PI_OVER_YEAR * tdata)) * exp(-tdata / Tad)
    )
    result += resid_coef * exp(-tdata / To)
    result += ec_coef * exp(-tdata / Tec)
    return result


def exp_cos_daily_times_expsin2_annual(
    tdata,
    ann_coef, ann_width, Ta,
    resid_coef, To,
    ec_coef, Tec):
    """Errors in daily cycle correlated day-night, are always of same sign day-day

    d_c dm_p a_0
    """
    Tec /= HOURS_PER_DAY
    Ta *= DAYS_PER_YEAR
    To *= DAYS_PER_WEEK
    exp = np.exp
    result = (
        np.cos(TWO_PI_OVER_DAY * tdata) *
        ann_coef *
        exp(-(np.sin(PI_OVER_YEAR * tdata) / ann_width) ** 2)
    )
    result += resid_coef * exp(-tdata / To)
    result += ec_coef * exp(-tdata / Tec)
    return result


# Functions where seasonal cycle is off and daily cycle is off


def exp_cos_daily_times_cos_annual_plus_cos_annual(
    tdata,
    dann_coef0, dann_coef1, dann_coef2, Tad,
    ann_coef0, ann_coef1, ann_coef2, Ta,
    resid_coef, To, ec_coef, Tec
):
    """Daily cycle errors not correlated day-night, may be anticorrelated, seasonal errors correlated

    d_c dm_c a_c
    """
    Tec /= HOURS_PER_DAY
    Ta *= DAYS_PER_YEAR
    To *= DAYS_PER_WEEK
    cos = np.cos
    exp = np.exp
    result = (
        cos(TWO_PI_OVER_DAY * tdata) *
        (dann_coef0 + dann_coef1 * cos(TWO_PI_OVER_YEAR * tdata) +
         dann_coef2 * cos(FOUR_PI_OVER_YEAR * tdata)) * exp(-tdata / Tad)
    )
    result += (
        ann_coef0 + ann_coef1 * cos(TWO_PI_OVER_YEAR * tdata) +
        ann_coef2 * cos(FOUR_PI_OVER_YEAR * tdata)
    ) * exp(-tdata / Ta)
    result += resid_coef * exp(-tdata / To)
    result += ec_coef * exp(-tdata / Tec)
    return result


def exp_expsin2_daily_times_cos_annual_plus_cos_annual(
    tdata, daily_width,
    dann_coef0, dann_coef1, dann_coef2, Tad,
    ann_coef0, ann_coef1, ann_coef2, Ta,
    resid_coef, To, ec_coef, Tec
):
    """Daily cycle errors not correlated day-night, may be anticorrelated, seasonal errors correlated

    d_p dm_c a_c
    """
    Tec /= HOURS_PER_DAY
    Ta *= DAYS_PER_YEAR
    To *= DAYS_PER_WEEK
    cos = np.cos
    exp = np.exp
    result = (
        exp(-(np.sin(PI_OVER_DAY * tdata) / daily_width) ** 2) *
        (dann_coef0 + dann_coef1 * cos(TWO_PI_OVER_YEAR * tdata) +
         dann_coef2 * cos(FOUR_PI_OVER_YEAR * tdata)) * exp(-tdata / Tad)
    )
    result += (
        ann_coef0 + ann_coef1 * cos(TWO_PI_OVER_YEAR * tdata) +
        ann_coef2 * cos(FOUR_PI_OVER_YEAR * tdata)
    ) * exp(-tdata / Ta)
    result += resid_coef * exp(-tdata / To)
    result += ec_coef * exp(-tdata / Tec)
    return result



def exp_cos_daily_times_expsin2_annual_plus_cos_annual(
    tdata,
    dann_coef, dann_width, Tad,
    ann_coef0, ann_coef1, ann_coef2, Ta,
    resid_coef, To, ec_coef, Tec
):
    """Daily cycle errors not correlated day-night, may be anticorrelated, seasonal errors correlated"""
    Tec /= HOURS_PER_DAY
    Ta *= DAYS_PER_YEAR
    To *= DAYS_PER_WEEK
    cos = np.cos
    exp = np.exp
    result = (
        dann_coef * cos(TWO_PI_OVER_DAY * tdata) *
        exp(-np.sin(PI_OVER_YEAR * tdata / dann_width) ** 2 - tdata / Tad)
    )
    result += (
        ann_coef0 + ann_coef1 * cos(TWO_PI_OVER_YEAR * tdata) +
        ann_coef2 * cos(FOUR_PI_OVER_YEAR * tdata)
    ) * exp(-tdata / Ta)
    result += resid_coef * exp(-tdata / To)
    result += ec_coef * exp(-tdata / Tec)
    return result


def exp_expsin2_daily_times_expsin2_annual_plus_cos_annual(
    tdata, daily_width,
    dann_coef, dann_width, Tad,
    ann_coef0, ann_coef1, ann_coef2, Ta,
    resid_coef, To, ec_coef, Tec
):
    """Daily cycle errors not correlated day-night, may be anticorrelated, seasonal errors correlated

    d_c dm_p a_c
    """
    Tec /= HOURS_PER_DAY
    Ta *= DAYS_PER_YEAR
    To *= DAYS_PER_WEEK
    sin = np.sin
    cos = np.cos
    exp = np.exp
    result = (
        dann_coef *
        exp(
            -sin(PI_OVER_DAY * tdata / daily_width) ** 2
            -sin(PI_OVER_YEAR * tdata / dann_width) ** 2
            - tdata / Tad
        )
    )
    result += (
        ann_coef0 + ann_coef1 * cos(TWO_PI_OVER_YEAR * tdata) +
        ann_coef2 * cos(FOUR_PI_OVER_YEAR * tdata)
    ) * exp(-tdata / Ta)
    result += resid_coef * exp(-tdata / To)
    result += ec_coef * exp(-tdata / Tec)
    return result


CORR_FUNS = (
    exp_only,
    exp_cos_daily,
    exp_cos_daily_annual,
    exp_cos_daily_expsin2_annual,
    exp_cos_daily_times_annual,
    exp_expsin2_daily_times_cos_annual,
    exp_cos_daily_times_expsin2_annual,
    exp_cos_daily_times_cos_annual_plus_cos_annual,
    exp_cos_daily_times_expsin2_annual_plus_cos_annual,
    exp_expsin2_daily_times_cos_annual_plus_cos_annual,
    exp_expsin2_daily_times_expsin2_annual_plus_cos_annual,
)

STARTING_PARAMS = dict(
    daily_coef = 0.4,
    daily_width = .3,
    Td = 3.,
    ann_coef0 = -1e-3,
    ann_coef1 = +1e-2,
    ann_coef2 = +1e-2,
    dann_coef = 1e-3,
    dann_width = .3,
    dann_coef0 = -1e-3,
    dann_coef1 = +1e-2,
    dann_coef2 = +1e-2,
    ann_coef = 0.04,
    ann_width = .3,
    Ta = 3.,
    Tad = 3.,
    resid_coef = 0.2,
    To = 3.,
    ec_coef = 0.4,
    Tec = 3.,
)

COEF_DATA = pd.DataFrame(
    columns=STARTING_PARAMS.keys(),
    index=pd.MultiIndex.from_product(
        [acf_data,
         [fun.__name__ for fun in CORR_FUNS]],
        names=["Site", "Correlation function"]
    )
)
COEF_VAR_DATA = pd.DataFrame(
    columns=STARTING_PARAMS.keys(),
    index=pd.MultiIndex.from_product(
        [acf_data,
         [fun.__name__ for fun in CORR_FUNS]],
        names=["Site", "Correlation function"]
    )
)
FIT_ERROR = pd.DataFrame(
    columns=["weighted_error", "MSE", "MAE", "MAR-r"],
    index=pd.MultiIndex.from_product(
        [acf_data,
         [fun.__name__ for fun in CORR_FUNS]],
        names=["Site", "Correlation function"]
    )
)
INF_CRIT = (aic, aicc, bic, hqic)
IC_DATA = pd.DataFrame(
    columns=[ic.__name__ for ic in INF_CRIT],
    index=pd.MultiIndex.from_product(
        [acf_data,
         [fun.__name__ for fun in CORR_FUNS]],
        names=["Site", "Correlation function"]
    )
)
SAMPLE_SIZE = 2000
MVN_LOGPDF = scipy.stats.multivariate_normal.logpdf
MIN_LAGS_FOR_FIT = pd.Timedelta(50, "W")

for column in acf_data.iloc[:, :]:
    print(column, flush=True)
    data_col = difference_df_rect[column]
    acf_pair_counts = pair_counts.loc[:, column].dropna()
    acf_col = acf_data[column].dropna()
    amf_col = amf_ds["ameriflux_carbon_dioxide_flux_estimate"].sel(site=column)
    casa_col = casa_ds["NEE"].set_index(
        ameriflux_tower_location="Site_Id"
    ).sel(ameriflux_tower_location=column)
    # .dropna("time").resample(time="1H").mean()
    fig, axes = plt.subplots(5, 1, figsize=(6.5, 8))
    for ax in axes[:-1]:
        tmp = ax.axhline(0)
    casa_line = casa_col.plot(ax=axes[0])
    amf_line = amf_col.plot(ax=axes[0])
    tmp = axes[0].set_title("Hourly fluxes")
    tmp = axes[0].set_ylabel("Flux\n\N{MICRO SIGN}mol/m\N{SUPERSCRIPT TWO}/s")
    tmp = axes[0].set_xlabel("Date")
    resampled_casa = casa_col.resample(time="1W").mean()
    casa_line = axes[1].plot(resampled_casa.coords["time"].values,
                             resampled_casa.values, label="CASA")
    resampled_amf = amf_col.resample(TIMESTAMP_START="1W").mean()
    amf_line = axes[1].plot(resampled_amf.coords["TIMESTAMP_START"].values,
                            resampled_amf.values, label="AmeriFlux")
    tmp = axes[1].set_title("Weekly-average fluxes")
    tmp = axes[1].set_ylabel("Flux\n\N{MICRO SIGN}mol/m\N{SUPERSCRIPT TWO}/s")
    tmp = fig.legend(handles=[casa_line[0], amf_line[0]],
                     labels=["CASA", "AmeriFlux"], ncol=2)
    tmp = axes[1].set_xlabel("Date")
    tmp = data_col.plot(ax=axes[2])
    tmp = axes[2].set_title("Ameriflux minus CASA Residuals")
    tmp = axes[2].set_ylabel("Residuals\n(\N{MICRO SIGN}mol/m\N{SUPERSCRIPT TWO}/s)")
    tmp = axes[2].set_xlabel("Date")
    # tmp = acf_col.plot(ax=axes[3])
    tmp = axes[3].plot(acf_col.index, acf_col.values)
    tmp = axes[3].set_ylim(-1, 1)
    tmp = axes[3].set_title("Autocorrelation function")
    tmp = axes[3].set_ylabel("Correlation")
    tmp = (acf_pair_counts / 1000).plot(ax=axes[4])
    tmp = axes[4].set_ylim(0, acf_pair_counts[0] / 1000)
    tmp = axes[4].set_title("Number of pairs used for ACF")
    tmp = axes[4].set_ylabel("Count\n(thousands)")
    dates = pd.date_range(data_col.index[0], data_col.index[-1], freq="1AS")
    minor_dates = pd.date_range(data_col.index[0], data_col.index[-1], freq="3MS")
    for ax in axes[:3]:
        tmp = ax.set_xlim(data_col.index[0], data_col.index[-1])
        tmp = ax.set_xticks(dates)
        tmp = ax.set_xticklabels(
            dates.strftime("%Y-%m"), rotation=10,
            verticalalignment="top", horizontalalignment="right"
        )
        tmp = ax.set_xticks(minor_dates, minor=True)
    xticklocs = pd.timedelta_range(start=0, freq="365D", periods=7)
    minor_dts = pd.timedelta_range(start=0, freq="91D", periods=28)
    for ax in axes[3:]:
        tmp = ax.set_xlim(acf_col.index[0].to_numpy().astype("i8").astype(float),
                          acf_col.index[-1].to_numpy().astype("i8").astype(float))
        tmp = ax.set_xticks(
            xticklocs.to_numpy().astype("i8").astype(float)
        )
        tmp = ax.set_xticklabels(xticklocs.days)
        tmp = ax.set_xlabel("Lag (days)")
    tmp = fig.suptitle(
        "{site:s} - {climate:s} - {veg:s}".format(
            site=column,
            climate=amf_ds.coords["CLIMATE_KOEPPEN"].sel(site=column).values,
            veg=amf_ds.coords["IGBP"].sel(site=column).values,
        )
    )
    fig.tight_layout()
    fig.subplots_adjust(hspace=1, top=.93)
    fig.savefig(
        "{site:s}-ameriflux-minus-casa-resid-acf-counts.pdf".format(site=column)
    )
    plt.close(fig)
    acf_col = acf_col[acf_pair_counts > 0].dropna()
    acf_pair_counts = pair_counts.loc[acf_col.index, column]
    if acf_col.index[-1] < MIN_LAGS_FOR_FIT:
        continue
    acf_times = acf_col.index.values.astype("m8[h]").astype("u8")
    acf_times -= acf_times[0]
    acf_times = acf_times.astype("f4") / 24
    fig, axes = plt.subplots(len(CORR_FUNS) + 1, 1, figsize=(6.5, 5),
                             sharex=True, sharey=True)
    tmp = axes[0].plot(acf_times, acf_col)
    tmp = axes[0].set_title("Empirical Correlogram")
    tmp = fig.suptitle(
        "{site:s} - {climate:s} - {veg:s}".format(
            site=column,
            climate=amf_ds.coords["CLIMATE_KOEPPEN"].sel(site=column).values,
            veg=amf_ds.coords["IGBP"].sel(site=column).values,
        )
    )
    # col_data = difference_df_rect.loc[:, column].dropna()
    # sample = col_data.sample(min(SAMPLE_SIZE, col_data.shape[0]))
    # sample /= sample.std()
    # sample_times = acf_col.index.values.astype("M8[h]").astype("u8")
    # sample_times -= sample_times[0]
    # sample_times = sample_times.astype("f4") / 24
    # dt_sample = np.abs(sample_times[:, np.newaxis] - sample_times[np.newaxis, :])
    uncertainty = 1. / np.sqrt(acf_pair_counts + 1e-30).astype(np.float32)
    for corr_fun, ax in zip(CORR_FUNS, axes[1:]):
        argspec = inspect.getfullargspec(corr_fun)
        param_names = inspect.getfullargspec(corr_fun).args[1:]
        try:
            param_vals, param_cov = scipy.optimize.curve_fit(
                corr_fun, acf_times, acf_col,
                [STARTING_PARAMS[param] for param in param_names],
                sigma=uncertainty
            )
        except RuntimeError:
            continue
        COEF_DATA.loc[(column, corr_fun.__name__), param_names] = param_vals
        COEF_VAR_DATA.loc[(column, corr_fun.__name__), param_names] = np.diag(param_cov)
        fitted_acf = corr_fun(acf_times, *param_vals)
        tmp = ax.plot(acf_times, fitted_acf, label="ACF fit")
        acf_fit_resids = acf_col - fitted_acf
        FIT_ERROR.loc[(column, corr_fun.__name__), :] = [
            np.sum(np.square(acf_fit_resids / uncertainty)),
            np.sum(np.square(acf_fit_resids)),
            np.mean(np.abs(acf_fit_resids)),
            np.median(np.abs(acf_fit_resids)),
        ]
        # def loglik_fn(params):
        #     corr_mat = corr_fun(dt_sample, *params)
        #     return MVN_LOGPDF(sample.values, cov=corr_mat)
        # # res = scipy.optimize.minimize(lambda params: -loglik_fn(params), param_vals)
        # # ax.plot(acf_times, corr_fun(acf_times, *res.x), label="ML fit")
        # # ax.legend()
        # loglik = loglik_fn(param_vals)
        # for ic_fun in INF_CRIT:
        #     IC_DATA.loc[(column, corr_fun.__name__), ic_fun.__name__] = ic_fun(loglik, 1, len(param_names))
        # ic_str = "AIC: {aic:3.2e} AICC: {aicc:3.2e} BIC: {3.2e} HQIC: {3.2e}".format(
        #     IC_DATA.loc[(column, corr_fun.__name__), :]
        # )
        # ax.set_title(
        #     "Fit of {corr_fun:s}  (ic_str:s}".format(
        #         corr_fun=corr_fun.__name__, ic_str=ic_str
        #     )
        # )
        tmp = ax.set_title("Fit of {corr_fun:s}".format(corr_fun=corr_fun.__name__))
    tmp = fig.tight_layout()
    tmp = fig.subplots_adjust(top=.9, hspace=1.1)
    tmp = ax.set_xlim(0, 365.2425 * 3)
    tmp = ax.set_ylim(-1, 1)
    for ax in axes:
        tmp = ax.set_xticks(pd.timedelta_range(start=0, freq="365D", periods=6).to_numpy()
                            .astype("m8[D]").astype("u8").astype(float))
    tmp = fig.savefig("{site:s}-ameriflux-minus-casa-corr-fits-long.pdf".format(site=column))
    tmp = ax.set_xlim(0, 56)
    for ax in axes:
        tmp = ax.set_xticks(pd.timedelta_range(start=0, freq="7D", periods=9).to_numpy()
                            .astype("m8[D]").astype("u8").astype(float))
    tmp = fig.savefig("{site:s}-ameriflux-minus-casa-corr-fits-short.pdf".format(site=column))
    plt.close(fig)

COEF_DATA.to_csv("ameriflux-minus-casa-half-hour-towers-parameters.csv")
COEF_VAR_DATA.to_csv("ameriflux-minus-casa-half-hour-towers-parameter-variances.csv")
FIT_ERROR.to_csv("ameriflux-minus-casa-half-hour-towers-correlation-function-fits.csv")


for column in sorted(set(COEF_DATA.index.get_level_values(0))):
    fig, axes = plt.subplots(4, 1, figsize=(6.5, 4),
                             sharex=True, sharey=True)
    fig.suptitle("{site:s} - {climate:s} - {veg:s}".format(
            site=column,
            climate=amf_ds.coords["CLIMATE_KOEPPEN"].sel(site=column).values,
            veg=amf_ds.coords["IGBP"].sel(site=column).values,
        )
    )
    acf_col = acf_data[column].dropna()
    acf_times = acf_col.index.values.astype("m8[h]").astype(float) / HOURS_PER_DAY
    acf_col.plot(ax=axes[0])
    axes[0].set_xticks(pd.timedelta_range(start=0, freq="365D", periods=6)
                  .to_numpy().astype("i8").astype(float))
    axes[0].set_xticks(pd.timedelta_range(start=0, freq="91D", periods=24)
                  .to_numpy().astype("i8").astype(float), minor=True)
    axes[0].set_xticklabels(["{num:d} years".format(num=num)
                        for num in range(6)])
    ax.set_ylim(-1, 1)
    for ax, fit_name in zip(
        axes[1:], 
        FIT_ERROR.loc[(column, slice(None)), :].sort_values("weighted_error").index.get_level_values(1)
    ):
        corr_params = COEF_DATA.loc[(column, fit_name), :].dropna()
        if len(corr_params) == 0:
            continue
        ax.plot(
            acf_col.index,
            eval(fit_name)(acf_times, **corr_params)
        )
        ax.set_title(fit_name)
        ax.set_xticks(pd.timedelta_range(start=0, freq="365D", periods=6)
                      .to_numpy().astype("i8").astype(float))
        ax.set_xticks(pd.timedelta_range(start=0, freq="91D", periods=24)
                      .to_numpy().astype("i8").astype(float), minor=True)
        ax.set_xticklabels(["{num:d} years".format(num=num)
                            for num in range(6)])
        ax.set_ylim(-1, 1)
    fig.tight_layout()
    fig.subplots_adjust(top=.9)
    fig.savefig("{column:s}-top-fits.pdf".format(column=column))
    plt.close(fig)

################################################################################

BEST_FITS = FIT_ERROR.sort_values(["Site", "weighted_error"]).groupby("Site").head(1).reset_index(level=1)
BEST_FITS["Correlation function"] = pd.Categorical(BEST_FITS["Correlation function"])
BEST_FITS.groupby("Correlation function").count()["weighted_error"].to_csv(
    "ameriflux-minus-casa-half-hour-towers-correlation-function-best-fit-counts.csv"
)

TOWER_NAMES = BEST_FITS.index
TOWER_CORR_FUNS = BEST_FITS["Correlation function"]
AMF_VARS_TO_USE = ["IGBP", "LOCATION_LAT", "LOCATION_LONG", "STATE",
                   "UTC_OFFSET", "CLIMATE_KOEPPEN", "FLUX_MEASUREMENTS_METHOD",
                   "LOCATION_ELEV", "TERRAIN", "ASPECT"]
CASA_VARS_TO_USE = ["Vegetation", "Mean_Temp", "Mean_Preci", "Elevation",
                    "Longitude", "Years_of_D", "Latitude", "Climate_Cl"]

amf_var_data = amf_ds[AMF_VARS_TO_USE].sel(site=TOWER_NAMES).to_dataframe()[AMF_VARS_TO_USE]
amf_var_data["LOCATION_ELEV"] = amf_var_data["LOCATION_ELEV"].astype(np.float32)
for column in amf_var_data:
    if amf_var_data[column].dtype == object:
        amf_var_data[column] = pd.Categorical(amf_var_data[column])

casa_var_data = casa_ds[CASA_VARS_TO_USE].set_index(
    ameriflux_tower_location="Site_Id"
).sel(ameriflux_tower_location=TOWER_NAMES).to_dataframe()[CASA_VARS_TO_USE]
for column in ["Vegetation", "Climate_Cl"]:
    casa_var_data[column] = pd.Categorical(casa_var_data[column])

best_fits_with_explanatory_data = pd.concat((BEST_FITS, amf_var_data, casa_var_data), axis=1)
best_fits_with_explanatory_data.to_csv(
    "ameriflux-minus-casa-half-hour-towers-correlation-functions-best-fits-explanatory-vars.csv"
)

import patsy
design_matrix = patsy.dmatrix(
    "0 + IGBP + LOCATION_LAT + LOCATION_LONG + CLIMATE_KOEPPEN + FLUX_MEASUREMENTS_METHOD"
    " + LOCATION_ELEV + Mean_Temp + Mean_Preci + Vegetation + Climate_Cl",
    best_fits_with_explanatory_data
)
sparse_explanatory_data = pd.DataFrame(
    design_matrix,
    columns=design_matrix.design_info.column_names,
    index=best_fits_with_explanatory_data.index,
    dtype=pd.SparseDtype(np.float32, 0.0)
)

import sklearn.tree
tree_model = sklearn.tree.DecisionTreeClassifier(max_depth=3)
classifier = tree_model.fit(sparse_explanatory_data, TOWER_CORR_FUNS)

with open("ameriflux-minus-casa-best-fits-tree.txt", "w") as out_file:
    print(sklearn.tree.export.export_text(classifier, list(sparse_explanatory_data.columns)), file=out_file)
    print(sparse_explanatory_data.columns, file=out_file)

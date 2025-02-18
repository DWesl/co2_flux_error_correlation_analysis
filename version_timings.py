import inspect

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import scipy.optimize
import perfplot

import flux_correlation_functions

HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365.2425
HOURS_PER_YEAR = HOURS_PER_DAY * DAYS_PER_YEAR
N_YEARS_DATA = 4

STARTING_PARAMS = dict(
    daily_coef = 0.2,
    daily_coef1 = .6,
    daily_coef2 = .5,
    daily_width = .4,
    Td = 30,  # weeks
    dm_width = .3,
    dm_coef1 = .1,
    dm_coef2 = +.3,
    ann_coef1 = +.3,
    ann_coef2 = +.3,
    ann_coef = 0.1,
    ann_width = .3,
    Ta = 30.,  # years
    resid_coef = 0.1,
    To = 2.,  # weeks
    ec_coef = 0.7,
    Tec = 2.,  # hours
)

for coef, val in STARTING_PARAMS.items():
    STARTING_PARAMS[coef] = np.float32(val)

LOOP_NAMES = [
    corr_name
    for corr_name in dir(flux_correlation_functions)
    if corr_name.endswith("loop")
]
LOOP_FUNCTIONS = [
    getattr(flux_correlation_functions, corr_name)
    for corr_name in CORRELATION_FUNCTION_NAMES
]

NUMPY_NAMES = [
    corr_name
    for corr_name in dir(flux_correlation_functions)
    if corr_name.endswith("numpy")
]
NUMPY_FUNCTIONS = [
    getattr(flux_correlation_functions, corr_name)
    for corr_name in CORRELATION_FUNCTION_NAMES
]

NUMEXPR_NAMES = [
    corr_name
    for corr_name in dir(flux_correlation_functions)
    if corr_name.endswith("numexpr")
]
NUMEXPR_EXPRESSIONS = [
    getattr(flux_correlation_functions, corr_name)
    for corr_name in CORRELATION_FUNCTION_NAMES
]


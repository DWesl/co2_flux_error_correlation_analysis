#!/usr/bin/env python
# ~*~ coding: utf8 ~*~
"""Make plots to explain the correlation functions.

They will need to have only four or six days per year to be
understandable.
"""
import textwrap

import numpy as np
import numexpr as ne
import matplotlib.pyplot as plt
import seaborn as sns

import correlation_function_fits

############################################################
# Set up constants for plots

# For deomonstration purposes only
DAYS_PER_YEAR = 6
DAYS_PER_DAY = 1
EPS = 1e-13

GLOBAL_DICT = correlation_function_fits.GLOBAL_DICT.copy()
GLOBAL_DICT.update({
    "DAYS_PER_DAY": DAYS_PER_DAY,
    "PI_OVER_DAY": np.pi / DAYS_PER_DAY,
    "TWO_PI_OVER_DAY": 2 * np.pi / DAYS_PER_DAY,
    "FOUR_PI_OVER_DAY": 4 * np.pi / DAYS_PER_DAY,
    "DAYS_PER_YEAR": DAYS_PER_YEAR,
    "PI_OVER_YEAR": np.pi / DAYS_PER_YEAR,
    "TWO_PI_OVER_YEAR": 2 * np.pi / DAYS_PER_YEAR,
    "FOUR_PI_OVER_YEAR": 4 * np.pi / DAYS_PER_YEAR,
})

TIMES = np.linspace(0, DAYS_PER_YEAR, 601)
AX_HEIGHT = 5.5
AX_WIDTH = 6

LOCAL_DICT = {"tdata": TIMES}
for part in ("daily", "dm", "ann"):
    LOCAL_DICT.update({
        "{part:s}_coef".format(part=part): 1,
        "{part:s}_coef1".format(part=part): 0.5,
        "{part:s}_coef2".format(part=part): 0.25,
        "{part:s}_width".format(part=part): 0.4,
        # I'm ignoring this for now
        "{part:s}_timescale".format(part=part): 100,
    })

############################################################
# Set plotting defaults
sns.set_context("paper")
sns.set(style="whitegrid")
sns.set_palette("colorblind")

############################################################
# create plots

# Describe axes I'm using
fig, ax = plt.subplots(1, 1, figsize=(AX_WIDTH, AX_HEIGHT))
ax.set_xlabel("Lag Time (days)")
ax.set_xticks(np.arange(0, DAYS_PER_YEAR + EPS, 1))
ax.set_title("One year")

ax.set_xlim(0, DAYS_PER_YEAR)
ax.set_ylim(-1, 1)
ax.set_xticks(np.arange(0, DAYS_PER_YEAR + EPS, 3))
ax.set_xticks(np.arange(0, DAYS_PER_YEAR + EPS, 1), minor=True)

fig.tight_layout()
fig.savefig("demonstration-setup.pdf")
plt.close(fig)

# Describe the slots
fig, axes = plt.subplots(
    3, 2, figsize=(AX_WIDTH, AX_HEIGHT), sharex=True, sharey=True
)

axes[0, 0].plot(TIMES, np.cos(2 * np.pi * TIMES / DAYS_PER_DAY))
axes[0, 0].set_ylabel("Daily Cycle")
axes[0, 1].plot(TIMES, np.exp(-(np.sin(2 * np.pi * TIMES / DAYS_PER_DAY) / 0.5) ** 2))

axes[2, 0].plot(TIMES, np.cos(2 * np.pi * TIMES / DAYS_PER_YEAR))
axes[2, 0].set_ylabel("Annual Cycle")
axes[2, 1].plot(TIMES, np.exp(-(np.sin(np.pi * TIMES / DAYS_PER_YEAR) / 0.5) ** 2))

axes[1, 0].plot(
    TIMES,
    np.cos(2 * np.pi * TIMES / DAYS_PER_DAY) *
    (0.5 + 0.5 * np.cos(2 * np.pi * TIMES / DAYS_PER_YEAR))
)
axes[1, 0].set_ylabel("Modulation of\ndaily cycle")
axes[1, 1].plot(
    TIMES,
    np.cos(2 * np.pi * TIMES / DAYS_PER_DAY) *
    np.exp(-(np.sin(np.pi * TIMES / DAYS_PER_YEAR) / 0.5) ** 2)
)

axes[2, 0].set_xlim(0, DAYS_PER_YEAR)
axes[2, 0].set_ylim(-1, 1)
axes[2, 0].set_xticks(np.arange(0, DAYS_PER_YEAR + EPS, 3))
axes[2, 0].set_xticks(np.arange(0, DAYS_PER_YEAR + EPS, 1), minor=True)
axes[2, 0].set_xlabel("Lag Time (days)")
axes[2, 1].set_xlabel("Lag Time (days)")

fig.suptitle("Correlations in errors in:")
fig.subplots_adjust(left=.15, bottom=.15)
fig.savefig("demonstration-corr-fun-slots.pdf")
plt.close(fig)

fig, axes = plt.subplots(
    len(correlation_function_fits.PartForm),
    len(correlation_function_fits.CorrelationPart),
    figsize=(AX_WIDTH, AX_HEIGHT),
    sharex=True, sharey=True,
)

for axes_row, part_form in zip(
        axes,
        sorted(
            correlation_function_fits.PartForm,
            key=lambda part_form: len(
                part_form.get_parameters(
                    correlation_function_fits.CorrelationPart.DAILY
                )
            )
        )
):
    for ax, func_part in zip(
            axes_row, correlation_function_fits.CorrelationPart
    ):
        if func_part.is_modulation():
            expression = part_form.get_expression(func_part)
            expression += " * cos(TWO_PI_OVER_DAY * tdata)"
        else:
            expression = part_form.get_expression(func_part)
        ax.plot(
            *np.broadcast_arrays(
                TIMES,
                ne.evaluate(
                    expression,
                    global_dict=GLOBAL_DICT,
                    local_dict=LOCAL_DICT,
                ),
            )
        )
        ax.set_ylim(-1, 1)
        ax.set_xlim(0, DAYS_PER_YEAR)
        ax.set_xticks(np.arange(0, DAYS_PER_YEAR + EPS, 3))
        ax.set_xticks(np.arange(0, DAYS_PER_YEAR + EPS, 1), minor=True)

for ax, part_form in zip(axes[:, 0], correlation_function_fits.PartForm):
    ax.set_ylabel(textwrap.fill(part_form.value, 14))

for ax, func_part in zip(
        axes[0, :],
        ("Daily Cycle", "Modulation\nof Daily Cycle", "Annual Cycle")
):
    ax.set_title(func_part)

for ax in axes[-1, :]:
    ax.set_xlabel("Time Lag (days)")

fig.savefig("demonstration-corr-fun-slots-and-forms.pdf")
fig.savefig("demonstration-corr-fun-slots-and-forms.png")
plt.close(fig)

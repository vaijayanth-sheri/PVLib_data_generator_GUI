from __future__ import annotations
import re
import math
import pandas as pd

# canonical names & units
CANON = {
    "ghi": "W/m^2",
    "dni": "W/m^2",
    "dhi": "W/m^2",
    "temp_air": "C",
    "wind_speed": "m/s",
    "pressure": "Pa",
    "albedo": "-",
}

FUZZY = {
    "ghi": ["ghi", "global", "globalhor", "i_gh", "allsky_sfc_sw_dwn", "g"],
    "dni": ["dni", "direct", "beam", "allsky_sfc_sw_dni"],
    "dhi": ["dhi", "diffuse", "allsky_sfc_sw_diff"],
    "temp_air": ["temp", "t2m", "ta", "temp_air", "temperature"],
    "wind_speed": ["wind", "ws2m", "wspd", "wind_speed"],
    "pressure": ["pressure", "press", "ps", "pres", "sp"],
    "albedo": ["albedo", "rho"],
}

def guess_column(name: str) -> str | None:
    n = re.sub(r"[^a-z0-9]", "", name.lower())
    for canonical, candidates in FUZZY.items():
        if any(n.startswith(c) or c in n for c in candidates):
            return canonical
    return None

def infer_units(series_name: str, series: pd.Series, freq_seconds: int | None = None) -> str | None:
    sname = series_name.lower()
    v = series.dropna().astype(float)
    if v.empty:
        return None
    mean = v.iloc[: min(500, len(v))].mean()
    if series_name in ["pressure", "ps", "pres", "sp"]:
        # if ~100 -> kPa, if ~1000 -> hPa, if ~100000 -> Pa
        if 70 < mean < 110:
            return "kPa"
        if 700 < mean < 1100:
            return "hPa"
        return "Pa"
    if series_name in ["ghi", "dni", "dhi", "global", "direct", "diffuse"]:
        # detect energy units kWh/m2 per interval
        # if values are mostly < 2, likely kWh/m2; if < 1400 typical W/m2
        if mean < 5 and freq_seconds:
            return "kWh/m^2"
        return "W/m^2"
    return None

def energy_to_power_kwhm2_to_wm2(s: pd.Series, freq_seconds: int) -> pd.Series:
    # average power over the interval: W/m^2 = (kWh/m^2) * 1000 * (3600 / seconds)
    factor = 1000 * (3600 / freq_seconds)
    return s.astype(float) * factor

def convert_to_canonical(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    # detect freq
    if isinstance(df.index, pd.DatetimeIndex) and df.index.freqstr:
        freq_seconds = int(pd.to_timedelta(df.index.freq).total_seconds())
    else:
        # fallback by median diff
        diffs = df.index.to_series().diff().dropna().dt.total_seconds()
        freq_seconds = int(diffs.median()) if not diffs.empty else 3600

    conversions = {}
    # pressure
    for col in list(df.columns):
        low = col.lower()
        if low in ["pressure", "ps", "pres", "sp"]:
            units = infer_units("pressure", df[col])
            if units == "kPa":
                df[col] = df[col].astype(float) * 1000.0
                conversions[col] = ("kPa", "Pa")
            elif units == "hPa":
                df[col] = df[col].astype(float) * 100.0
                conversions[col] = ("hPa", "Pa")
            else:
                conversions[col] = ("Pa", "Pa")

    # irradiance possibly in kWh/m2
    for q in ["ghi", "dni", "dhi"]:
        for col in list(df.columns):
            if guess_column(col) == q:
                units = infer_units(q, df[col], freq_seconds=freq_seconds)
                if units == "kWh/m^2":
                    df[col] = energy_to_power_kwhm2_to_wm2(df[col], freq_seconds)
                    conversions[col] = ("kWh/m^2", "W/m^2")
                elif units == "W/m^2":
                    conversions[col] = ("W/m^2", "W/m^2")

    # rename to canonical where possible
    rename = {}
    for col in df.columns:
        g = guess_column(col)
        if g and g not in df.columns:
            rename[col] = g
    df = df.rename(columns=rename)
    return df, conversions

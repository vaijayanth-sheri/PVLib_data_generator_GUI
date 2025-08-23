from __future__ import annotations
import pandas as pd
from zoneinfo import ZoneInfo
from timezonefinder import TimezoneFinder

_tf = TimezoneFinder(in_memory=True)

def tz_name_from_latlon(lat: float, lon: float) -> str:
    tz = _tf.timezone_at(lat=lat, lng=lon) or _tf.certain_timezone_at(lat=lat, lng=lon)
    return tz or "UTC"

def localize_index(idx: pd.DatetimeIndex, tz_name: str) -> pd.DatetimeIndex:
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return idx.tz_convert(ZoneInfo(tz_name))

def ensure_tz_aware(df: pd.DataFrame, tz_name: str) -> pd.DataFrame:
    df = df.copy()
    df.index = localize_index(df.index, tz_name)
    return df

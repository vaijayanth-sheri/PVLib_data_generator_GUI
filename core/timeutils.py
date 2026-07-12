from __future__ import annotations
import pandas as pd
import requests

def tz_name_from_latlon(lat: float, lon: float) -> str:
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&timezone=auto&current_weather=true"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json().get("timezone", "UTC")
    except Exception:
        pass
    return "UTC"

def localize_index(idx: pd.DatetimeIndex, tz_name: str) -> pd.DatetimeIndex:
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return idx.tz_convert(tz_name)

def ensure_tz_aware(df: pd.DataFrame, tz_name: str) -> pd.DataFrame:
    df = df.copy()
    df.index = localize_index(df.index, tz_name)
    return df

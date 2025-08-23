from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
import requests
from meteostat import Point, Hourly
from pvlib import iotools
from .timeutils import ensure_tz_aware
from .cache import get_cached_df, set_cached_df
from .mapping import convert_to_canonical

@dataclass
class SourceMeta:
    name: str
    details: dict
    conversions: dict
    derived: dict

def _normalize_pvgis(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={
        "G(h)": "ghi", "Gb(n)": "dni", "Gd(h)": "dhi",
        "T2m": "temp_air", "WS10m": "wind_speed", "SP": "pressure",
    })

def fetch_pvgis_hourly(lat, lon, year, tz_name):
    key = {"src":"pvgis", "lat":lat, "lon":lon, "year":year}
    cached = get_cached_df("pvgis", key)
    if cached is not None:
        df, conv = convert_to_canonical(cached)
        return df, SourceMeta("PVGIS", {"year": year}, conv, {"dni":"measured","dhi":"measured"})
    data, meta = iotools.get_pvgis_hourly(latitude=lat, longitude=lon,
                                          start=year, end=year, components=True)
    df = _normalize_pvgis(data)
    df.index = pd.to_datetime(df.index, utc=True)
    df = ensure_tz_aware(df, tz_name)
    df, conv = convert_to_canonical(df)
    set_cached_df("pvgis", key, df)
    return df, SourceMeta("PVGIS", {"meta":meta}, conv, {"dni":"measured","dhi":"measured"})

def fetch_pvgis_tmy(lat, lon, tz_name):
    data, meta = iotools.get_pvgis_tmy(lat, lon, map_variables=True, usehorizon=True)
    df = data.rename(columns={"G(h)":"ghi","Gb(n)":"dni","Gd(h)":"dhi",
                              "T2m":"temp_air","WS10m":"wind_speed","SP":"pressure"})
    df.index = pd.to_datetime(df.index, utc=True)
    df = ensure_tz_aware(df, tz_name)
    df, conv = convert_to_canonical(df)
    return df, SourceMeta("PVGIS TMY", {"meta":meta}, conv, {"dni":"measured","dhi":"measured"})

def fetch_nasa_power_hourly(lat, lon, start, end, tz_name):
    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")
    params = ",".join(["ALLSKY_SFC_SW_DWN", "T2M", "WS2M", "PS"])
    url = (
        "https://power.larc.nasa.gov/api/temporal/hourly/point?"
        f"parameters={params}&community=RE&longitude={lon:.5f}&latitude={lat:.5f}"
        f"&start={start_s}&end={end_s}&format=JSON&time-standard=UTC"
    )
    key = {"src":"nasa_power", "lat":lat, "lon":lon, "start":start_s, "end":end_s}
    cached = get_cached_df("nasa", key)
    if cached is not None:
        df, conv = convert_to_canonical(cached)
        return df, SourceMeta("NASA POWER Hourly", {"url": url}, conv, {"dni":"derived","dhi":"derived"})
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    js = r.json()
    base = js["properties"]["parameter"]

    def series_for(k):
        data = base.get(k, {})
        if not data:
            return pd.Series(dtype=float)
        s = pd.Series(data).sort_index()
        idx = pd.to_datetime(s.index, format="%Y%m%d%H", utc=True)
        s.index = idx
        return s.astype(float)

    df = pd.DataFrame({
        "ghi": series_for("ALLSKY_SFC_SW_DWN"),
        "temp_air": series_for("T2M"),
        "wind_speed": series_for("WS2M"),
        "pressure": series_for("PS"),
    }).dropna(how="all")
    df, conv = convert_to_canonical(df)
    df = ensure_tz_aware(df, tz_name)
    set_cached_df("nasa", key, df)
    return df, SourceMeta("NASA POWER Hourly", {"url": url}, conv, {"dni":"derived","dhi":"derived"})

def fetch_meteostat_patch(lat, lon, start, end, tz_name):
    loc = Point(lat, lon)
    data = Hourly(loc, start, end).fetch()
    ren = {"temp":"temp_air", "wspd":"wind_speed", "pres":"pressure"}
    df = data.rename(columns=ren)[["temp_air","wind_speed","pressure"]].dropna(how="all")
    df.index = pd.to_datetime(df.index, utc=True)
    df = ensure_tz_aware(df, tz_name)
    df, _ = convert_to_canonical(df)
    return df

def read_epw(file: Path, tz_name: str):
    data, meta = iotools.read_epw(str(file))
    df = data.rename(columns={
        "ghi":"ghi","dni":"dni","dhi":"dhi",
        "temp_air":"temp_air","wind_speed":"wind_speed","atmospheric_pressure":"pressure"
    })
    df.index = pd.to_datetime(df.index, utc=True)
    df = ensure_tz_aware(df, tz_name)
    df, conv = convert_to_canonical(df)
    return df, SourceMeta("EPW Upload", {"original_name": file.name, "epw_meta": meta}, conv, {"dni":"measured","dhi":"measured"})

def read_csv(file: Path, tz_name: str):
    df = pd.read_csv(file)
    dtcol = None
    for c in df.columns:
        if "time" in c.lower() or "date" in c.lower():
            dtcol = c
            break
    if dtcol is None:
        raise ValueError("Upload CSV must include a datetime/time column")
    df[dtcol] = pd.to_datetime(df[dtcol], utc=True, errors="coerce")
    df = df.set_index(dtcol).sort_index()
    df, conv = convert_to_canonical(df)
    df = ensure_tz_aware(df, tz_name)
    return df, SourceMeta("CSV Upload", {"original_name": file.name}, conv, {"dni":"unknown","dhi":"unknown"})

from __future__ import annotations
import pandas as pd
from pvlib import irradiance, solarposition, location

def derive_from_ghi(df: pd.DataFrame, lat: float, lon: float, tz_name: str) -> tuple[pd.DataFrame, dict]:
    out = df.copy()
    derived = {}
    # need solar position
    times = out.index
    sp = solarposition.get_solarposition(times, lat, lon)
    zen = sp["zenith"]
    if "dni" not in out or out["dni"].isna().all():
        dni = irradiance.dirint(out["ghi"].fillna(0), zen, times)  # DIRINT for DNI :contentReference[oaicite:11]{index=11}
        out["dni"] = dni
        derived["dni"] = "dirint"
    if "dhi" not in out or out["dhi"].isna().all():
        # ERBS uses GHI + zenith to split diffuse/beam  :contentReference[oaicite:12]{index=12}
        er = irradiance.erbs(out["ghi"].fillna(0), zen, times)
        out["dhi"] = er["dhi"]
        derived["dhi"] = "erbs"
    return out, derived

def to_poa(df: pd.DataFrame, surface_tilt: float, surface_azimuth: float, lat: float, lon: float) -> pd.DataFrame:
    times = df.index
    solpos = solarposition.get_solarposition(times, lat, lon)
    poa = irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        solar_zenith=solpos["zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=df["dni"], ghi=df["ghi"], dhi=df["dhi"],
        model="perez"  # default per spec; can swap to "haydavies"  :contentReference[oaicite:13]{index=13}
    )
    return poa

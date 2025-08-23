# core/model.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from pvlib import modelchain, pvsystem, location
from .irradiance import to_poa


@dataclass
class SystemConfig:
    # geometry / layout
    layout: str = "fixed_tilt"
    tilt_deg: float = 30.0
    azimuth_deg: float = 180.0
    # sizing
    dc_kwp: float = 1.0
    ac_kw: float | None = None
    ac_dc_ratio: float | None = None
    # losses & irradiance model
    losses_pct: float = 14.0
    transposition: str = "perez"          # "perez" or "haydavies"
    albedo: float = 0.2


def _losses_dict(pct: float) -> dict:
    """
    PVWatts-style lumped losses. We provide a plausible breakdown that sums to ~pct.
    """
    base = {
        "soiling": 2.0,
        "shading": 0.0,
        "snow": 0.0,
        "mismatch": 2.0,
        "wiring": 2.0,
        "connections": 0.5,
        "lid": 1.5,
        "nameplate_rating": 1.0,
        "age": 0.0,
        "availability": max(0.0, pct - 9.0),
    }
    return base


def run_pvwatts(weather: pd.DataFrame, lat: float, lon: float, tz_name: str, cfg: SystemConfig):
    """
    Run a PVWatts-based ModelChain with explicit models set (no inference).
    Temperature model is fixed to Faiman with consistent parameters.
    """
    required = ["ghi", "dni", "dhi", "temp_air", "wind_speed"]
    missing = [c for c in required if c not in weather.columns]
    if missing:
        raise ValueError(f"Weather is missing required columns: {missing}")

    dc_w = float(cfg.dc_kwp) * 1000.0
    if cfg.ac_kw is not None:
        ac_w_nameplate = float(cfg.ac_kw) * 1000.0
    elif cfg.ac_dc_ratio is not None:
        ac_w_nameplate = dc_w * float(cfg.ac_dc_ratio)
    else:
        ac_w_nameplate = dc_w * 0.9

    module_params = dict(pdc0=dc_w, gamma_pdc=-0.003)
    inverter_params = dict(pdc0=ac_w_nameplate)

    # Fixed temperature model: Faiman (robust default)
    temp_params = {"u0": 25.0, "u1": 6.84}

    system = pvsystem.PVSystem(
        surface_tilt=cfg.tilt_deg,
        surface_azimuth=cfg.azimuth_deg,
        module_parameters=module_params,
        inverter_parameters=inverter_params,
        losses_parameters=_losses_dict(cfg.losses_pct),
        temperature_model_parameters=temp_params,
        albedo=cfg.albedo,
        racking_model="open_rack",
        module_type="glass_polymer",
    )

    loc = location.Location(latitude=lat, longitude=lon, tz=tz_name)

    mc = modelchain.ModelChain(
        system=system,
        location=loc,
        dc_model="pvwatts",
        ac_model="pvwatts",
        spectral_model=None,
        aoi_model="physical",
        airmass_model="kastenyoung1989",
        transposition_model=cfg.transposition,   # "perez" or "haydavies"
        temperature_model="faiman",              # fixed to Faiman
        losses_model="pvwatts",
    )

    mc.run_model(weather)

    ac_w = mc.results.ac.astype(float).fillna(0.0)
    if hasattr(mc.results, "total_irrad") and "poa_global" in mc.results.total_irrad:
        poa = mc.results.total_irrad["poa_global"].astype(float).fillna(0.0)
    else:
        poa = to_poa(weather, cfg.tilt_deg, cfg.azimuth_deg, lat, lon)["poa_global"].astype(float).fillna(0.0)

    hourly_kwh = ac_w / 1000.0
    annual_kwh = float(hourly_kwh.sum())
    poa_kwhm2 = float(poa.sum() / 1000.0)

    # PR = E_ac / (P_stc * H_poa / 1000)
    pr = float(annual_kwh / (cfg.dc_kwp * (poa_kwhm2 / 1.0))) if poa_kwhm2 > 0 else np.nan
    pr = round(pr, 3) if np.isfinite(pr) else None

    hours = len(weather.index)
    ac_capacity_kw = ac_w_nameplate / 1000.0
    cf = float(annual_kwh / (ac_capacity_kw * hours)) if (hours and ac_capacity_kw > 0) else np.nan
    cf = round(cf, 3) if np.isfinite(cf) else None

    monthly = hourly_kwh.resample("MS").sum().round(2)

    kpis = {
        "annual_kwh": round(annual_kwh, 2),
        "performance_ratio": pr,
        "capacity_factor": cf,
        "monthly_kwh": {str(k.date()): float(v) for k, v in monthly.items()},
    }

    return ac_w, poa, kpis, mc

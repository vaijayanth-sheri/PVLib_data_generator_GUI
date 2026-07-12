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
    tilt_deg: float = 35.0
    azimuth_deg: float = 180.0
    # sizing
    dc_kwp: float = 10.0
    ac_kw: float | None = None
    ac_dc_ratio: float | None = 0.9
    # losses & irradiance model
    losses_pct: float = 14.0
    transposition: str = "perez"          # "perez" or "haydavies"
    albedo: float = 0.2
    
    # Expert Mode Sizing
    expert_mode: bool = False
    module_name: str | None = None
    inverter_name: str | None = None
    modules_per_string: int = 14
    strings_per_inverter: int = 2
    custom_module_params: dict | None = None  # { pdc0: float, gamma_pdc: float }


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

    loc = location.Location(latitude=lat, longitude=lon, tz=tz_name)
    temp_params = {"u0": 25.0, "u1": 6.84} # Fixed Faiman model
    
    if cfg.expert_mode:
        # Load Sandia inverter database
        sandia_inverters = pvsystem.retrieve_sam('cecinverter')
        if cfg.inverter_name not in sandia_inverters:
            raise ValueError(f"Inverter {cfg.inverter_name} not found.")
        inverter_params = sandia_inverters[cfg.inverter_name]
        ac_w_nameplate = float(inverter_params.get('Paco', 5000.0))
        
        if cfg.custom_module_params:
            # Custom Module (Use PVWatts DC model for simplicity of params)
            module_power_w = float(cfg.custom_module_params.get("pdc0", 300))
            gamma_pdc = float(cfg.custom_module_params.get("gamma_pdc", -0.003))
            
            total_modules = cfg.modules_per_string * cfg.strings_per_inverter
            dc_w = module_power_w * total_modules
            cfg.dc_kwp = dc_w / 1000.0  # Update for KPI reporting
            
            system = pvsystem.PVSystem(
                surface_tilt=cfg.tilt_deg,
                surface_azimuth=cfg.azimuth_deg,
                module_parameters=dict(pdc0=dc_w, gamma_pdc=gamma_pdc),
                inverter_parameters=inverter_params,
                losses_parameters=_losses_dict(cfg.losses_pct),
                temperature_model_parameters=temp_params,
                albedo=cfg.albedo,
                racking_model="open_rack",
                module_type="glass_polymer",
            )
            
            mc = modelchain.ModelChain(
                system=system,
                location=loc,
                dc_model="pvwatts",
                ac_model="sandia",
                spectral_model=None,
                aoi_model="physical",
                airmass_model="kastenyoung1989",
                transposition_model=cfg.transposition,
                temperature_model="faiman",
                losses_model="pvwatts"
            )
        else:
            # DB Module (CEC DC model)
            cec_modules = pvsystem.retrieve_sam('cecmod')
            if cfg.module_name not in cec_modules:
                raise ValueError(f"Module {cfg.module_name} not found.")
            module_params = cec_modules[cfg.module_name]
            
            # STC power is V_mp_ref * I_mp_ref in CEC model
            module_power_w = module_params.get('STC', module_params.get('V_mp_ref', 0) * module_params.get('I_mp_ref', 0))
            if module_power_w <= 0: module_power_w = 300
            
            total_modules = cfg.modules_per_string * cfg.strings_per_inverter
            dc_w = module_power_w * total_modules
            cfg.dc_kwp = dc_w / 1000.0 # Update for KPI reporting
            
            system = pvsystem.PVSystem(
                surface_tilt=cfg.tilt_deg,
                surface_azimuth=cfg.azimuth_deg,
                module_parameters=module_params,
                inverter_parameters=inverter_params,
                losses_parameters=_losses_dict(cfg.losses_pct),
                temperature_model_parameters=temp_params,
                albedo=cfg.albedo,
                racking_model="open_rack",
                strings_per_inverter=cfg.strings_per_inverter,
                modules_per_string=cfg.modules_per_string,
            )
            
            mc = modelchain.ModelChain(
                system=system,
                location=loc,
                dc_model="cec",
                ac_model="sandia",
                spectral_model=None,
                aoi_model="physical",
                airmass_model="kastenyoung1989",
                transposition_model=cfg.transposition,
                temperature_model="faiman",
                losses_model="pvwatts"
            )
    else:
        # Basic PVWatts setup
        dc_w = float(cfg.dc_kwp) * 1000.0
        if cfg.ac_kw is not None:
            ac_w_nameplate = float(cfg.ac_kw) * 1000.0
        elif cfg.ac_dc_ratio is not None:
            ac_w_nameplate = dc_w * float(cfg.ac_dc_ratio)
        else:
            ac_w_nameplate = dc_w * 0.9

        system = pvsystem.PVSystem(
            surface_tilt=cfg.tilt_deg,
            surface_azimuth=cfg.azimuth_deg,
            module_parameters=dict(pdc0=dc_w, gamma_pdc=-0.003),
            inverter_parameters=dict(pdc0=ac_w_nameplate),
            losses_parameters=_losses_dict(cfg.losses_pct),
            temperature_model_parameters=temp_params,
            albedo=cfg.albedo,
            racking_model="open_rack",
            module_type="glass_polymer",
        )

        mc = modelchain.ModelChain(
            system=system,
            location=loc,
            dc_model="pvwatts",
            ac_model="pvwatts",
            spectral_model=None,
            aoi_model="physical",
            airmass_model="kastenyoung1989",
            transposition_model=cfg.transposition,
            temperature_model="faiman",
            losses_model="pvwatts",
        )

    mc.run_model(weather)

    ac_w = mc.results.ac.astype(float).fillna(0.0)
    if hasattr(mc.results, "total_irrad") and "poa_global" in mc.results.total_irrad:
        poa = mc.results.total_irrad["poa_global"].astype(float).fillna(0.0)
    else:
        poa = to_poa(weather, cfg.tilt_deg, cfg.azimuth_deg, lat, lon)["poa_global"].astype(float).fillna(0.0)

    if isinstance(mc.results.dc, pd.DataFrame) and 'p_mp' in mc.results.dc:
        dc_w = mc.results.dc['p_mp'].astype(float).fillna(0.0)
    elif isinstance(mc.results.dc, pd.DataFrame):
        dc_w = mc.results.dc.iloc[:, 0].astype(float).fillna(0.0)
    else:
        dc_w = mc.results.dc.astype(float).fillna(0.0)

    hourly_kwh = ac_w / 1000.0
    annual_kwh = float(hourly_kwh.sum())
    annual_dc_kwh = float(dc_w.sum() / 1000.0)
    poa_kwhm2 = float(poa.sum() / 1000.0)

    # PR = E_ac / (P_stc * H_poa / 1000)
    pr = float(annual_kwh / (cfg.dc_kwp * (poa_kwhm2 / 1.0))) if poa_kwhm2 > 0 else np.nan
    pr = round(pr, 3) if np.isfinite(pr) else None

    hours = len(weather.index)
    ac_capacity_kw = ac_w_nameplate / 1000.0
    cf = float(annual_kwh / (ac_capacity_kw * hours)) if (hours and ac_capacity_kw > 0) else np.nan
    cf = round(cf, 3) if np.isfinite(cf) else None
    
    specific_yield = float(annual_kwh / cfg.dc_kwp) if cfg.dc_kwp > 0 else 0.0

    kpis = {
        "annual_kwh": round(annual_kwh, 2),
        "annual_dc_kwh": round(annual_dc_kwh, 2),
        "performance_ratio": pr,
        "capacity_factor": cf,
        "specific_yield": round(specific_yield, 2),
        "poa_kwhm2": round(poa_kwhm2, 2)
    }

    return ac_w, dc_w, poa, kpis, mc

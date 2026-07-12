from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import io
import json
import tempfile
import pandas as pd
from geopy.geocoders import Nominatim
from datetime import datetime
from pvlib import pvsystem

import sys
from pathlib import Path
# Add project root to path so we can import core and app
sys.path.append(str(Path(__file__).parent.parent))

from core.timeutils import tz_name_from_latlon, ensure_tz_aware
from core.adapters import fetch_pvgis_hourly, fetch_pvgis_tmy, fetch_nasa_power_hourly, read_epw
from core.mapping import convert_to_canonical
from core.model import SystemConfig, run_pvwatts
from core.irradiance import derive_from_ghi


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LocationQuery(BaseModel):
    query: str

PVGIS_HOURLY_MIN_YEAR = 2005
PVGIS_HOURLY_MAX_YEAR = 2023

@app.post("/api/location/search")
def search_location(body: LocationQuery):
    geocoder = Nominatim(user_agent="pvlib_gui")
    loc = geocoder.geocode(body.query, timeout=10)
    if loc:
        tz_name = tz_name_from_latlon(loc.latitude, loc.longitude)
        return {
            "lat": loc.latitude,
            "lon": loc.longitude,
            "address": loc.address,
            "timezone": tz_name
        }
    raise HTTPException(status_code=404, detail="Location not found")

class FetchQuery(BaseModel):
    source: str
    lat: float
    lon: float
    year: Optional[int] = None
    tz_name: str

@app.post("/api/weather/fetch")
def fetch_weather(body: FetchQuery):
    try:
        df = None
        meta = None
        if body.source == "PVGIS Hourly":
            if not body.year:
                raise HTTPException(status_code=400, detail="Year required for PVGIS Hourly")
            if body.year < PVGIS_HOURLY_MIN_YEAR or body.year > PVGIS_HOURLY_MAX_YEAR:
                raise HTTPException(
                    status_code=400,
                    detail=f"PVGIS Hourly supports years {PVGIS_HOURLY_MIN_YEAR}–{PVGIS_HOURLY_MAX_YEAR}. "
                           f"Year {body.year} is out of range. Use PVGIS TMY or NASA POWER instead."
                )
            df, meta = fetch_pvgis_hourly(body.lat, body.lon, body.year, body.tz_name)
        elif body.source == "PVGIS TMY":
            df, meta = fetch_pvgis_tmy(body.lat, body.lon, body.tz_name)
        elif body.source == "NASA POWER":
            if not body.year:
                raise HTTPException(status_code=400, detail="Year required for NASA POWER")
            start = pd.Timestamp(f"{body.year}-01-01", tz="UTC")
            end   = pd.Timestamp(f"{body.year}-12-31 23:00:00", tz="UTC")
            df, meta = fetch_nasa_power_hourly(body.lat, body.lon, start, end, body.tz_name)
        else:
            raise HTTPException(status_code=400, detail="Invalid source")
            
        # Reset index to keep the datetime column
        df_reset = df.reset_index()
        # Ensure we know the name of the time column, usually it's 'time' or 'index'
        time_col = df.index.name if df.index.name else "time"
        if not df.index.name:
            df_reset.rename(columns={"index": "time"}, inplace=True)
            
        df_json = json.loads(df_reset.to_json(orient="records", date_format="iso"))
        meta_dict = meta if isinstance(meta, dict) else meta.__dict__
        
        return {"weather": df_json, "meta": meta_dict, "time_col": time_col}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/weather/upload")
def upload_weather(file: UploadFile = File(...), tz_name: str = Form(...)):
    try:
        # Save to tempfile since read_epw expects a file path
        with tempfile.NamedTemporaryFile(delete=False, suffix=".epw") as tmp:
            tmp.write(file.file.read())
            tmp_path = Path(tmp.name)
            
        df, meta = read_epw(tmp_path, tz_name)
        
        # Clean up
        tmp_path.unlink()
        
        # Format response
        df_reset = df.reset_index()
        time_col = df.index.name if df.index.name else "time"
        if not df.index.name:
            df_reset.rename(columns={"index": "time"}, inplace=True)
            
        df_json = json.loads(df_reset.to_json(orient="records", date_format="iso"))
        meta_dict = meta if isinstance(meta, dict) else meta.__dict__
        
        return {"weather": df_json, "meta": meta_dict, "time_col": time_col}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/components")
def get_components(type: str = 'module', provider: str = None):
    try:
        # Load the databases
        db = pvsystem.retrieve_sam('cecmod') if type == 'module' else pvsystem.retrieve_sam('cecinverter')
        
        def extract_provider(name):
            if '__' in name: return name.split('__')[0]
            if '_' in name: return name.split('_')[0]
            return "Other"
            
        all_items = list(db.columns)
        
        if not provider:
            # Return list of unique providers
            providers = sorted(list(set([extract_provider(i) for i in all_items])))
            return {"providers": providers}
        else:
            # Return items matching the provider
            filtered_items = [i for i in all_items if extract_provider(i) == provider]
            return {"items": filtered_items}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SimulateQuery(BaseModel):
    weather: list
    time_col: str
    lat: float
    lon: float
    tz_name: str
    syscfg: dict

@app.post("/api/simulate")
def simulate(body: SimulateQuery):
    try:
        df = pd.DataFrame.from_records(body.weather)
        df[body.time_col] = pd.to_datetime(df[body.time_col])
        df.set_index(body.time_col, inplace=True)
        
        # Ensure required met columns exist
        if "temp_air" not in df.columns:
            df["temp_air"] = 20.0
        else:
            df["temp_air"] = df["temp_air"].fillna(20.0)
        if "wind_speed" not in df.columns:
            df["wind_speed"] = 1.0
        else:
            df["wind_speed"] = df["wind_speed"].fillna(1.0)
            
        # Derive DNI/DHI if missing
        need_dni = ("dni" not in df.columns) or df["dni"].isna().all()
        need_dhi = ("dhi" not in df.columns) or df["dhi"].isna().all()
        deriv = {}
        if need_dni or need_dhi:
            df, deriv = derive_from_ghi(df, body.lat, body.lon, body.tz_name)
            
        cfg = SystemConfig(**body.syscfg)
        ac_w, dc_w, poa, kpis, mc = run_pvwatts(df, body.lat, body.lon, body.tz_name, cfg)
        
        # Combine to a single dataframe
        res_df = pd.DataFrame({"ac_w": ac_w, "dc_w": dc_w, "poa_w": poa})
        
        # Hourly array
        hourly = res_df.reset_index()
        hourly.rename(columns={hourly.columns[0]: "time"}, inplace=True)
        # W to kWh (for 1-hour intervals, power in kW equals energy in kWh)
        hourly['ac_kwh'] = hourly['ac_w'] / 1000.0
        hourly['dc_kwh'] = hourly['dc_w'] / 1000.0
        hourly['poa_kwhm2'] = hourly['poa_w'] / 1000.0
        
        # Daily array (convert W to kWh)
        daily_df = res_df.resample('D').sum() / 1000.0
        daily_df.rename(columns={"ac_w": "ac_kwh", "dc_w": "dc_kwh", "poa_w": "poa_kwhm2"}, inplace=True)
        daily = daily_df.reset_index()
        daily.rename(columns={daily.columns[0]: "time"}, inplace=True)
        
        # Monthly array (convert W to kWh)
        monthly_df = res_df.resample('MS').sum() / 1000.0
        monthly_df.rename(columns={"ac_w": "ac_kwh", "dc_w": "dc_kwh", "poa_w": "poa_kwhm2"}, inplace=True)
        monthly = monthly_df.reset_index()
        monthly.rename(columns={monthly.columns[0]: "time"}, inplace=True)
        
        # Make sure kpis has what frontend expects
        kpis["annual_energy"] = kpis["annual_kwh"]
            
        return {
            "series": {
                "hourly": json.loads(hourly.to_json(orient="records", date_format="iso")),
                "daily": json.loads(daily.to_json(orient="records", date_format="iso")),
                "monthly": json.loads(monthly.to_json(orient="records", date_format="iso"))
            },
            "kpis": kpis,
            "derived_methods": deriv
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

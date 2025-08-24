from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json, io, zipfile
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from geopy.geocoders import Nominatim

from core.timeutils import tz_name_from_latlon, ensure_tz_aware
from core.adapters import (fetch_pvgis_hourly, fetch_pvgis_tmy,
                           fetch_nasa_power_hourly, read_epw)
from core.mapping import convert_to_canonical
from core.model import SystemConfig, run_pvwatts
from core.cache import export_dir
from core.irradiance import derive_from_ghi
from app.report import write_pdf, _fig_to_png_bytes

TOOL_NAME = "PVLib_data_generator_GUI"

# PVGIS hourly historical bounds (per API)
PVGIS_HOURLY_MIN_YEAR = 2005
PVGIS_HOURLY_MAX_YEAR = 2023

st.set_page_config(page_title=TOOL_NAME, layout="wide")

# --- initialize defaults
st.session_state.setdefault("step", 1)
st.session_state.setdefault("year", datetime.utcnow().year - 1)

# --- sidebar navigation
with st.sidebar:
    st.title("Navigation")
    choice = st.radio("Go to:", [
        "Step 1: Site, Period & Source",
        "Step 2: System",
        "Step 3: Run Model",
        "Step 4: Export",
        "Step 5: About"
    ], index=st.session_state["step"]-1)

    step_map = {
        "Step 1: Site, Period & Source": 1,
        "Step 2: System": 2,
        "Step 3: Run Model": 3,
        "Step 4: Export": 4,
        "Step 5: About": 5
    }
    st.session_state["step"] = step_map[choice]

def next_step():
    st.session_state["step"] = min(st.session_state["step"] + 1, 5)
    st.experimental_rerun()  # hard rerender to clear previous widgets

def prev_step():
    st.session_state["step"] = max(st.session_state["step"] - 1, 1)
    st.experimental_rerun()


# ---------- Step 1: Site, Period & Source (merged) ----------
if st.session_state["step"] == 1:
    st.header("Step 1 — Site, Period & Data Source")

    # Location
    colA, colB = st.columns([2,1])
    with colA:
        mode = st.radio("Location input", ["Search address","Lat/Lon"], key="site_mode")
        if mode == "Search address":
            q = st.text_input("Search", value=st.session_state.get("last_query","Berlin, Germany"))
            if st.button("Lookup"):
                geocoder = Nominatim(user_agent="pvlib_gui")
                loc = geocoder.geocode(q, timeout=10)
                if loc:
                    st.session_state["latlon"] = (loc.latitude, loc.longitude, loc.address)
                    st.session_state["last_query"] = q
                else:
                    st.warning("Address not found. Try a broader query or use Lat/Lon.")
        else:
            lat = st.number_input("Latitude", value=52.52, format="%.6f")
            lon = st.number_input("Longitude", value=13.405, format="%.6f")
            st.session_state["latlon"] = (lat, lon, f"{lat:.4f},{lon:.4f}")
    with colB:
        lat, lon, addr = st.session_state.get("latlon",(52.52,13.405,"Berlin, Germany"))
        tz_name = tz_name_from_latlon(lat, lon)
        st.success(f"📍 {addr}\n\n🕒 Timezone: {tz_name}")

    # Period
    st.divider()
    pmode = st.radio("Period", ["Calendar Year","TMY"], key="period_mode", horizontal=True)
    if pmode == "Calendar Year":
        # Only let the widget manage 'year'
        st.number_input("Year", PVGIS_HOURLY_MIN_YEAR, 2100, value=st.session_state["year"], key="year")
        st.caption(f"PVGIS Hourly supports {PVGIS_HOURLY_MIN_YEAR}–{PVGIS_HOURLY_MAX_YEAR}. "
                   f"For other years, use NASA POWER or TMY.")

    # Data source + notes
    st.divider()
    st.subheader("Data Source")
    ds = st.radio(
        "Choose a source",
        ["PVGIS Hourly", "PVGIS TMY", "NASA POWER", "Upload (CSV/EPW)"],
        key="ds_mode",
        horizontal=True
    )
    if ds == "PVGIS Hourly":
        st.info("PVGIS Hourly — strong coverage/accuracy in Europe; includes DNI/DHI & met; years "
                f"{PVGIS_HOURLY_MIN_YEAR}–{PVGIS_HOURLY_MAX_YEAR}.")
    elif ds == "PVGIS TMY":
        st.info("PVGIS TMY — typical meteorological year (8760 hours); best for long-term yield estimates.")
    elif ds == "NASA POWER":
        st.info("NASA POWER — global coverage; hourly GHI + met (UTC). We derive DNI/DHI (DIRINT/ERBS).")
    else:
        st.info("Upload — bring your own CSV/EPW. We’ll help map columns and fix units.")

    # --- Fetch logic ---
    upload = None
    if ds == "Upload (CSV/EPW)":
        upload = st.file_uploader("Upload CSV or EPW", type=["csv","epw"], key="upload")

        # If CSV, show mapping UI after reading a preview
        if upload and upload.name.lower().endswith(".csv"):
            try:
                # Lightweight preview read without parsing index
                csv_raw = pd.read_csv(upload)
                st.write("CSV preview:")
                st.dataframe(csv_raw.head())

                cols = list(csv_raw.columns)
                st.markdown("**Map your columns** (datetime required; at least GHI or DNI+DHI required).")
                c1, c2 = st.columns(2)
                with c1:
                    dt_col = st.selectbox("Datetime column", options=["<none>"] + cols, index=0, key="csv_dt_col")
                    dt_fmt = st.text_input("Datetime format (optional, e.g. `%Y-%m-%d %H:%M`)", value="", key="csv_dt_fmt")
                with c2:
                    ghi_col = st.selectbox("GHI", options=["<none>"] + cols, index=0, key="csv_ghi_col")
                    dni_col = st.selectbox("DNI", options=["<none>"] + cols, index=0, key="csv_dni_col")
                    dhi_col = st.selectbox("DHI", options=["<none>"] + cols, index=0, key="csv_dhi_col")
                    ta_col  = st.selectbox("Air temperature", options=["<none>"] + cols, index=0, key="csv_ta_col")
                    ws_col  = st.selectbox("Wind speed", options=["<none>"] + cols, index=0, key="csv_ws_col")
                    ps_col  = st.selectbox("Pressure", options=["<none>"] + cols, index=0, key="csv_ps_col")

                if st.button("Apply mapping"):
                    if dt_col == "<none>":
                        st.error("Please select a datetime column.")
                    else:
                        df = csv_raw.copy()
                        # Parse datetime
                        if dt_fmt.strip():
                            df[dt_col] = pd.to_datetime(df[dt_col], format=dt_fmt.strip(), errors="coerce", utc=True)
                        else:
                            df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce", utc=True)
                        df = df.dropna(subset=[dt_col]).set_index(dt_col).sort_index()

                        # Build rename dict
                        rename = {}
                        if ghi_col != "<none>": rename[ghi_col] = "ghi"
                        if dni_col != "<none>": rename[dni_col] = "dni"
                        if dhi_col != "<none>": rename[dhi_col] = "dhi"
                        if ta_col  != "<none>": rename[ta_col]  = "temp_air"
                        if ws_col  != "<none>": rename[ws_col]  = "wind_speed"
                        if ps_col  != "<none>": rename[ps_col]  = "pressure"

                        df = df.rename(columns=rename)

                        # Basic requirement check
                        has_ghi = "ghi" in df.columns and not df["ghi"].isna().all()
                        has_dn_dh = ("dni" in df.columns and not df["dni"].isna().all()) and \
                                    ("dhi" in df.columns and not df["dhi"].isna().all())
                        if not (has_ghi or has_dn_dh):
                            st.error("Please map at least GHI, or both DNI and DHI.")
                        else:
                            # Harmonize units & names using our converter
                            df, conv = convert_to_canonical(df)

                            # Apply site timezone
                            lat, lon, _addr = st.session_state.get("latlon",(52.52,13.405,"Berlin, Germany"))
                            tz_name = tz_name_from_latlon(lat, lon)
                            df = ensure_tz_aware(df, tz_name)

                            # Store as fetched weather (like any other source)
                            st.session_state["raw_weather"] = df
                            st.session_state["source_meta"] = {
                                "name": "CSV Upload (mapped)",
                                "details": {"original_name": upload.name},
                                "conversions": conv,
                                "derived": {
                                    "dni": "as provided" if "dni" in df.columns else "derived later",
                                    "dhi": "as provided" if "dhi" in df.columns else "derived later"
                                }
                            }
                            st.session_state["derived_methods"] = {}
                            st.success(f"CSV mapped successfully with {len(df)} rows.")
                            st.download_button("Download normalized CSV",
                                               df.to_csv().encode("utf-8"),
                                               file_name="weather_normalized.csv")
            except Exception as e:
                st.error(f"CSV mapping error: {e}")

    if st.button("Fetch data"):
        # Non-CSV paths, or EPW upload path
        lat, lon, addr = st.session_state["latlon"]
        tz_name = tz_name_from_latlon(lat, lon)
        try:
            df = None; meta = None

            if ds == "PVGIS Hourly":
                year_val = int(st.session_state["year"])
                if year_val < PVGIS_HOURLY_MIN_YEAR or year_val > PVGIS_HOURLY_MAX_YEAR:
                    st.warning(
                        f"Year {year_val} is outside PVGIS Hourly range "
                        f"({PVGIS_HOURLY_MIN_YEAR}–{PVGIS_HOURLY_MAX_YEAR}). "
                        "Switch to NASA POWER or use PVGIS TMY."
                    )
                else:
                    df, meta = fetch_pvgis_hourly(lat, lon, year_val, tz_name)

            elif ds == "PVGIS TMY":
                df, meta = fetch_pvgis_tmy(lat, lon, tz_name)

            elif ds == "NASA POWER":
                year_val = int(st.session_state["year"])
                start = pd.Timestamp(f"{year_val}-01-01", tz="UTC")
                end   = pd.Timestamp(f"{year_val}-12-31 23:00:00", tz="UTC")
                df, meta = fetch_nasa_power_hourly(lat, lon, start, end, tz_name)

            elif ds == "Upload (CSV/EPW)":
                # If it's EPW, handle it here. CSV is handled in the mapping block above.
                if upload and upload.name.lower().endswith(".epw"):
                    tmp_path = Path(export_dir().parent/"uploads"/upload.name)
                    tmp_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(tmp_path,"wb") as f: f.write(upload.getbuffer())
                    df, meta = read_epw(tmp_path, tz_name)
                elif upload and upload.name.lower().endswith(".csv"):
                    # CSV handled by mapping above; if user hits Fetch anyway, use mapped if present
                    df = st.session_state.get("raw_weather")
                    meta = st.session_state.get("source_meta")
                    if df is None:
                        st.warning("Please map the CSV columns first using 'Apply mapping'.")
                else:
                    st.error("Please upload a CSV or EPW file.")
                    df=None; meta=None
            else:
                st.error("Invalid selection or missing file.")
                df=None; meta=None

            if df is not None:
                st.session_state["raw_weather"] = df
                if isinstance(meta, dict):
                    st.session_state["source_meta"] = meta
                elif meta is not None:
                    st.session_state["source_meta"] = meta.__dict__
                st.session_state.setdefault("derived_methods", {})
                st.success(f"Fetched {st.session_state['source_meta'].get('name','Weather')} with {len(df)} rows.")
                st.caption(f"Rows: {len(df)}, Start: {df.index.min()}, End: {df.index.max()}")
                st.dataframe(df.head())
                st.download_button("Download weather (CSV)", df.to_csv().encode("utf-8"),
                                   file_name="weather.csv")
        except Exception as e:
            if "startyear" in str(e).lower() or "endyear" in str(e).lower():
                st.error(
                    f"Fetch error: {e}\n\n"
                    f"PVGIS Hourly supports {PVGIS_HOURLY_MIN_YEAR}–{PVGIS_HOURLY_MAX_YEAR}. "
                    "Try a supported year, PVGIS TMY, or NASA POWER."
                )
            else:
                st.error(f"Fetch error: {e}")

    st.button("Next →", on_click=next_step)

# ---------- Step 2: System ----------
elif st.session_state["step"] == 2:
    st.header("Step 2 — System Definition")
    tilt = st.slider("Tilt (°)", 0, 60, int(abs(st.session_state.get("latlon",(52.52,0,""))[0])-10))
    az = st.slider("Azimuth (°)", 0, 359, 180)
    dirs = ["N","NE","E","SE","S","SW","W","NW","N"]
    st.caption(f"Direction: {dirs[int((az%360)/45)]} (0°=N, 90°=E, 180°=S, 270°=W)")

    dc_kwp = st.number_input("DC size (kWp)", 0.1, 1000.0, 10.0)
    ac_mode = st.radio("AC Spec", ["AC rating","AC/DC ratio"])
    ac_kw=None; ac_dc_ratio=None
    if ac_mode=="AC rating":
        ac_kw = st.number_input("AC rating (kW)", 0.1, 1000.0, 9.0)
    else:
        ac_dc_ratio = st.number_input("AC/DC ratio", 0.5, 1.5, 0.9)

    losses = st.slider("Losses (%)", 0, 40, 12)
    albedo = st.slider("Albedo", 0.0, 1.0, 0.2)
    irrad_model = st.radio("Irradiance model", ["haydavies","perez"])

    cfg = SystemConfig(
        tilt_deg=tilt, azimuth_deg=az, dc_kwp=dc_kwp,
        ac_kw=ac_kw, ac_dc_ratio=ac_dc_ratio,
        losses_pct=losses, albedo=albedo,
        transposition=irrad_model
    )
    st.session_state["syscfg"] = cfg.__dict__
    st.button("Next →", on_click=next_step)
    st.button("← Back", on_click=prev_step)

# ---------- Step 3: Run model ----------
elif st.session_state["step"] == 3:
    st.header("Step 3 — Run PVWatts")
    if st.button("Run simulation"):
        try:
            lat, lon, addr = st.session_state["latlon"]
            tz_name = tz_name_from_latlon(lat, lon)

            # Start from fetched weather
            weather = st.session_state["raw_weather"].copy()

            # Ensure required met columns exist
            if "temp_air" not in weather.columns:
                weather["temp_air"] = 20.0
            else:
                weather["temp_air"] = weather["temp_air"].fillna(20.0)
            if "wind_speed" not in weather.columns:
                weather["wind_speed"] = 1.0
            else:
                weather["wind_speed"] = weather["wind_speed"].fillna(1.0)

            # Derive DNI/DHI if missing or empty (e.g., NASA or CSV w/o both)
            need_dni = ("dni" not in weather.columns) or weather["dni"].isna().all()
            need_dhi = ("dhi" not in weather.columns) or weather["dhi"].isna().all()
            if need_dni or need_dhi:
                weather, deriv = derive_from_ghi(weather, lat, lon, tz_name)
                st.session_state["derived_methods"] = deriv  # record for provenance

            cfg = SystemConfig(**st.session_state["syscfg"])
            ac_w, poa, kpis, mc = run_pvwatts(weather, lat, lon, tz_name, cfg)
            st.session_state["ac_w"]=ac_w
            st.session_state["poa"]=poa
            st.session_state["kpis"]=kpis
            st.success("Simulation complete")

            # Plot 1: AC Power (first 7 days, kW)
            fig, ax = plt.subplots()
            ac_w.iloc[:24*7].div(1000).plot(ax=ax)
            ax.set_ylabel("AC Power (kW)")
            ax.set_title("AC Power — first 7 days")
            st.pyplot(fig)

            # Plot 2: Monthly Energy (kWh)
            fig2, ax2 = plt.subplots()
            ac_w.resample("M").sum().div(1000).plot(kind="bar", ax=ax2)
            ax2.set_ylabel("Energy (kWh)")
            ax2.set_title("Monthly Energy")
            st.pyplot(fig2)
        except Exception as e:
            st.error(f"Run error: {e}")
    st.button("Next →", on_click=next_step)
    st.button("← Back", on_click=prev_step)

# ---------- Step 4: Export ----------
elif st.session_state["step"] == 4:
    st.header("Step 4 — Export")

    # Build provenance info
    prov = {
        "weather_source": st.session_state.get("source_meta", {}),
        "derived": st.session_state.get("derived_methods", {}),
        "irradiance_model": st.session_state.get("syscfg",{}).get("transposition","perez"),
        "temperature_model": "faiman (fixed)",
    }
    st.subheader("Provenance")
    st.json(prov)

    ac_w = st.session_state.get("ac_w")
    if ac_w is not None:
        exports = export_dir()

        # Hourly CSV
        hourly = exports/"hourly.csv"
        ac_w.to_csv(hourly)
        st.download_button("Hourly CSV", open(hourly,"rb"), file_name="hourly.csv")

        # PDF Report
        monthly = ac_w.resample("M").sum().div(1000)
        pdf = exports/"report.pdf"
        fig_tmp, ax_tmp = plt.subplots()
        ac_w.iloc[:24*7].div(1000).plot(ax=ax_tmp)
        ax_tmp.set_ylabel("AC Power (kW)")
        ax_tmp.set_title("AC Power — first 7 days")
        sample_plot=_fig_to_png_bytes(fig_tmp)
        write_pdf(pdf,
                  {"lat":st.session_state["latlon"][0],
                   "lon":st.session_state["latlon"][1],
                   "addr":st.session_state["latlon"][2],
                   "timezone": tz_name_from_latlon(st.session_state["latlon"][0],
                                                   st.session_state["latlon"][1]),
                   "period": st.session_state.get("period_mode","Calendar Year")},
                  prov, st.session_state.get("syscfg",{}),
                  st.session_state.get("kpis",{}), monthly, sample_plot)
        st.download_button("PDF Report", open(pdf,"rb"), file_name="report.pdf")

        # ZIP bundle
        if st.button("ZIP bundle"):
            bundle=exports/"bundle.zip"
            with zipfile.ZipFile(bundle,"w") as z:
                z.write(hourly,"hourly.csv")
                z.write(pdf,"report.pdf")
                z.writestr("provenance.json", json.dumps(prov, indent=2))
                z.writestr("config.json", json.dumps(st.session_state.get("syscfg",{}), indent=2))
            st.download_button("Download Bundle", open(bundle,"rb"), file_name="bundle.zip")

    st.button("Next →", on_click=next_step)
    st.button("← Back", on_click=prev_step)

# ---------- Step 5: About ----------
elif st.session_state["step"] == 5:
    st.header("About")
    st.markdown(f"""
**{TOOL_NAME}**

Generates PV hourly data using pvlib + open weather sources.

**Overview**  
This tool is an open-source PV simulation dashboard built on **pvlib 0.13**.  
It fetches weather data from multiple open APIs (PVGIS, NASA POWER, EPW/CSV uploads),  
harmonizes them, and generates **bankable PV production time series** with KPIs, plots, and a professional PDF report.  

**Why developers love it**  
- **Transparent provenance:** every data source, conversion, and derived variable is logged.  
- **Extensible core:** built modularly (adapters, model, irradiance, cache) so contributors can plug in new data APIs or models.  
- **Reproducibility:** exports include config.json + provenance.json alongside results, ensuring runs can be recreated exactly.  
- **Standards-friendly:** weather harmonization maps to pvlib’s canonical columns (`ghi`, `dni`, `dhi`, `temp_air`, `wind_speed`, `pressure`).  
- **Lightweight deployment:** runs locally via Streamlit, Python-only dependencies, no cloud lock-in.  

**Data sources supported**  
- **PVGIS Hourly:** Europe-focused, high accuracy, supports {PVGIS_HOURLY_MIN_YEAR}–{PVGIS_HOURLY_MAX_YEAR}  
- **PVGIS TMY:** Typical Meteorological Year (8760 hrs) for long-term estimates  
- **NASA POWER:** Global hourly GHI + met, DNI/DHI derived with DIRINT/ERBS  
- **CSV / EPW:** Custom user uploads, with flexible mapping and unit conversion  

**Model stack**  
- **PVWatts v5** (pvlib)  
- **Irradiance models:** Hay-Davies, Perez  
- **Temperature model:** Faiman (fixed default, robust for most climates)  
- **Losses model:** PVWatts lumped losses  

**Limitations (MVP)**  
- No horizon/terrain shading  
- No bifacial, tracking, or degradation modeling yet  
- Derived DNI/DHI flagged in provenance when not measured  

---

**Developer**  
This tool was developed as part of an open-source energy systems engineering project.  
**Author:** Vaijayanth Sheri  
""")
    st.button("← Back", on_click=prev_step)


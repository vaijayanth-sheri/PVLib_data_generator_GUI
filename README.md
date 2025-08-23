# PVLib Data Generator GUI

**PVLib_data_generator_GUI** is a lightweight, open-source dashboard for simulating photovoltaic (PV) system generation data using [pvlib-python](https://github.com/pvlib/pvlib-python) and open weather sources.  

It provides a clean GUI (built with Streamlit) to fetch, harmonize, and simulate PV production time series, returning KPIs, plots, and professional PDF reports.

---

## ✨ Features

- **Weather sources supported**  
  - **PVGIS Hourly** (2005–2023, Europe-focused, includes DNI/DHI & met)  
  - **PVGIS TMY** (Typical Meteorological Year, 8760 hrs)  
  - **NASA POWER** (global GHI + met; DNI/DHI derived via DIRINT/ERBS)  
  - **CSV / EPW uploads** (CSV with interactive column mapping; EPW auto-parsed)

- **PV System modeling**  
  - Based on **PVWatts v5** in pvlib 0.13  
  - Irradiance transposition: Hay-Davies or Perez  
  - Temperature model: Faiman (fixed)  
  - Losses model: PVWatts lumped losses  

- **Outputs**  
  - Hourly AC power timeseries (kW)   
  - Key performance indicators: Annual kWh, PR, Capacity Factor  
  - Provenance + configuration JSON  
  - Professional multi-page PDF report with charts, tables, provenance, and system info  

- **UI**  
  - Streamlit-based, modular step-by-step workflow  
  - Sidebar navigation  
  - Configurable system (DC size, tilt, azimuth, AC/DC ratio, albedo, losses)  

---

## 🛠 Project Structure

```bash
PVLib_GUI/
│
├── .streamlit/
│ ├──  config.toml
├── data_cache/
│ ├──  .gitkeep
├── app/              
│ ├── report.py       # Report generator
├── core/             # Core modeling + utilities
│ ├── model.py        # PV system definition + PVWatts simulation
│ ├── adapters.py     # Data fetchers (PVGIS, NASA, EPW/CSV)
│ ├── irradiance.py   # Derived DNI/DHI calculations
│ ├── mapping.py      # Column mapping + unit harmonization
│ ├── cache.py        # Local cache for downloaded data
│ ├── timeutils.py    # Timezone helpers
│
├── main.py           # Main dashboard
├── requirements.txt  # Python dependencies
├── README.md  
```

---

## ⚡️ Installation & Usage

#### 1. Clone repository
```bash
git clone https://github.com/vaijayanth-sheri/PVLib_data_generator_GUI.git
cd PVLib_data_generator_GUI
```
#### 2. Setup Python environment

Recommended: Python 3.10 or 3.11 (tested with pvlib 0.13.0)

```bash
python -m venv venv
source venv/bin/activate   # On Linux/macOS
venv\Scripts\activate      # On Windows
```
#### 3. Install dependencies
```bash
pip install -r requirements.txt
```
#### 4. Run the dashboard
```bash
streamlit run app/main.py
```
Then open your browser at http://localhost:8501.

## 🤝 Contributing

- Pull requests are welcome!
- Fork the repo
- Create a feature branch (git checkout -b feature/my-feature)
- Commit changes (git commit -m "Add new feature")
- Push (git push origin feature/my-feature)
- Open a PR 🎉

## 📜 License

This project is licensed under the MIT License — see the LICENSE file for details.

## 👤 Author

Developed by Vaijayanth Sheri 



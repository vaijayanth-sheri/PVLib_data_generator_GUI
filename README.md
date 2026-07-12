---
title: PVLib GUI Backend
emoji: ☀️
colorFrom: yellow
colorTo: orange
sdk: docker
app_port: 7860
---

# PVLib GUI - Solar Energy Yield Assessment

A modern, highly interactive, and extremely performant Solar PV simulation dashboard powered by **PVLib-Python** on the backend and **React + Vite** on the frontend.

## Overview
This application provides engineering-grade solar PV modeling and yield assessment through a beautiful, seamless interface. 
It entirely replaces the previous Streamlit version with a blazing-fast decoupled architecture, allowing for instantaneous client-side UI rendering alongside heavy numerical computing on the server.

### Features
- **Interactive Site Selection:** Leaflet map integration and OpenStreetMap (Nominatim) search with automatic coordinate and timezone extraction.
- **Dynamic Weather APIs:** Automatically fetches hourly TMY/weather data from PVGIS or OpenMeteo based on the selected location.
- **Expert Mode Configuration:** Offers granular system sizing, azimuth, tilt, and comprehensive access to the CEC Modules and Sandia Inverters databases.
- **High-Performance Analytics:** 8760 hourly data points computed instantaneously and aggregated via Pandas into Hourly, Daily, and Monthly profiles without browser lag.
- **Interactive Visualizations:** Deep zoom, pan, and hover support across all time series via `react-plotly.js`.
- **Corporate Report Generation:** One-click, fully-branded PDF engineering report generation (powered by `jsPDF`) and raw CSV extraction.

## Tech Stack
- **Frontend:** React, Vite, Plotly.js, Leaflet, jsPDF, Tailwind-inspired pure CSS.
- **Backend:** FastAPI, Python, PVLib, Pandas, Uvicorn.

## Getting Started

### 1. Backend Setup
The FastAPI server handles all the complex PVLib model chain processing and data manipulation.
```bash
# Install Python dependencies
pip install -r requirements.txt

# Start the FastAPI server (runs on port 8000)
python -m uvicorn api.index:app --reload
```

### 2. Frontend Setup
The Vite development server runs the React client.
```bash
# Install Node dependencies
npm install

# Start the Vite server (runs on port 5173)
npm run dev
```

Navigate to `http://localhost:5173` to start modeling!

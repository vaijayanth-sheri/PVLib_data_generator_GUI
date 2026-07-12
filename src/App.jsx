import { useState, useEffect } from 'react'
import axios from 'axios'
import { MapPin, Sun, Activity, Download, ChevronRight, ChevronLeft, UploadCloud, CheckCircle2, Info, Zap } from 'lucide-react'
import Plot from 'react-plotly.js'
import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import BackgroundCanvas from './components/BackgroundCanvas'
import LocationMap from './components/LocationMap'
import './App.css'

const API_BASE = '/api'

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

const TooltipLabel = ({ label, tooltip }) => {
  const [show, setShow] = useState(false);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', position: 'relative' }}>
      <label className="text-secondary" style={{ margin: 0, fontSize: '0.9rem' }}>{label}</label>
      <div 
        onMouseEnter={() => setShow(true)} 
        onMouseLeave={() => setShow(false)}
        style={{ cursor: 'help', color: 'var(--accent)' }}
      >
        <Info size={14} />
      </div>
      {show && (
        <div className="animate-fade-in" style={{
          position: 'absolute', top: '100%', left: '0', marginTop: '0.5rem',
          background: 'rgba(15, 23, 42, 0.95)', border: '1px solid var(--glass-border)',
          padding: '0.75rem', borderRadius: '8px', zIndex: 100, width: '280px',
          boxShadow: '0 10px 25px rgba(0,0,0,0.5)', backdropFilter: 'blur(10px)',
          fontSize: '0.85rem', color: '#e2e8f0', pointerEvents: 'none', lineHeight: '1.4'
        }}>
          {tooltip}
        </div>
      )}
    </div>
  )
}

function App() {
  const [step, setStep] = useState(1)
  
  // Location State
  const [location, setLocation] = useState({ query: 'Berlin, Germany', lat: 52.52, lon: 13.405, timezone: 'Europe/Berlin', address: 'Berlin, Germany', confirmed: true })
  const [searchQuery, setSearchQuery] = useState(location.query)
  const [searchSuggestions, setSearchSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const debouncedQuery = useDebounce(searchQuery, 400)
  
  // Data Source State
  const [source, setSource] = useState('PVGIS Hourly')
  const [year, setYear] = useState(2023)
  const [uploadFile, setUploadFile] = useState(null)
  
  const [weatherData, setWeatherData] = useState(null)
  const [weatherMeta, setWeatherMeta] = useState(null)
  const [timeCol, setTimeCol] = useState(null)
  const [fetchSuccess, setFetchSuccess] = useState(false)
  
  // System Config State
  const [expertMode, setExpertMode] = useState(false)
  const [sysCfg, setSysCfg] = useState({
    tilt_deg: 35,
    azimuth_deg: 180,
    albedo: 0.2,
    losses_pct: 14.0,
    transposition: 'perez',
    // Basic Mode
    dc_kwp: 10.0,
    ac_kw: 9.0,
    // Expert Mode
    module_name: 'Custom',
    inverter_name: '',
    modules_per_string: 14,
    strings_per_inverter: 2,
    custom_module_params: { pdc0: 400, gamma_pdc: -0.003 } // 400W panel
  })
  
  const [providersDb, setProvidersDb] = useState({ modules: [], inverters: [] })
  const [componentsDb, setComponentsDb] = useState({ modules: [], inverters: [] })
  const [selectedModuleProvider, setSelectedModuleProvider] = useState('Custom')
  const [selectedInverterProvider, setSelectedInverterProvider] = useState('')
  const [simResults, setSimResults] = useState(null)
  const [chartResolution, setChartResolution] = useState('hourly') // 'hourly', 'daily', 'monthly'
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Fetch nominatim suggestions
  useEffect(() => {
    if (debouncedQuery && debouncedQuery.length > 2 && showSuggestions) {
      axios.get(`https://nominatim.openstreetmap.org/search?q=${debouncedQuery}&format=json&limit=5`)
        .then(res => setSearchSuggestions(res.data))
        .catch(err => console.error("Autocomplete error:", err))
    } else {
      setSearchSuggestions([])
    }
  }, [debouncedQuery, showSuggestions])

  // Fetch components DB providers when expert mode enabled
  useEffect(() => {
    if (expertMode && providersDb.modules.length === 0) {
      axios.get(`${API_BASE}/components?type=module`)
        .then(res => {
          setProvidersDb(prev => ({ ...prev, modules: res.data.providers || [] }))
        })
        .catch(err => console.error("Module providers fetch error:", err))

      axios.get(`${API_BASE}/components?type=inverter`)
        .then(res => {
          setProvidersDb(prev => ({ ...prev, inverters: res.data.providers || [] }))
          if (res.data.providers && res.data.providers.length > 0) {
            setSelectedInverterProvider(res.data.providers[0])
          }
        })
        .catch(err => console.error("Inverter providers fetch error:", err))
    }
  }, [expertMode, providersDb.modules.length])

  // Fetch module items when provider changes
  useEffect(() => {
    if (expertMode && selectedModuleProvider) {
      if (selectedModuleProvider === 'Custom') {
        setSysCfg(prev => ({ ...prev, module_name: 'Custom' }))
        setComponentsDb(prev => ({ ...prev, modules: [] }))
        return
      }
      axios.get(`${API_BASE}/components?type=module&provider=${selectedModuleProvider}`)
        .then(res => {
          setComponentsDb(prev => ({ ...prev, modules: res.data.items || [] }))
          if (res.data.items && res.data.items.length > 0) {
            setSysCfg(prev => ({ ...prev, module_name: res.data.items[0] }))
          }
        })
    }
  }, [expertMode, selectedModuleProvider])

  // Fetch inverter items when provider changes
  useEffect(() => {
    if (expertMode && selectedInverterProvider) {
      axios.get(`${API_BASE}/components?type=inverter&provider=${selectedInverterProvider}`)
        .then(res => {
          setComponentsDb(prev => ({ ...prev, inverters: res.data.items || [] }))
          if (res.data.items && res.data.items.length > 0) {
            setSysCfg(prev => ({ ...prev, inverter_name: res.data.items[0] }))
          }
        })
    }
  }, [expertMode, selectedInverterProvider])

  const recommendSource = (lat, lon) => {
    if (lat > -40 && lat < 60 && lon > -20 && lon < 50) setSource('PVGIS Hourly')
    else setSource('NASA POWER')
  }

  const selectSuggestion = async (sugg) => {
    setLoading(true); setError(null); setShowSuggestions(false); setSearchQuery(sugg.display_name); setFetchSuccess(false);
    try {
      const res = await axios.post(`${API_BASE}/location/search`, { query: sugg.display_name })
      setLocation({ query: sugg.display_name, lat: parseFloat(sugg.lat), lon: parseFloat(sugg.lon), timezone: res.data.timezone, address: res.data.address, confirmed: true })
      recommendSource(parseFloat(sugg.lat), parseFloat(sugg.lon))
    } catch (err) { setError('Location timezone lookup failed.') } 
    finally { setLoading(false) }
  }

  const handleMapClick = async ({ lat, lon }) => {
    setLoading(true); setError(null); setFetchSuccess(false);
    try {
      const tzRes = await axios.post(`${API_BASE}/location/search`, { query: `${lat}, ${lon}` })
      const addr = tzRes.data.address || `Lat: ${lat.toFixed(4)}, Lon: ${lon.toFixed(4)}`
      setSearchQuery(addr)
      setLocation({ query: addr, lat: lat, lon: lon, timezone: tzRes.data.timezone, address: addr, confirmed: true })
      recommendSource(lat, lon)
    } catch (err) { setError('Coordinate lookup failed.') } 
    finally { setLoading(false) }
  }

  const handleFetch = async () => {
    setLoading(true); setError(null); setFetchSuccess(false);
    try {
      let res;
      if (source === 'Upload EPW') {
        if (!uploadFile) throw new Error("Please select an EPW file to upload.");
        const formData = new FormData()
        formData.append('file', uploadFile)
        formData.append('tz_name', location.timezone)
        res = await axios.post(`${API_BASE}/weather/upload`, formData)
      } else {
        res = await axios.post(`${API_BASE}/weather/fetch`, { source, lat: location.lat, lon: location.lon, year: (source === 'PVGIS Hourly' || source === 'NASA POWER') ? parseInt(year) : null, tz_name: location.timezone })
      }
      setWeatherData(res.data.weather)
      setWeatherMeta(res.data.meta)
      setTimeCol(res.data.time_col)
      setFetchSuccess(true)
    } catch (err) { setError(err.response?.data?.detail || err.message || 'Failed to fetch weather data.') } 
    finally { setLoading(false) }
  }
  
  const handleSimulate = async () => {
    setLoading(true); setError(null);
    try {
      const payload = {
        weather: weatherData,
        time_col: timeCol,
        lat: location.lat,
        lon: location.lon,
        tz_name: location.timezone,
        syscfg: {
          ...sysCfg,
          expert_mode: expertMode,
          custom_module_params: sysCfg.module_name === 'Custom' ? sysCfg.custom_module_params : null
        }
      }
      const res = await axios.post(`${API_BASE}/simulate`, payload)
      setSimResults(res.data)
      setStep(3)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to run simulation.')
    } finally {
      setLoading(false)
    }
  }

  const getYears = () => {
    const years = []
    if (source === 'PVGIS Hourly') {
      for (let y = 2023; y >= 2005; y--) years.push(y)
    } else if (source === 'NASA POWER') {
      const max = new Date().getFullYear() - 1
      for (let y = max; y >= 1984; y--) years.push(y)
    }
    return years
  }

  const getChartData = () => {
    if (!simResults || !simResults.series) return { x: [], y: [] };
    const series = simResults.series[chartResolution] || simResults.series.hourly;
    // To prevent browser lag with hourly data, we can subsample or rely on Plotly's WebGL
    // Plotly standard handles 8760 points reasonably well.
    return {
      x: series.map(row => row.time),
      y: series.map(row => row.ac_kwh)
    };
  }
  
  const chartProps = getChartData();

  // Export Functions
  const downloadHourlyCSV = () => {
    if (!simResults?.series?.hourly) return;
    const data = simResults.series.hourly;
    
    // Create CSV header
    const headers = ['Time', 'AC Energy (kWh)', 'DC Energy (kWh)', 'POA Irradiance (kWh/m2)'];
    const rows = data.map(row => [
      row.time,
      (row.ac_kwh || 0).toFixed(4),
      (row.dc_kwh || 0).toFixed(4),
      (row.poa_kwhm2 || 0).toFixed(4)
    ]);
    
    const csvContent = [
      headers.join(','),
      ...rows.map(e => e.join(','))
    ].join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `pv_hourly_simulation_${new Date().getTime()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const generateProfessionalPDF = () => {
    if (!simResults) return;
    
    const doc = new jsPDF('p', 'pt', 'a4');
    const pageWidth = doc.internal.pageSize.getWidth();
    
    // Colors and Fonts
    const primaryColor = [30, 27, 75]; // deep indigo
    const accentColor = [99, 102, 241]; // indigo
    
    // Header
    doc.setFillColor(...primaryColor);
    doc.rect(0, 0, pageWidth, 60, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(22);
    doc.setFont('helvetica', 'bold');
    doc.text('Solar PV Yield Assessment Report', 40, 38);
    
    // Consultant Info
    doc.setTextColor(100, 100, 100);
    doc.setFontSize(10);
    doc.setFont('helvetica', 'normal');
    doc.text(`Generated on: ${new Date().toLocaleString()}`, 40, 90);
    doc.text(`Project Address: ${searchQuery}`, 40, 105);
    doc.text(`Coordinates: ${location.lat.toFixed(4)}, ${location.lon.toFixed(4)}`, 40, 120);
    
    // Divider
    doc.setDrawColor(...accentColor);
    doc.setLineWidth(2);
    doc.line(40, 140, pageWidth - 40, 140);
    
    // Section 1: Executive Summary
    doc.setTextColor(...primaryColor);
    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.text('1. Executive Summary', 40, 170);
    
    const kpiData = [
      ['Annual AC Energy Yield:', `${simResults.kpis?.annual_energy?.toLocaleString(undefined, {maximumFractionDigits:0})} kWh`],
      ['Specific Yield:', `${simResults.kpis?.specific_yield?.toLocaleString(undefined, {maximumFractionDigits:0})} kWh/kWp`],
      ['Performance Ratio (PR):', `${((simResults.kpis?.performance_ratio || 0) * 100).toFixed(1)} %`],
      ['Capacity Factor:', `${((simResults.kpis?.capacity_factor || 0) * 100).toFixed(1)} %`],
      ['Total POA Irradiance:', `${simResults.kpis?.poa_kwhm2?.toLocaleString(undefined, {maximumFractionDigits:0})} kWh/m²`]
    ];
    
    autoTable(doc, {
      startY: 185,
      margin: { left: 40 },
      tableWidth: 250,
      theme: 'plain',
      body: kpiData,
      styles: { fontSize: 11, cellPadding: 4, textColor: [50, 50, 50] },
      columnStyles: { 0: { fontStyle: 'bold', cellWidth: 140 }, 1: { cellWidth: 110 } }
    });
    
    // Section 2: System Configuration
    let nextY = doc.lastAutoTable.finalY + 30;
    doc.setTextColor(...primaryColor);
    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.text('2. System Configuration', 40, nextY);
    
    const configData = [
      ['DC Capacity (kWp):', getExpertDcSize()],
      ['AC Capacity (kW):', sysCfg.ac_kw || 'Auto'],
      ['Tilt Angle:', `${sysCfg.tilt_deg}°`],
      ['Azimuth Angle:', `${sysCfg.azimuth_deg}° (0=N, 180=S)`],
      ['System Losses:', `${sysCfg.losses_pct}%`]
    ];
    
    if (expertMode) {
      configData.push(['PV Module:', sysCfg.module_name]);
      configData.push(['Inverter:', sysCfg.inverter_name]);
      configData.push(['Modules per String:', sysCfg.modules_per_string]);
      configData.push(['Strings per Inverter:', sysCfg.strings_per_inverter]);
    }
    
    autoTable(doc, {
      startY: nextY + 15,
      margin: { left: 40 },
      tableWidth: 400,
      theme: 'striped',
      head: [['Parameter', 'Value']],
      body: configData,
      headStyles: { fillColor: accentColor, textColor: 255 },
      styles: { fontSize: 10, cellPadding: 5 }
    });
    
    // Section 3: Monthly Generation Profile (Force New Page)
    doc.addPage();
    nextY = 60;
    
    doc.setTextColor(...primaryColor);
    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.text('3. Monthly Generation Profile', 40, nextY);
    
    const monthlyRows = simResults.series?.monthly?.map((row) => {
      const date = new Date(row.time);
      return [
        date.toLocaleString('default', { month: 'long', timeZone: 'UTC' }),
        (row.poa_kwhm2 || 0).toFixed(1),
        (row.dc_kwh || 0).toFixed(1),
        (row.ac_kwh || 0).toFixed(1)
      ];
    }) || [];
    
    autoTable(doc, {
      startY: nextY + 15,
      margin: { left: 40, right: 40 },
      theme: 'grid',
      head: [['Month', 'POA Irradiance (kWh/m²)', 'DC Energy (kWh)', 'AC Energy (kWh)']],
      body: monthlyRows,
      headStyles: { fillColor: primaryColor, textColor: 255, halign: 'center' },
      bodyStyles: { halign: 'right' },
      columnStyles: { 0: { halign: 'left' } },
      foot: [['Total', 
        simResults.kpis?.poa_kwhm2?.toLocaleString(undefined, {maximumFractionDigits:0}),
        simResults.kpis?.annual_dc_kwh?.toLocaleString(undefined, {maximumFractionDigits:0}),
        simResults.kpis?.annual_energy?.toLocaleString(undefined, {maximumFractionDigits:0})
      ]],
      footStyles: { fillColor: [240, 240, 240], textColor: [0, 0, 0], fontStyle: 'bold', halign: 'right' }
    });
    
    // Footer
    const pageCount = doc.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i);
      doc.setFontSize(8);
      doc.setTextColor(150);
      doc.text(`Generated using PVLib`, 40, doc.internal.pageSize.getHeight() - 20);
      doc.text(`Page ${i} of ${pageCount}`, pageWidth - 70, doc.internal.pageSize.getHeight() - 20);
    }
    
    doc.save(`Solar_PV_Report_${new Date().getTime()}.pdf`);
  };

  // Dynamic calculations for expert mode UI feedback
  const getExpertDcSize = () => {
    let modulePower = 300
    if (sysCfg.module_name === 'Custom') modulePower = sysCfg.custom_module_params.pdc0
    return ((modulePower * sysCfg.modules_per_string * sysCfg.strings_per_inverter) / 1000).toFixed(2)
  }

  return (
    <>
      <BackgroundCanvas />
      <div className="container" style={{ maxWidth: '1200px', margin: '0 auto', padding: '2rem', position: 'relative', zIndex: 10 }}>
        <h1 style={{ textAlign: 'center', marginBottom: '2rem' }}>PVLib Data Generator</h1>
      
        <div className="step-indicator">
          {[{ id: 1, name: 'Site & Data', icon: <MapPin size={20} /> }, { id: 2, name: 'System', icon: <Sun size={20} /> }, { id: 3, name: 'Results', icon: <Activity size={20} /> }, { id: 4, name: 'Export', icon: <Download size={20} /> }].map(s => (
            <div key={s.id} className={`step-item ${step === s.id ? 'active' : ''} ${step > s.id ? 'completed' : ''}`} onClick={() => setStep(s.id)}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>{s.icon} <span>{s.name}</span></div>
            </div>
          ))}
        </div>

        <div className="glass-panel animate-fade-in" style={{ minHeight: '500px' }}>
          {error && <div style={{ background: 'rgba(239, 68, 68, 0.2)', border: '1px solid var(--danger)', padding: '1rem', borderRadius: '8px', marginBottom: '1.5rem' }}>{error}</div>}
          
          {/* STEP 1: Location & Data Source (Collapsed to keep code clean, unchanged logic) */}
          {step === 1 && (
            <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
              <div style={{ padding: '1.5rem', background: 'rgba(0,0,0,0.1)', borderRadius: '12px', border: '1px solid var(--glass-border)' }}>
                <h3 style={{ marginBottom: '1.5rem', color: 'var(--accent)' }}>1. Define Location</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
                  <div>
                    <label className="text-secondary" style={{ display: 'block', marginBottom: '0.5rem' }}>Search Address</label>
                    <div style={{ position: 'relative' }}>
                      <input className="input-field" value={searchQuery} onChange={e => { setSearchQuery(e.target.value); setShowSuggestions(true); }} onKeyDown={e => { if (e.key === 'Enter') selectSuggestion({ display_name: searchQuery, lat: location.lat, lon: location.lon }) }} placeholder="Start typing to search..." style={{ marginBottom: '1rem' }} />
                      {showSuggestions && searchSuggestions.length > 0 && (
                        <div style={{ position: 'absolute', top: '100%', left: 0, width: '100%', background: '#1e1b4b', border: '1px solid var(--glass-border)', borderRadius: '8px', zIndex: 100, maxHeight: '200px', overflowY: 'auto' }}>
                          {searchSuggestions.map((s, i) => (
                            <div key={i} onClick={() => selectSuggestion(s)} style={{ padding: '0.75rem 1rem', cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.05)' }} onMouseEnter={e => e.target.style.background = 'rgba(255,255,255,0.1)'} onMouseLeave={e => e.target.style.background = 'transparent'}>{s.display_name}</div>
                          ))}
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
                      <div style={{ flex: 1 }}><label className="text-secondary" style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem' }}>Latitude</label><input className="input-field" type="number" step="0.0001" value={location.lat} onChange={e => setLocation({...location, lat: parseFloat(e.target.value)})} onBlur={() => handleMapClick({lat: location.lat, lon: location.lon})} /></div>
                      <div style={{ flex: 1 }}><label className="text-secondary" style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem' }}>Longitude</label><input className="input-field" type="number" step="0.0001" value={location.lon} onChange={e => setLocation({...location, lon: parseFloat(e.target.value)})} onBlur={() => handleMapClick({lat: location.lat, lon: location.lon})} /></div>
                    </div>
                    <div style={{ padding: '1rem', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: '8px' }}>
                      <p style={{ margin: 0 }}><strong>Detected Timezone:</strong> {location.timezone}</p>
                    </div>
                  </div>
                  <div><label className="text-secondary" style={{ display: 'block', marginBottom: '0.5rem' }}>Map View (Click to set pin)</label><LocationMap lat={location.lat} lon={location.lon} onLocationChange={handleMapClick} /></div>
                </div>
              </div>

              <div style={{ padding: '1.5rem', background: location.confirmed ? 'rgba(0,0,0,0.1)' : 'rgba(0,0,0,0.3)', borderRadius: '12px', border: '1px solid var(--glass-border)', opacity: location.confirmed ? 1 : 0.5, pointerEvents: location.confirmed ? 'auto' : 'none', transition: 'all 0.3s ease' }}>
                <h3 style={{ marginBottom: '1.5rem', color: 'var(--accent)' }}>2. Weather Data Source</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
                  <div>
                    <label className="text-secondary" style={{ display: 'block', marginBottom: '0.5rem' }}>Select Provider</label>
                    <select className="input-field" value={source} onChange={e => { setSource(e.target.value); setFetchSuccess(false); }} style={{ background: '#1e1b4b', cursor: 'pointer', marginBottom: '1.5rem' }}>
                      <option value="PVGIS Hourly">PVGIS Hourly (Recommended for EU/Africa)</option>
                      <option value="PVGIS TMY">PVGIS TMY (Typical Meteorological Year)</option>
                      <option value="NASA POWER">NASA POWER Hourly (Global)</option>
                      <option value="Upload EPW">Upload Custom EPW File</option>
                    </select>
                    {(source === 'PVGIS Hourly' || source === 'NASA POWER') && (
                      <div className="animate-fade-in">
                        <label className="text-secondary" style={{ display: 'block', marginBottom: '0.5rem' }}>Select Year</label>
                        <select className="input-field" value={year} onChange={e => { setYear(e.target.value); setFetchSuccess(false); }} style={{ background: '#1e1b4b', cursor: 'pointer' }}>
                          {getYears().map(y => <option key={y} value={y}>{y}</option>)}
                        </select>
                      </div>
                    )}
                    {source === 'Upload EPW' && (
                      <div className="animate-fade-in" style={{ padding: '1.5rem', border: '2px dashed var(--glass-border)', borderRadius: '8px', textAlign: 'center', cursor: 'pointer' }}>
                        <UploadCloud size={32} style={{ color: 'var(--accent)', marginBottom: '0.5rem' }} />
                        <p className="text-secondary" style={{ marginBottom: '0.5rem' }}>Drop your .epw file here or</p>
                        <input type="file" accept=".epw" onChange={e => { setUploadFile(e.target.files[0]); setFetchSuccess(false); }} style={{ width: '100%', color: 'var(--text-primary)' }} />
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <button className="btn" onClick={handleFetch} disabled={loading} style={{ width: '100%', justifyContent: 'center', padding: '1rem', fontSize: '1.1rem' }}>
                      {loading ? 'Fetching Weather Data...' : 'Download Weather Data'} <Download size={20} />
                    </button>
                    {fetchSuccess && weatherData && (
                      <div className="animate-fade-in" style={{ marginTop: '1.5rem', padding: '1rem', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid var(--success)', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--success)' }}>
                        <CheckCircle2 size={24} />
                        <div><strong>Success!</strong> Data loaded perfectly.<br/><span style={{ fontSize: '0.85rem' }}>Ready with {weatherData.length} hours of data.</span></div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}><button className="btn" onClick={() => setStep(2)} disabled={!fetchSuccess} style={{ padding: '0.75rem 2rem' }}>Proceed to System Config <ChevronRight size={20} /></button></div>
            </div>
          )}

          {/* STEP 2: System Configuration */}
          {step === 2 && (
            <div className="animate-fade-in">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h2>System Configuration</h2>
                
                {/* Expert Mode Toggle */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', background: 'rgba(0,0,0,0.2)', padding: '0.5rem 1rem', borderRadius: '30px', border: '1px solid var(--glass-border)' }}>
                  <Zap size={18} color={expertMode ? '#f59e0b' : '#64748b'} />
                  <span style={{ fontWeight: '500', color: expertMode ? '#f59e0b' : 'var(--text-primary)' }}>Expert Mode</span>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={expertMode} onChange={(e) => setExpertMode(e.target.checked)} />
                    <span className="slider"></span>
                  </label>
                </div>
              </div>

              {/* Layout Configuration */}
              <div style={{ background: 'rgba(0,0,0,0.1)', padding: '1.5rem', borderRadius: '12px', border: '1px solid var(--glass-border)', marginBottom: '2rem' }}>
                <h3 style={{ marginBottom: '1.5rem', color: 'var(--accent)', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '0.5rem' }}>Layout & Environment</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                  <div>
                    <TooltipLabel label="Surface Tilt (°)" tooltip="The angle of the modules relative to horizontal. Germany industry default is often 30-35° for optimal annual yield." />
                    <input className="input-field" type="number" value={sysCfg.tilt_deg} onChange={e => setSysCfg({...sysCfg, tilt_deg: parseFloat(e.target.value)})} />
                  </div>
                  <div>
                    <TooltipLabel label="Surface Azimuth (°)" tooltip="The compass direction the panels face. North=0°, East=90°, South=180°, West=270°." />
                    <input className="input-field" type="number" value={sysCfg.azimuth_deg} onChange={e => setSysCfg({...sysCfg, azimuth_deg: parseFloat(e.target.value)})} />
                  </div>
                  <div>
                    <TooltipLabel label="Albedo" tooltip="Ground reflectance. Grass/soil is typically 0.2. Snow can be 0.6-0.8. Crucial for bifacial or high-tilt systems." />
                    <input className="input-field" type="number" step="0.05" value={sysCfg.albedo} onChange={e => setSysCfg({...sysCfg, albedo: parseFloat(e.target.value)})} />
                  </div>
                  <div>
                    <TooltipLabel label="System Losses (%)" tooltip="Lumped losses covering soiling, shading, wiring, mismatch, and LID. PVWatts default is 14%." />
                    <input className="input-field" type="number" step="0.5" value={sysCfg.losses_pct} onChange={e => setSysCfg({...sysCfg, losses_pct: parseFloat(e.target.value)})} />
                  </div>
                </div>
              </div>

              {/* Sizing Configuration */}
              <div className="animate-fade-in" style={{ background: 'rgba(0,0,0,0.1)', padding: '1.5rem', borderRadius: '12px', border: '1px solid var(--glass-border)' }}>
                <h3 style={{ marginBottom: '1.5rem', color: 'var(--accent)', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '0.5rem' }}>Electrical Sizing</h3>
                
                {!expertMode ? (
                  // BASIC MODE SIZING
                  <div className="animate-fade-in" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                    <div>
                      <TooltipLabel label="Total DC Capacity (kWp)" tooltip="The total nameplate capacity of all solar panels combined." />
                      <input className="input-field" type="number" step="0.1" value={sysCfg.dc_kwp} onChange={e => setSysCfg({...sysCfg, dc_kwp: parseFloat(e.target.value)})} />
                    </div>
                    <div>
                      <TooltipLabel label="Inverter AC Rating (kW)" tooltip="The maximum AC output limit of the inverter. DC/AC ratio is usually 1.1 to 1.3." />
                      <input className="input-field" type="number" step="0.1" value={sysCfg.ac_kw} onChange={e => setSysCfg({...sysCfg, ac_kw: parseFloat(e.target.value)})} />
                    </div>
                  </div>
                ) : (
                  // EXPERT MODE SIZING
                  <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    
                    {/* Module Selectors */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                      <div>
                        <TooltipLabel label="PV Module Manufacturer" tooltip="Select a manufacturer to load available panels." />
                        <select className="input-field" value={selectedModuleProvider} onChange={e => setSelectedModuleProvider(e.target.value)} style={{ background: '#1e1b4b', cursor: 'pointer' }}>
                          <option value="Custom">-- Custom Panel --</option>
                          {providersDb.modules.map((m, i) => <option key={i} value={m}>{m}</option>)}
                        </select>
                      </div>
                      <div>
                        <TooltipLabel label="PV Module Model" tooltip="Select the specific module model from the database." />
                        <select className="input-field" value={sysCfg.module_name} onChange={e => setSysCfg({...sysCfg, module_name: e.target.value})} disabled={selectedModuleProvider === 'Custom'} style={{ background: '#1e1b4b', cursor: 'pointer', opacity: selectedModuleProvider === 'Custom' ? 0.5 : 1 }}>
                          {selectedModuleProvider === 'Custom' ? <option value="Custom">Custom Parameters</option> : componentsDb.modules.map((m, i) => <option key={i} value={m}>{m.replace(selectedModuleProvider + '_', '')}</option>)}
                        </select>
                      </div>
                    </div>

                    {/* Inverter Selectors */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                      <div>
                        <TooltipLabel label="Inverter Manufacturer" tooltip="Select a manufacturer to load available inverters." />
                        <select className="input-field" value={selectedInverterProvider} onChange={e => setSelectedInverterProvider(e.target.value)} style={{ background: '#1e1b4b', cursor: 'pointer' }}>
                          {providersDb.inverters.length === 0 && <option>Loading...</option>}
                          {providersDb.inverters.map((inv, i) => <option key={i} value={inv}>{inv}</option>)}
                        </select>
                      </div>
                      <div>
                        <TooltipLabel label="Inverter Model" tooltip="Select the specific inverter model." />
                        <select className="input-field" value={sysCfg.inverter_name} onChange={e => setSysCfg({...sysCfg, inverter_name: e.target.value})} style={{ background: '#1e1b4b', cursor: 'pointer' }}>
                          {componentsDb.inverters.length === 0 && <option>Waiting for provider...</option>}
                          {componentsDb.inverters.map((inv, i) => <option key={i} value={inv}>{inv.replace(selectedInverterProvider + '_', '')}</option>)}
                        </select>
                      </div>
                    </div>

                    {/* Custom Panel Inputs */}
                    {sysCfg.module_name === 'Custom' && (
                      <div className="animate-fade-in" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', padding: '1rem', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px dashed var(--glass-border)' }}>
                        <div>
                          <TooltipLabel label="Panel Nameplate Power (W)" tooltip="STC maximum power output of a single panel." />
                          <input className="input-field" type="number" value={sysCfg.custom_module_params.pdc0} onChange={e => setSysCfg({...sysCfg, custom_module_params: { ...sysCfg.custom_module_params, pdc0: parseFloat(e.target.value) }})} />
                        </div>
                        <div>
                          <TooltipLabel label="Temperature Coefficient (%/°C)" tooltip="Power loss per degree above 25°C. Usually around -0.3% to -0.4%. Enter as negative decimal (e.g. -0.0035 for -0.35%)." />
                          <input className="input-field" type="number" step="0.0001" value={sysCfg.custom_module_params.gamma_pdc} onChange={e => setSysCfg({...sysCfg, custom_module_params: { ...sysCfg.custom_module_params, gamma_pdc: parseFloat(e.target.value) }})} />
                        </div>
                      </div>
                    )}

                    {/* String Sizing */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                      <div>
                        <TooltipLabel label="Modules per String" tooltip="Number of panels wired in series. Determines the string voltage." />
                        <input className="input-field" type="number" value={sysCfg.modules_per_string} onChange={e => setSysCfg({...sysCfg, modules_per_string: parseInt(e.target.value)})} />
                      </div>
                      <div>
                        <TooltipLabel label="Strings per Inverter" tooltip="Number of parallel strings connected to the inverter." />
                        <input className="input-field" type="number" value={sysCfg.strings_per_inverter} onChange={e => setSysCfg({...sysCfg, strings_per_inverter: parseInt(e.target.value)})} />
                      </div>
                    </div>

                    {/* Auto Calculated Preview */}
                    <div style={{ padding: '1rem', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <span style={{ color: 'var(--success)', fontWeight: '500' }}>Calculated DC Capacity</span>
                        <p style={{ margin: 0, fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>Automatically sized based on string configuration</p>
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--success)' }}>
                        {getExpertDcSize()} kWp
                      </div>
                    </div>

                  </div>
                )}
              </div>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '3rem' }}>
                <button className="btn" onClick={() => setStep(1)} style={{ background: 'transparent', border: '1px solid var(--glass-border)' }}>
                  <ChevronLeft size={18} /> Back
                </button>
                <button className="btn" onClick={handleSimulate} disabled={loading || !weatherData || (expertMode && componentsDb.inverters.length === 0)}>
                  {loading ? 'Simulating...' : 'Run Simulation'} <ChevronRight size={18} />
                </button>
              </div>
            </div>
          )}

          {/* STEP 3 & 4 (Collapsed) */}
          {step === 3 && simResults && (
            <div className="animate-fade-in">
              <h2>Simulation Results</h2>
              
              {/* KPI Dashboard (6 Cards) */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem', marginTop: '2rem', marginBottom: '2rem' }}>
                <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '2rem' }}>{(simResults.kpis?.annual_energy || 0).toLocaleString(undefined, {maximumFractionDigits:0})}</h3>
                  <p className="text-secondary">Annual AC Energy (kWh)</p>
                </div>
                <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '2rem', color: 'var(--success)' }}>{(simResults.kpis?.specific_yield || 0).toLocaleString(undefined, {maximumFractionDigits:0})}</h3>
                  <p className="text-secondary">Specific Yield (kWh/kWp)</p>
                </div>
                <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '2rem' }}>{((simResults.kpis?.performance_ratio || 0) * 100).toFixed(1)}%</h3>
                  <p className="text-secondary">Performance Ratio</p>
                </div>
                <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '1.75rem' }}>{((simResults.kpis?.capacity_factor || 0) * 100).toFixed(1)}%</h3>
                  <p className="text-secondary">Capacity Factor</p>
                </div>
                <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '1.75rem' }}>{(simResults.kpis?.poa_kwhm2 || 0).toLocaleString(undefined, {maximumFractionDigits:0})}</h3>
                  <p className="text-secondary">Total POA Irradiance (kWh/m²)</p>
                </div>
                <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '1.75rem' }}>{(simResults.kpis?.annual_dc_kwh || 0).toLocaleString(undefined, {maximumFractionDigits:0})}</h3>
                  <p className="text-secondary">Annual DC Energy (kWh)</p>
                </div>
              </div>

              {/* Interactive Plotly Chart */}
              <div className="glass-panel" style={{ padding: '1rem', height: 'auto', marginBottom: '2rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h3 style={{ margin: 0 }}>System Output</h3>
                  <select 
                    className="input-field" 
                    style={{ width: 'auto', background: 'rgba(0,0,0,0.3)', padding: '0.5rem 1rem' }}
                    value={chartResolution}
                    onChange={(e) => setChartResolution(e.target.value)}
                  >
                    <option value="hourly">Hourly (kWh)</option>
                    <option value="daily">Daily (kWh)</option>
                    <option value="monthly">Monthly (kWh)</option>
                  </select>
                </div>
                
                <div style={{ background: '#0f172a', borderRadius: '8px', overflow: 'hidden' }}>
                  <Plot
                    data={[
                      {
                        x: chartProps.x,
                        y: chartProps.y,
                        type: chartResolution === 'monthly' ? 'bar' : 'scatter',
                        mode: 'lines',
                        marker: { color: '#6366f1' },
                        line: { color: '#6366f1', width: 2 },
                        name: 'AC Energy (kWh)'
                      }
                    ]}
                    layout={{
                      autosize: true,
                      height: 450,
                      margin: { l: 50, r: 20, t: 20, b: 40 },
                      paper_bgcolor: 'transparent',
                      plot_bgcolor: 'transparent',
                      font: { color: '#94a3b8' },
                      xaxis: { 
                        gridcolor: 'rgba(255,255,255,0.05)',
                        zerolinecolor: 'rgba(255,255,255,0.1)'
                      },
                      yaxis: { 
                        title: 'Energy (kWh)',
                        gridcolor: 'rgba(255,255,255,0.05)',
                        zerolinecolor: 'rgba(255,255,255,0.1)'
                      }
                    }}
                    config={{ responsive: true, displayModeBar: true, displaylogo: false }}
                    style={{ width: '100%', height: '100%' }}
                  />
                </div>
              </div>

              {/* Monthly Data Table */}
              <div className="glass-panel" style={{ padding: '1.5rem' }}>
                <h3 style={{ marginBottom: '1rem' }}>Monthly Summary</h3>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--glass-border)', color: 'var(--accent)' }}>
                        <th style={{ padding: '0.75rem' }}>Month</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right' }}>POA Irradiance (kWh/m²)</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right' }}>DC Energy (kWh)</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right' }}>AC Energy (kWh)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {simResults.series?.monthly?.map((row, i) => {
                        const date = new Date(row.time);
                        const monthName = date.toLocaleString('default', { month: 'long', timeZone: 'UTC' });
                        return (
                          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', ':hover': { background: 'rgba(255,255,255,0.02)' } }}>
                            <td style={{ padding: '0.75rem' }}>{monthName}</td>
                            <td style={{ padding: '0.75rem', textAlign: 'right' }}>{(row.poa_kwhm2 || 0).toFixed(1)}</td>
                            <td style={{ padding: '0.75rem', textAlign: 'right' }}>{(row.dc_kwh || 0).toFixed(1)}</td>
                            <td style={{ padding: '0.75rem', textAlign: 'right', fontWeight: '500', color: 'var(--success)' }}>{(row.ac_kwh || 0).toFixed(1)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '3rem' }}>
                <button className="btn" onClick={() => setStep(2)} style={{ background: 'transparent', border: '1px solid var(--glass-border)' }}><ChevronLeft size={18} /> Back</button>
                <button className="btn" onClick={() => setStep(4)}>Proceed to Export <ChevronRight size={18} /></button>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="animate-fade-in" style={{ textAlign: 'center', padding: '2rem' }}>
              <h2>Export Data</h2>
              <p className="text-secondary" style={{ marginBottom: '3rem' }}>Download your simulation results, PDF report, and provenance data.</p>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '2rem' }}>
                 <button className="btn" onClick={downloadHourlyCSV} style={{ padding: '1rem 2rem', fontSize: '1.1rem' }}>
                   <Download size={20} /> Download Hourly Data (CSV)
                 </button>
                 <button className="btn" style={{ background: '#10b981', padding: '1rem 2rem', fontSize: '1.1rem' }} onClick={generateProfessionalPDF}>
                   <Download size={20} /> Generate Professional Report (PDF)
                 </button>
              </div>
              <div style={{ marginTop: '4rem' }}>
                <button className="btn" onClick={() => setStep(3)} style={{ background: 'transparent', border: '1px solid var(--glass-border)' }}>
                  <ChevronLeft size={18} /> Back to Results
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

export default App

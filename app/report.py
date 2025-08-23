from __future__ import annotations
from pathlib import Path
from datetime import datetime
import io, json
import pandas as pd
import matplotlib.pyplot as plt
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak
)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

TOOL_NAME = "PVLib_data_generator_GUI"
AUTHOR_NAME = "Vaijayanth Sheri"

# -----------------------
# helpers
# -----------------------
def _fig_to_png_bytes(fig) -> bytes:
    bio = io.BytesIO()
    fig.savefig(bio, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    bio.seek(0)
    return bio.getvalue()

def make_monthly_bar(monthly: pd.Series, title: str):
    """
    Clean monthly bar chart with short month labels (Jan..Dec).
    Expects a Series indexed by month-end timestamps (resample('M')).
    """
    if isinstance(monthly.index, pd.DatetimeIndex):
        labels = monthly.index.strftime("%b")
    else:
        labels = [str(x) for x in monthly.index]

    fig = plt.figure(figsize=(6.4, 3.0))
    ax = fig.add_subplot(111)
    ax.bar(range(len(monthly)), monthly.values)
    ax.set_xticks(range(len(monthly)))
    ax.set_xticklabels(labels, rotation=0)
    ax.set_title(title)
    ax.set_ylabel("kWh")
    ax.set_xlabel("")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)

def _escape(s: str) -> str:
    """Minimal XML escaping for Paragraph."""
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _summarize_weather_source(provenance: dict, site_info: dict) -> str:
    """
    Produce a short, plain-language summary of the weather source:
    '<Name>; <Period>; Location: <lat>, <lon>'
    """
    ws = provenance.get("weather_source", {}) or {}
    # If ws might be a dataclass dict, keep access via dict API
    name = ws.get("name") or "Weather source"
    details = ws.get("details") or {}

    # Determine period: TMY vs Year
    period_hint = (site_info or {}).get("period")
    is_tmy = ("TMY" in str(name).upper()) or (str(period_hint).lower().startswith("tmy") if period_hint else False)
    year = None

    # Try to infer the year from PVGIS hourly meta if present
    meta = details.get("meta") if isinstance(details, dict) else None
    if isinstance(meta, dict):
        inputs = meta.get("inputs") or {}
        # PVGIS hourly exposes startyear/endyear in meta.inputs
        year = inputs.get("startyear") or inputs.get("year")

    if not year and isinstance(details, dict):
        year = details.get("year")  # our adapters sometimes store {"year": 2021}

    if is_tmy:
        period_text = "TMY (8760 hrs)"
    else:
        if year:
            period_text = f"Year {year}"
        else:
            period_text = str(period_hint or "Calendar year")

    # Location
    lat = site_info.get("lat")
    lon = site_info.get("lon")
    loc_text = ""
    if lat is not None and lon is not None:
        try:
            loc_text = f"Location: {float(lat):.4f}, {float(lon):.4f}"
        except Exception:
            loc_text = f"Location: {lat}, {lon}"

    return f"{name}; {period_text}; {loc_text}".strip("; ")

# -----------------------
# footer on every page
# -----------------------
def _footer(canv: canvas.Canvas, doc):
    canv.saveState()
    footer_text = f"{TOOL_NAME}/{AUTHOR_NAME} — Page {doc.page}"
    canv.setFont("Helvetica", 8)
    canv.setFillColor(colors.grey)
    canv.drawString(36, 20, footer_text)
    canv.restoreState()

# -----------------------
# report writer
# -----------------------
def write_pdf(outpath: Path, site_info: dict, provenance: dict,
              cfg: dict, kpis: dict, monthly_series: pd.Series,
              sample_plot_png: bytes | None = None):

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Heading1C", parent=styles["Heading1"], alignment=1))
    styles.add(ParagraphStyle(name="Heading2S", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6))
    # Wrap long cells nicely; CJK wrap mode lets Paragraph break anywhere if needed
    styles.add(ParagraphStyle(name="TableCell", fontName="Helvetica", fontSize=9, leading=11, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="Mono", fontName="Courier", fontSize=8, leading=10))

    doc = SimpleDocTemplate(
        str(outpath),
        pagesize=A4,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )

    story = []

    # --- Title page ---
    story.append(Spacer(1, 120))
    story.append(Paragraph(f"<b>{TOOL_NAME}</b>", styles["Heading1C"]))
    story.append(Spacer(1, 24))
    story.append(Paragraph("Simulation Report", styles["Heading2S"]))
    story.append(Spacer(1, 48))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
    if "addr" in site_info:
        story.append(Paragraph(f"Site: { _escape(str(site_info['addr'])) }", styles["Normal"]))
    story.append(PageBreak())

    # --- Executive summary ---
    story.append(Paragraph("Executive Summary", styles["Heading1"]))
    story.append(Spacer(1, 12))
    kpi_table = Table(
        [
            ["Annual Energy (kWh)", f"{kpis.get('annual_kwh', '-')}"],
            ["Performance Ratio",   f"{kpis.get('performance_ratio', '-')}"],
            ["Capacity Factor",     f"{kpis.get('capacity_factor', '-')}"],
        ],
        colWidths=[220, 180],
        hAlign="LEFT",
    )
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1,18))

    # --- System configuration ---
    story.append(Paragraph("System & Models", styles["Heading1"]))
    sys_rows = [[Paragraph(_escape(str(k)), styles["TableCell"]),
                 Paragraph(_escape(str(v)), styles["TableCell"])] for k, v in cfg.items()]
    sys_table = Table([["Parameter", "Value"]] + sys_rows, colWidths=[220, 180], hAlign="LEFT")
    sys_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.lightgrey),
        ("GRID",(0,0),(-1,-1), 0.25, colors.grey),
        ("VALIGN",(0,0),(-1,-1), "TOP"),
        ("FONTNAME",(0,0),(-1,0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(sys_table)
    story.append(PageBreak())

    # --- Charts ---
    story.append(Paragraph("Monthly Energy", styles["Heading1"]))
    monthly_png = make_monthly_bar(monthly_series, "Monthly Energy (kWh)")
    story.append(RLImage(io.BytesIO(monthly_png), width=480, height=260))
    story.append(Spacer(1, 12))
    if sample_plot_png:
        story.append(Paragraph("Sample Time Series (First Week)", styles["Heading1"]))
        story.append(RLImage(io.BytesIO(sample_plot_png), width=480, height=260))
    story.append(PageBreak())

    # --- Provenance ---
    story.append(Paragraph("Provenance & Transformations", styles["Heading1"]))

    # Build concise, human-readable provenance rows
    prov_rows = []

    # 1) Weather source (summarized)
    ws_summary = _summarize_weather_source(provenance or {}, site_info or {})
    prov_rows.append([
        Paragraph("weather_source", styles["TableCell"]),
        Paragraph(_escape(ws_summary), styles["TableCell"])
    ])

    # 2) Derived variables summary (if any)
    derived = provenance.get("derived", {}) if isinstance(provenance, dict) else {}
    if isinstance(derived, dict) and derived:
        # Example: {"dni": "DIRINT", "dhi": "ERBS"} or flags
        parts = []
        for k, v in derived.items():
            parts.append(f"{k}: {v}")
        prov_rows.append([
            Paragraph("derived", styles["TableCell"]),
            Paragraph(_escape("; ".join(parts)), styles["TableCell"])
        ])

    # 3) Models (irradiance / temperature) in plain text
    irr = provenance.get("irradiance_model")
    if irr:
        prov_rows.append([Paragraph("irradiance_model", styles["TableCell"]),
                          Paragraph(_escape(str(irr)), styles["TableCell"])])
    temp = provenance.get("temperature_model")
    if temp:
        prov_rows.append([Paragraph("temperature_model", styles["TableCell"]),
                          Paragraph(_escape(str(temp)), styles["TableCell"])])
    # 4) Units normalization note
    prov_rows.append([
        Paragraph("units", styles["TableCell"]),
        Paragraph("Harmonized to: W/m², °C, m/s, Pa.", styles["TableCell"])
    ])

    prov_table = Table(
        [["Item", "Details"]] + prov_rows,
        colWidths=[160, 523-160],  # keep within page width (A4 with 36pt margins)
        hAlign="LEFT",
        repeatRows=1
    )
    prov_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.lightgrey),
        ("GRID",(0,0),(-1,-1), 0.25, colors.grey),
        ("VALIGN",(0,0),(-1,-1), "TOP"),
        ("FONTNAME",(0,0),(-1,0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(prov_table)
    story.append(Spacer(1,18))

    # --- Appendix ---
    story.append(Paragraph("Appendix: Configuration JSON", styles["Heading1"]))
    cfg_json = json.dumps(cfg, indent=2)
    story.append(Paragraph(_escape(cfg_json).replace("\n", "<br/>"), styles["Mono"]))

    # Build with footer
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return outpath

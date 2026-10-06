from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "sample_disruptions.csv"

st.set_page_config(page_title="Global Logistics Disruption Monitor", page_icon="🌍", layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1.6rem;padding-bottom:2.5rem}
[data-testid="stMetric"]{border:1px solid #2a3447;border-radius:14px;padding:12px 14px;background:#151d2e}
.pill{border:1px solid #2a3447;border-radius:999px;padding:4px 9px;display:inline-block;margin:0 6px 6px 0;font-size:.78rem}
</style>
""", unsafe_allow_html=True)

WEATHER = {
    0:"Clear",1:"Mainly clear",2:"Partly cloudy",3:"Overcast",45:"Fog",48:"Rime fog",
    51:"Light drizzle",53:"Drizzle",55:"Heavy drizzle",61:"Light rain",63:"Rain",
    65:"Heavy rain",66:"Freezing rain",67:"Heavy freezing rain",71:"Light snow",
    73:"Snow",75:"Heavy snow",77:"Snow grains",80:"Rain showers",81:"Rain showers",
    82:"Violent rain showers",85:"Snow showers",86:"Heavy snow showers",
    95:"Thunderstorm",96:"Thunderstorm + hail",99:"Severe thunderstorm + hail",
}

@st.cache_data
def load_sample() -> pd.DataFrame:
    return pd.read_csv(SAMPLE)

@st.cache_data(ttl=86400)
def geocode(place: str) -> dict[str, Any] | None:
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q":place,"format":"jsonv2","limit":1},
            headers={"User-Agent":"GlobalLogisticsDisruptionMonitor/1.0"},
            timeout=12,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return None
        x = rows[0]
        return {"name":x.get("display_name",place),"lat":float(x["lat"]),"lon":float(x["lon"])}
    except Exception:
        return None

@st.cache_data(ttl=900)
def weather_at(lat: float, lon: float) -> dict[str, Any]:
    params = {
        "latitude":lat,
        "longitude":lon,
        "current":"temperature_2m,precipitation,snowfall,weather_code,wind_speed_10m,wind_gusts_10m",
        "hourly":"precipitation_probability,precipitation,weather_code,wind_speed_10m,wind_gusts_10m",
        "forecast_days":2,
        "timezone":"auto",
    }
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=15)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=120)
def opensky_count(lat: float, lon: float, span: float = 2.0) -> int | None:
    try:
        r = requests.get(
            "https://opensky-network.org/api/states/all",
            params={
                "lamin":max(-90,lat-span),"lamax":min(90,lat+span),
                "lomin":max(-180,lon-span),"lomax":min(180,lon+span)
            },
            timeout=15,
        )
        r.raise_for_status()
        return len(r.json().get("states") or [])
    except Exception:
        return None

def weather_risk(payload: dict[str, Any]) -> tuple[int, str]:
    c = payload.get("current", {}) or {}
    code = int(c.get("weather_code",0) or 0)
    wind = float(c.get("wind_speed_10m",0) or 0)
    gust = float(c.get("wind_gusts_10m",0) or 0)
    precip = float(c.get("precipitation",0) or 0)
    snow = float(c.get("snowfall",0) or 0)
    score = 0
    reasons = []

    if code in {95,96,99}: score += 40; reasons.append("thunderstorm")
    elif code in {65,67,75,82,86}: score += 30; reasons.append("severe precipitation")
    elif code in {45,48,61,63,66,71,73,80,81,85}: score += 18; reasons.append("visibility/precipitation")

    if gust >= 70: score += 35; reasons.append("very strong gusts")
    elif gust >= 50: score += 25; reasons.append("strong gusts")
    elif gust >= 35: score += 12; reasons.append("moderate gusts")

    if wind >= 45: score += 20; reasons.append("strong sustained wind")
    elif wind >= 30: score += 10; reasons.append("moderate sustained wind")

    if precip >= 7: score += 20; reasons.append("heavy precipitation")
    elif precip >= 2: score += 10; reasons.append("precipitation")

    if snow >= 2: score += 20; reasons.append("snow accumulation")
    elif snow > 0: score += 10; reasons.append("snow")

    return min(score,100), ", ".join(reasons or ["no major weather trigger"])

def risk_label(score: int) -> str:
    return "High" if score >= 60 else "Medium" if score >= 30 else "Low"

def card(place: dict[str,Any], payload: dict[str,Any], aircraft: int | None) -> dict[str,Any]:
    c = payload.get("current", {}) or {}
    score, reasons = weather_risk(payload)
    return {
        "location":place["name"],
        "lat":place["lat"],
        "lon":place["lon"],
        "temperature_c":c.get("temperature_2m"),
        "condition":WEATHER.get(int(c.get("weather_code",0) or 0),"Unknown"),
        "wind_kmh":c.get("wind_speed_10m"),
        "gust_kmh":c.get("wind_gusts_10m"),
        "precip_mm":c.get("precipitation"),
        "risk":risk_label(score),
        "risk_score":score,
        "reasons":reasons,
        "aircraft_in_area":aircraft,
    }

def secret(key: str) -> str:
    try:
        return str(st.secrets.get(key,""))
    except Exception:
        return ""

def run_apify(actor_id: str, token: str, run_input: dict[str,Any], max_items: int) -> pd.DataFrame:
    actor = actor_id.replace("/","~")
    r = requests.post(
        f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
        headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},
        params={"clean":"true","format":"json","maxItems":max_items,"timeout":120},
        json=run_input,
        timeout=135,
    )
    r.raise_for_status()
    payload = r.json()
    items = payload if isinstance(payload,list) else payload.get("items",[])
    return pd.json_normalize(items)

st.title("🌍 Global Logistics Disruption Monitor")
st.caption("Weather, location and aviation-traffic context for logistics route risk assessment.")
st.markdown(
    '<span class="pill">Open-Meteo</span><span class="pill">Nominatim</span>'
    '<span class="pill">OpenSky</span><span class="pill">Apify-ready</span>'
    '<span class="pill">Streamlit</span>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Route")
    origin_text = st.text_input("Origin", "Lahore, Pakistan")
    destination_text = st.text_input("Destination", "Dubai, UAE")
    st.divider()
    severities = st.multiselect("Sample disruption severity", ["Low","Medium","High"], ["Medium","High"])
    types = st.multiselect("Sample disruption type", sorted(load_sample()["type"].unique()))

origin = geocode(origin_text)
destination = geocode(destination_text)
if not origin or not destination:
    st.error("Could not resolve one or both route locations.")
    st.stop()

midpoint = {
    "name":"Route midpoint",
    "lat":(origin["lat"]+destination["lat"])/2,
    "lon":(origin["lon"]+destination["lon"])/2,
}

with st.spinner("Reading live weather and aviation context…"):
    try:
        ow = weather_at(origin["lat"],origin["lon"])
        mw = weather_at(midpoint["lat"],midpoint["lon"])
        dw = weather_at(destination["lat"],destination["lon"])
    except Exception as exc:
        st.error(f"Weather service unavailable: {exc}")
        st.stop()
    oa = opensky_count(origin["lat"],origin["lon"])
    da = opensky_count(destination["lat"],destination["lon"])

cards = [card(origin,ow,oa),card(midpoint,mw,None),card(destination,dw,da)]
route_df = pd.DataFrame(cards)
route_score = int(round(route_df["risk_score"].mean()))
route_label = risk_label(route_score)

m1,m2,m3,m4 = st.columns(4)
m1.metric("Route weather risk",f"{route_label} · {route_score}/100")
m2.metric("Origin risk",f"{cards[0]['risk']} · {cards[0]['risk_score']}/100")
m3.metric("Destination risk",f"{cards[2]['risk']} · {cards[2]['risk_score']}/100")
known = [x for x in [oa,da] if isinstance(x,int)]
m4.metric("Aircraft context",sum(known) if known else "Unavailable")

t1,t2,t3,t4,t5 = st.tabs(["Route intelligence","Weather detail","Disruption feed","Apify collector","About"])

with t1:
    st.subheader("Route risk snapshot")
    st.map(pd.DataFrame([{"lat":origin["lat"],"lon":origin["lon"]},{"lat":destination["lat"],"lon":destination["lon"]}]))
    st.dataframe(
        route_df[["location","temperature_c","condition","wind_kmh","gust_kmh","precip_mm","risk","risk_score","reasons","aircraft_in_area"]],
        use_container_width=True,
        hide_index=True,
        column_config={"risk_score":st.column_config.ProgressColumn("Risk score",min_value=0,max_value=100,format="%d")},
    )
    if route_score >= 60:
        st.error("High weather disruption risk: consider schedule flexibility and alternative routing.")
    elif route_score >= 30:
        st.warning("Moderate weather disruption risk: monitor conditions before dispatch and during transit.")
    else:
        st.success("Low weather disruption signal from the current weather inputs.")

with t2:
    st.subheader("48-hour weather context")
    choice = st.selectbox("Location",["Origin","Midpoint","Destination"])
    payload = {"Origin":ow,"Midpoint":mw,"Destination":dw}[choice]
    h = payload.get("hourly",{}) or {}
    hourly = pd.DataFrame({
        "time":h.get("time",[]),
        "precipitation_probability":h.get("precipitation_probability",[]),
        "precipitation_mm":h.get("precipitation",[]),
        "wind_kmh":h.get("wind_speed_10m",[]),
        "gust_kmh":h.get("wind_gusts_10m",[]),
        "weather_code":h.get("weather_code",[]),
    })
    if not hourly.empty:
        hourly["time"] = pd.to_datetime(hourly["time"],errors="coerce")
        hourly["condition"] = hourly["weather_code"].map(lambda x: WEATHER.get(int(x),"Unknown") if pd.notna(x) else "")
        st.line_chart(hourly.set_index("time")[["precipitation_probability","wind_kmh","gust_kmh"]])
        st.dataframe(hourly.head(48),use_container_width=True,hide_index=True)

with t3:
    st.subheader("Sample logistics disruption feed")
    incidents = load_sample().copy()
    mask = incidents["severity"].isin(severities) if severities else pd.Series(True,index=incidents.index)
    if types:
        mask &= incidents["type"].isin(types)
    incidents = incidents.loc[mask]
    st.dataframe(incidents,use_container_width=True,hide_index=True,column_config={"source_url":st.column_config.LinkColumn("Source")})
    st.caption("Sample incidents are fictional portfolio data and are not live alerts.")
    st.download_button(
        "Download disruption watchlist (CSV)",
        incidents.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"logistics_disruption_watchlist_{date.today().isoformat()}.csv",
        mime="text/csv",
    )

with t4:
    st.subheader("Optional Apify logistics-news / alert collector")
    actor_id = st.text_input("Actor ID",value=secret("APIFY_ACTOR_ID"),placeholder="username/actor-name")
    token = st.text_input("Apify token",value=secret("APIFY_TOKEN"),type="password")
    urls = st.text_area("Alert/news URLs, one per line",height=110)
    max_items = st.number_input("Maximum returned items",1,200,25)
    actor_input = {"startUrls":[{"url":u.strip()} for u in urls.splitlines() if u.strip()],"maxCrawlPages":int(max_items)}
    with st.expander("Actor input preview"):
        st.code(json.dumps(actor_input,indent=2),language="json")
    if st.button("Run Apify collector",type="primary"):
        if not actor_id or not token:
            st.error("Actor ID and token are required.")
        elif not actor_input["startUrls"]:
            st.error("Add at least one URL.")
        else:
            try:
                with st.spinner("Running Actor…"):
                    live = run_apify(actor_id,token,actor_input,int(max_items))
                st.success(f"Collected {len(live)} item(s).")
                st.dataframe(live,use_container_width=True,hide_index=True)
                if not live.empty:
                    st.download_button(
                        "Download raw Apify results",
                        live.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"apify_disruption_results_{date.today().isoformat()}.csv",
                        mime="text/csv",
                    )
            except Exception as exc:
                st.error(f"Apify run failed: {exc}")

with t5:
    st.markdown("""
- **Nominatim / OpenStreetMap** resolves route endpoints.
- **Open-Meteo** supplies current conditions and short-term forecasts.
- **OpenSky Network** supplies anonymous aircraft-state context around endpoints when available.
- A transparent score combines severe weather, wind, gusts, precipitation and snowfall.
- **Apify** is optional for logistics notices/news pages not exposed through an API.
""")
    st.warning("Decision-support demo only. Verify official airport, port, carrier, NOTAM, road and emergency sources before operational action.")

st.divider()
st.caption("Portfolio demo by Muhammad Naveed · Logistics · Aviation · Supply Chain")

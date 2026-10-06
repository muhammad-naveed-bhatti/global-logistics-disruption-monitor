# Global Logistics Disruption Monitor

A Streamlit portfolio app for route-level logistics disruption awareness using public APIs and optional Apify web collection.

## Features

- Origin/destination geocoding
- Current weather risk at origin, midpoint and destination
- 48-hour weather context
- Transparent route-risk scoring
- Anonymous OpenSky aircraft-state count near route endpoints when available
- Sample disruption watchlist
- Optional Apify collector for public logistics alerts/news
- CSV export

## Public APIs

The app uses no-key public services where possible:

- **Open-Meteo** — weather forecast/current conditions
- **Nominatim / OpenStreetMap** — geocoding
- **OpenSky Network** — aviation state-vector context, subject to anonymous rate limits

## Optional Apify setup

In Streamlit Secrets:

```toml
APIFY_TOKEN = "your-token"
APIFY_ACTOR_ID = "username/actor-name"
```

Do not commit secrets.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

Deploy `app.py` from the repository root on Streamlit Community Cloud.

## Important

This portfolio demo is not a dispatch or flight-operations authority. Verify official airport, port, carrier, NOTAM, road and emergency sources before operational decisions.

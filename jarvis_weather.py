"""Weather via Open-Meteo (free, no API key). QOL pass, 2026-09-23.

Location: the place the user names ("weather in Lagos") via Open-Meteo's geocoding; otherwise
JARVIS_WEATHER_LOCATION (a place name); otherwise the PC's approximate location from its public IP
(ipapi.co), looked up once per run.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import date

log = logging.getLogger("jarvis.weather")

TIMEOUT_S = 10
_ip_location: dict | None = None

# WMO weather codes -> words (open-meteo.com/en/docs).
_CODES = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers",
    81: "showers", 82: "heavy showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.load(r)


def _geocode(name: str) -> dict | None:
    q = urllib.parse.urlencode({"name": name, "count": 1, "format": "json"})
    res = (_get(f"https://geocoding-api.open-meteo.com/v1/search?{q}").get("results") or [None])[0]
    if not res:
        return None
    label = ", ".join(p for p in (res.get("name"), res.get("admin1"), res.get("country")) if p)
    return {"lat": res["latitude"], "lon": res["longitude"], "label": label}


def _locate_by_ip() -> dict | None:
    global _ip_location
    if _ip_location is None:
        d = _get("https://ipapi.co/json/")
        if "latitude" in d:
            _ip_location = {"lat": d["latitude"], "lon": d["longitude"],
                            "label": ", ".join(p for p in (d.get("city"), d.get("country_name")) if p)}
    return _ip_location


def resolve_location(place: str = "") -> dict | None:
    place = (place or os.environ.get("JARVIS_WEATHER_LOCATION") or "").strip()
    return _geocode(place) if place else _locate_by_ip()


def _fmt_temp(c: float, unit: str) -> str:
    # words, not "°C": spoken aloud, and some TTS engines garble the symbol
    return f"{round(c * 9 / 5 + 32) if unit == 'f' else round(c)} degrees"


def weather_report(place: str = "", days: int = 1) -> str:
    unit = (os.environ.get("JARVIS_WEATHER_UNITS") or "c").strip().lower()[:1]
    try:
        days = max(1, min(int(days or 1), 7))
    except (TypeError, ValueError):
        days = 1
    try:
        loc = resolve_location(place)
        if not loc:
            return f"I couldn't find a place called {place!r}." if place else "I couldn't work out where you are."
        q = urllib.parse.urlencode({
            "latitude": loc["lat"], "longitude": loc["lon"], "timezone": "auto", "forecast_days": days,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        })
        d = _get(f"https://api.open-meteo.com/v1/forecast?{q}")
    except Exception as e:
        log.warning("Weather lookup failed: %s", e)
        return f"I couldn't get the weather right now ({type(e).__name__})."
    try:
        cur, daily = d.get("current") or {}, d.get("daily") or {}
        parts = [f"In {loc['label']} it's {_fmt_temp(cur.get('temperature_2m', 0), unit)} and "
                 f"{_CODES.get(cur.get('weather_code'), 'unsettled')}, feels like "
                 f"{_fmt_temp(cur.get('apparent_temperature', 0), unit)}, wind {round(cur.get('wind_speed_10m', 0))} km/h."]
        for i, day in enumerate((daily.get("time") or [])[:days]):
            name = "Today" if i == 0 else ("Tomorrow" if i == 1 else date.fromisoformat(day).strftime("%A"))
            rain = (daily.get("precipitation_probability_max") or [None] * days)[i]
            parts.append(f"{name}: {_CODES.get(daily['weather_code'][i], 'mixed')}, "
                         f"high {_fmt_temp(daily['temperature_2m_max'][i], unit)}, low {_fmt_temp(daily['temperature_2m_min'][i], unit)}"
                         + (f", {rain}% chance of rain." if rain is not None else "."))
        return " ".join(parts)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
        log.warning("Unexpected weather response: %r", e)  # partial/changed API answer
        return "The weather service sent back something I couldn't read."


if __name__ == "__main__":
    print(weather_report())

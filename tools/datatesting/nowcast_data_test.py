#!/usr/bin/env python3
"""
Nowcast data test harness — validates the nowcast-port branch's data layer
OUTSIDE the app, against the same live APIs, using line-for-line ports of the
Swift algorithms.

What it replicates (with Swift source citations in each function):
  NEW (feature on):
    - Storm Approach, improved mode  (StormApproachService.swift, weatherAroundMeImprovementsEnabled ON)
    - Storm Approach, legacy mode    (same service, improvements OFF)
    - Next Hour narration            (RadarService.buildNextHourSummaryFromMinutely15 / buildNextHourSummary)
  OLD (feature off — what the app showed before the port):
    - Wind-inferred "nearest precipitation" (RadarService.findNearestPrecipitation:
      direction = opposite of surface wind — the meteorologically-wrong method
      Storm Approach replaces)
    - Current status line (RadarService.determineCurrentStatus)

Known, deliberate deviations from the app (documented, equivalence argued):
  1. Time indexing for the legacy RadarService path uses timeformat=unixtime
     instead of local ISO strings + DateParser. The app's DateParser is
     separately unit-tested; index selection ("first step after now") is
     mathematically identical either way. All other query parameters match.
  2. WeatherKit paths (minute-by-minute narration, conditions overlay) cannot
     run outside an entitled app bundle. The narration tested here is the
     Open-Meteo minutely_15 path — the exact code path the app uses outside
     WeatherKit minute coverage, and the same summarizer function
     (buildNextHourSummary) the WeatherKit path feeds. Rows note this.
  3. "Saved cities" don't exist outside the app; the 3 nearest bundled cities
     between 40 and 250 km stand in for them (app filter: >1 km, <=250 km,
     nearest 5 — StormApproachService.swift step 2).

Output (per run, into <output-root>/run-YYYYMMDD-HHMMSSZ/):
  results.csv  — long format: data_name, app_location, new_value, old_value + context/checks
  cities.csv   — one wide row per city with every numeric metric for sorting/graphing
  summary.json — run metadata, counts, consistency statistics
  run.log      — per-city progress and errors

Usage:
  python3 tools/datatesting/nowcast_data_test.py [--cities 100] [--output-root DIR] [--repo DIR]
"""

import argparse
import concurrent.futures
import csv
import json
import math
import os
import random
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone  # datetime also used by nws_observation

sys_path_dir = os.path.dirname(os.path.abspath(__file__))
if sys_path_dir not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path_dir)
try:
    import weatherkit_rest as WK
    WEATHERKIT_ENABLED = WK.is_configured()
except Exception:  # noqa: BLE001 — harness must run without the key
    WK, WEATHERKIT_ENABLED = None, False

# Countries where the app uses the WeatherKit minute path
# (RadarService.weatherKitMinuteForecastCountries) -> ISO codes for REST.
WK_MINUTE_COUNTRIES = {"United States": "US", "Canada": "CA",
                       "United Kingdom": "GB", "Ireland": "IE",
                       "Australia": "AU", "New Zealand": "NZ"}

# Prefer IPv4. macOS + urllib can hang in the TLS handshake when a host's
# IPv6 path is broken; sorting A records first avoids the stall.
_real_getaddrinfo = socket.getaddrinfo


def _ipv4_first_getaddrinfo(*args, **kwargs):
    results = _real_getaddrinfo(*args, **kwargs)
    return sorted(results, key=lambda r: 0 if r[0] == socket.AF_INET else 1)


socket.getaddrinfo = _ipv4_first_getaddrinfo

USER_AGENT = "FastWeather/1.5 (weatherfast.online)"  # matches the app's requests
NWS_USER_AGENT = "FastWeather-datatest (kelly@theideaplace.net)"

# Candidate repo locations, in priority order, for Secrets.swift + city data.
REPO_CANDIDATES = [
    # repo copy lives at tools/datatesting/ → repo root is three levels up
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    os.path.expanduser("~/Documents/GitHub/FastWeather"),
]

# ---------------------------------------------------------------------------
# Constants ported from StormApproachService.swift (cited by line area)
# ---------------------------------------------------------------------------

ACTIVE_THRESHOLD_MM = 0.1       # StormApproachService: activeThresholdMm
# Proposed fix (spec under verification): WeatherKit minute data only counts as
# precipitation at or above this rate. Chosen from the two instrumented runs:
# radar phantoms measured 0.05-0.07 mm/h; real storms 3.6-10.4 mm/h.
WK_INTENSITY_FLOOR_MMHR = 0.2
HORIZON_STEPS = 8               # 8 x 15 min = 2 h look-ahead
MAX_CITY_KM = 250.0             # saved-city classification range
MAX_CITIES = 5
PLACE_RADIUS_KM = 80.0          # bundled towns within ~50 mi
MAX_PLACES = 12

IMPROVED_BEARINGS = [b * 22.5 for b in range(16)]     # 16 spokes
IMPROVED_RADII = [20.0, 40.0, 70.0]
LEGACY_BEARINGS = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]
LEGACY_RADII = [30.0, 60.0]

EARTH_RADIUS_KM = 6371.0        # GeoMath.earthRadiusKm

CARDINALS = ["North", "Northeast", "East", "Southeast",
             "South", "Southwest", "West", "Northwest"]

# WeatherCode.description (Weather.swift) — exact strings, used by
# determineCurrentStatus for the old status line.
WEATHER_CODE_DESC = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

THUNDER_CODES = {95, 96, 99}

# StormApproachService.precipType(forCode:)
SNOW_CODES = {71, 73, 75, 77, 85, 86}
MIXED_CODES = {56, 57, 66, 67}
RAIN_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}


# ---------------------------------------------------------------------------
# GeoMath — 1:1 port of the GeoMath enum in StormApproachService.swift
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def destination(lat, lon, bearing_deg, distance_km):
    angular = distance_km / EARTH_RADIUS_KM
    theta = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1) * math.cos(angular) +
                     math.cos(lat1) * math.sin(angular) * math.cos(theta))
    lon2 = lon1 + math.atan2(math.sin(theta) * math.sin(angular) * math.cos(lat1),
                             math.cos(angular) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)


def bearing_deg(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return normalize_degrees(math.degrees(math.atan2(y, x)))


def normalize_degrees(deg):
    m = math.fmod(deg, 360.0)
    return m + 360.0 if m < 0 else m


def angular_difference(a, b):
    diff = math.fmod(abs(normalize_degrees(a) - normalize_degrees(b)), 360.0)
    return 360.0 - diff if diff > 180.0 else diff


def cardinal_name(bearing):
    # GeoMath.cardinalName — Int((deg/45).rounded()) % 8, Swift .rounded() is
    # half-away-from-zero; deg is non-negative here so round-half-up matches.
    idx = int(math.floor(normalize_degrees(bearing) / 45.0 + 0.5)) % 8
    return CARDINALS[idx]


# RadarService.getCardinalDirection(_ degrees: Int) — same formula, Int input.
def rs_cardinal(degrees_int):
    idx = int(math.floor(degrees_int / 45.0 + 0.5)) % 8
    return CARDINALS[idx]


# RadarService.getOppositeDirection — precipitation comes FROM opposite of wind dir.
def rs_opposite_direction(degrees_int):
    return rs_cardinal((degrees_int + 180) % 360).lower()


# ---------------------------------------------------------------------------
# Intensity / phrasing helpers (PrecipIntensity + narration extensions)
# ---------------------------------------------------------------------------

def intensity_rank(mm_per_hour):
    # PrecipIntensity.init(mmPerHour:)
    if mm_per_hour < 0.1: return 0    # none
    if mm_per_hour < 2.5: return 1    # light
    if mm_per_hour < 10:  return 2    # moderate
    if mm_per_hour < 50:  return 3    # heavy
    return 4                          # very heavy


INTENSITY_ADJ = {0: "no", 1: "light", 2: "moderate", 3: "heavy", 4: "very heavy"}


def cap_first(s):
    return s[:1].upper() + s[1:] if s else s


def format_distance_mi(km):
    # DistanceUnit.miles: convert = km*0.621371, then .rounded(), format "%.0f mi"
    return "%.0f mi" % round(km * 0.621371)


def format_speed_mph(kmh):
    # WindSpeedUnit.mph convert + Int(rounded())
    return "%d mph" % int(round(kmh * 0.621371))


def minutes_phrase(m):
    # Shared minutesPhrase (StormApproach narration + buildNextHourSummary)
    if m <= 0:
        return "now"
    if m < 60:
        return "about %d minutes" % m
    h, mm = divmod(m, 60)
    h_str = "%d hour%s" % (h, "" if h == 1 else "s")
    return "about %s" % h_str if mm == 0 else "about %s %d minutes" % (h_str, mm)


def format_precipitation_intensity(mm):
    # RadarService.formatPrecipitationIntensity
    if mm < 0.1: return "None"
    if mm < 2.5: return "Light precipitation"
    if mm < 10:  return "Moderate precipitation"
    if mm < 50:  return "Heavy precipitation"
    return "Very heavy precipitation"


THUNDERSTORM_NOTE = ("Thunderstorms are in your area's forecast, but no measurable rain is"
                     " reaching your location or nearby towns right now. Scattered storms can do this —"
                     " conditions may change quickly.")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

API_CALLS = {"count": 0, "customer_fallbacks": 0}


def http_get_json(url, user_agent=USER_AGENT, retries=5, timeout=45):
    """GET with retries. If the paid customer endpoint keeps failing at the
    connection/TLS layer, fall back to the free endpoint for that request —
    same API, same data; only rate limits differ. Fallbacks are counted and
    reported in summary.json."""
    last_err = None
    for attempt in range(retries):
        attempt_url = url
        if (attempt >= 2 and "customer-api.open-meteo.com" in url):
            attempt_url = (url.replace("customer-api.open-meteo.com", "api.open-meteo.com")
                              .replace("&apikey=", "&_unused_key="))
        try:
            req = urllib.request.Request(attempt_url, headers={"User-Agent": user_agent})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                API_CALLS["count"] += 1
                if attempt_url is not url:
                    API_CALLS["customer_fallbacks"] += 1
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 — log and retry
            last_err = e
            time.sleep(min(10.0, 1.5 * (attempt + 1)) + random.uniform(0, 0.5))
    raise RuntimeError("GET failed after %d tries: %s (%s)" % (retries, url[:120], last_err))


def find_repo():
    for cand in REPO_CANDIDATES:
        if os.path.isfile(os.path.join(cand, "CityData", "us-cities-cached.json")):
            return cand
    sys.exit("Cannot locate the FastWeather repo (needed for CityData). Use --repo.")


def load_api_key(repo):
    key = os.environ.get("OPEN_METEO_API_KEY")
    if key:
        return key
    secrets = os.path.join(repo, "iOS", "FastWeather", "Services", "Secrets.swift")
    if os.path.isfile(secrets):
        text = open(secrets).read()
        m = re.search(r'openMeteoAPIKey:\s*String\?\s*=\s*"([^"]+)"', text)
        if m:
            return m.group(1)
    return None


def om_base(key):
    # Same endpoint selection as the app (customer endpoint when key present).
    return ("https://customer-api.open-meteo.com/v1/forecast" if key
            else "https://api.open-meteo.com/v1/forecast")


def om_url(base, params, key):
    if key:
        params = dict(params, apikey=key)
    return base + "?" + urllib.parse.urlencode(params)


# ---------------------------------------------------------------------------
# City pools
# ---------------------------------------------------------------------------

def load_city_pools(repo):
    us = json.load(open(os.path.join(repo, "CityData", "us-cities-cached.json")))
    intl = json.load(open(os.path.join(repo, "CityData", "international-cities-cached.json")))
    all_cities = []
    for state, cities in us.items():
        for c in cities:
            all_cities.append(dict(name=c["name"], region=c.get("state") or state,
                                   country=c.get("country") or "United States",
                                   lat=c["lat"], lon=c["lon"]))
    for country, cities in intl.items():
        for c in cities:
            all_cities.append(dict(name=c["name"], region=c.get("state") or "",
                                   country=c.get("country") or country,
                                   lat=c["lat"], lon=c["lon"]))
    return all_cities


BASELINE_CITIES = [
    # Geographic + climate spread; includes dry-likely and international
    # (international exercises the 2-hour narration phrasing path).
    ("Madison", "Wisconsin", "United States"), ("Seattle", "Washington", "United States"),
    ("Phoenix", "Arizona", "United States"), ("Miami", "Florida", "United States"),
    ("New Orleans", "Louisiana", "United States"), ("Denver", "Colorado", "United States"),
    ("Boston", "Massachusetts", "United States"), ("Anchorage", "Alaska", "United States"),
    ("Honolulu", "Hawaii", "United States"), ("Kansas City", "Missouri", "United States"),
    ("Portland", "Oregon", "United States"), ("Atlanta", "Georgia", "United States"),
    ("Minneapolis", "Minnesota", "United States"), ("Houston", "Texas", "United States"),
    ("Salt Lake City", "Utah", "United States"), ("Buffalo", "New York", "United States"),
    ("London", "", "United Kingdom"), ("Tokyo", "", "Japan"), ("Mumbai", "", "India"),
    ("Singapore", "", "Singapore"), ("Sydney", "", "Australia"), ("Reykjavik", "", "Iceland"),
    ("Oslo", "", "Norway"), ("Buenos Aires", "", "Argentina"), ("Nairobi", "", "Kenya"),
    ("Cairo", "", "Egypt"), ("Vancouver", "", "Canada"), ("Mexico City", "", "Mexico"),
    ("Amsterdam", "", "Netherlands"), ("Zurich", "", "Switzerland"),
]


def match_city(pool, name, region, country):
    for c in pool:
        if c["name"] == name and (not region or c["region"] == region) and c["country"] == country:
            return c
    for c in pool:
        if c["name"] == name and c["country"] == country:
            return c
    return None


def polygon_centroid(coords):
    lats = [pt[1] for ring in coords for pt in ring]
    lons = [pt[0] for ring in coords for pt in ring]
    return sum(lats) / len(lats), sum(lons) / len(lons)


INTERESTING_ALERT_EVENTS = {
    "Severe Thunderstorm Warning", "Tornado Warning", "Tornado Watch",
    "Severe Thunderstorm Watch", "Flash Flood Warning", "Flood Warning",
    "Winter Storm Warning", "Blizzard Warning", "Winter Weather Advisory",
    "High Wind Warning", "Special Weather Statement",
}


def find_interesting_cities(pool, want, log):
    """Automated version of quickradar's hand-curated storm-chase list:
    NWS active alerts + an Open-Meteo current-precipitation scan."""
    chosen, seen_coords = [], []

    def far_enough(lat, lon, min_km=100.0):
        return all(haversine_km(lat, lon, a, b) > min_km for a, b in seen_coords)

    def nearest_pool_city(lat, lon, max_km=80.0):
        best, best_d = None, max_km
        for c in pool:
            if abs(c["lat"] - lat) > 1.5 or abs(c["lon"] - lon) > 2.0:
                continue
            d = haversine_km(lat, lon, c["lat"], c["lon"])
            if d < best_d:
                best, best_d = c, d
        return best

    # 1) NWS active alerts (the app's own alert source), most severe first.
    try:
        data = http_get_json(
            "https://api.weather.gov/alerts/active?status=actual&message_type=alert",
            user_agent=NWS_USER_AGENT)
        feats = [f for f in data.get("features", [])
                 if f.get("properties", {}).get("event") in INTERESTING_ALERT_EVENTS]
        severity_rank = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}
        feats.sort(key=lambda f: severity_rank.get(f["properties"].get("severity"), 4))
        for f in feats:
            geom = f.get("geometry")
            if not geom:
                continue
            if geom["type"] == "Polygon":
                lat, lon = polygon_centroid(geom["coordinates"])
            elif geom["type"] == "MultiPolygon":
                lat, lon = polygon_centroid(geom["coordinates"][0])
            else:
                continue
            if not far_enough(lat, lon):
                continue
            city = nearest_pool_city(lat, lon)
            if city:
                chosen.append(dict(city, reason="nws-alert: %s" % f["properties"]["event"]))
                seen_coords.append((city["lat"], city["lon"]))
            if len(chosen) >= want * 2 // 3:
                break
        log("Finder: %d cities from NWS active alerts" % len(chosen))
    except Exception as e:  # noqa: BLE001
        log("Finder: NWS alerts unavailable (%s) — relying on precipitation scan" % e)

    # 2) Open-Meteo current-precipitation scan over a broad candidate set.
    candidates, seen_names = [], set()
    by_region = {}
    for c in pool:
        by_region.setdefault((c["country"], c["region"]), []).append(c)
    for (_country, _region), cities in by_region.items():
        for c in cities[:2]:  # cache files are ordered biggest-first
            k = (c["name"], c["country"])
            if k not in seen_names:
                seen_names.add(k)
                candidates.append(c)
    key = load_api_key(find_repo())
    base = om_base(key)
    scan_hits = []
    for i in range(0, len(candidates), 50):
        chunk = candidates[i:i + 50]
        url = om_url(base, {
            "latitude": ",".join("%.4f" % c["lat"] for c in chunk),
            "longitude": ",".join("%.4f" % c["lon"] for c in chunk),
            "current": "precipitation,weather_code",
        }, key)
        try:
            data = http_get_json(url)
        except Exception as e:  # noqa: BLE001
            log("Finder: scan chunk failed (%s)" % e)
            continue
        results = data if isinstance(data, list) else [data]
        for c, r in zip(chunk, results):
            cur = r.get("current", {})
            precip = cur.get("precipitation") or 0
            code = cur.get("weather_code")
            if precip >= 0.1 or code in THUNDER_CODES or code in {65, 67, 75, 82, 86}:
                scan_hits.append((precip, dict(c, reason="precip-scan: %.1fmm code=%s" % (precip, code))))
    scan_hits.sort(key=lambda t: -t[0])
    for _p, c in scan_hits:
        if len(chosen) >= want:
            break
        if far_enough(c["lat"], c["lon"]):
            chosen.append(c)
            seen_coords.append((c["lat"], c["lon"]))
    log("Finder: %d cities after precipitation scan" % len(chosen))
    return chosen


# ---------------------------------------------------------------------------
# NWS observation referee (US only) — nearest station's current conditions,
# used to adjudicate WeatherKit-vs-Open-Meteo seam disagreements about "now".
# ---------------------------------------------------------------------------

NWS_PRECIP_WORDS = ("rain", "drizzle", "snow", "thunder", "shower", "sleet",
                    "hail", "storm", "wintry")


def nws_observation(lat, lon):
    """Latest observation from the nearest NWS station, or None.
    Three requests: points -> stations -> latest observation."""
    try:
        pt = http_get_json("https://api.weather.gov/points/%.4f,%.4f" % (lat, lon),
                           user_agent=NWS_USER_AGENT, retries=2, timeout=20)
        stations_url = pt["properties"]["observationStations"]
        st = http_get_json(stations_url, user_agent=NWS_USER_AGENT, retries=2, timeout=20)
        feats = st.get("features") or []
        if not feats:
            return None
        sid = feats[0]["properties"]["stationIdentifier"]
        obs = http_get_json("https://api.weather.gov/stations/%s/observations/latest" % sid,
                            user_agent=NWS_USER_AGENT, retries=2, timeout=20)
        prop = obs["properties"]
        text = prop.get("textDescription") or ""
        ts = prop.get("timestamp") or ""
        age_min = ""
        try:
            obs_epoch = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            age_min = int((time.time() - obs_epoch) / 60)
        except Exception:  # noqa: BLE001
            pass
        return dict(station=sid, text=text, timestamp=ts, age_min=age_min,
                    precip_last_hr=(prop.get("precipitationLastHour") or {}).get("value"),
                    raining=any(w in text.lower() for w in NWS_PRECIP_WORDS))
    except Exception:  # noqa: BLE001 — referee is best-effort
        return None


def build_city_list(pool, total, log, baseline_only=False):
    interesting = [] if baseline_only else find_interesting_cities(
        pool, want=max(1, total * 6 // 10), log=log)
    cities = list(interesting)
    have = {(c["name"], c["country"]) for c in cities}
    for name, region, country in BASELINE_CITIES:
        if len(cities) >= total:
            break
        c = match_city(pool, name, region, country)
        if c and (c["name"], c["country"]) not in have:
            cities.append(dict(c, reason="baseline"))
            have.add((c["name"], c["country"]))
    # Top up from the pool with a deterministic-ish spread if still short.
    rng = random.Random(42)
    shuffled = pool[:]
    rng.shuffle(shuffled)
    for c in shuffled:
        if len(cities) >= total:
            break
        if (c["name"], c["country"]) not in have:
            cities.append(dict(c, reason="fill-random"))
            have.add((c["name"], c["country"]))
    return cities[:total]


# ---------------------------------------------------------------------------
# Storm Approach — port of StormApproachService.fetchStormApproach + analyse
# ---------------------------------------------------------------------------

def ring_samples(lat, lon, improved):
    bearings = IMPROVED_BEARINGS if improved else LEGACY_BEARINGS
    radii = IMPROVED_RADII if improved else LEGACY_RADII
    samples = [dict(lat=lat, lon=lon, bearing=0.0, distance_km=0.0)]
    for r in radii:                      # Swift: for radius in radiiKm { for bearing in bearings
        for b in bearings:
            plat, plon = destination(lat, lon, b, r)
            samples.append(dict(lat=plat, lon=plon, bearing=b, distance_km=r))
    return samples


def extract_series(forecast, now_epoch):
    # StormApproachService.extractSeries: first index at-or-after now, else 0.
    m15 = forecast.get("minutely_15") or {}
    times, precip = m15.get("time"), m15.get("precipitation")
    if not times or precip is None:
        return []
    now_index = next((i for i, t in enumerate(times) if t >= now_epoch), 0)
    return [(p if p is not None else 0.0) for p in precip[now_index:]]


def centroid_motion(samples, series):
    # StormApproachService.estimateMotion — frames at steps 0 and 2 (30 min apart).
    offsets = [(s["distance_km"] * math.sin(math.radians(s["bearing"])),
                s["distance_km"] * math.cos(math.radians(s["bearing"]))) for s in samples]

    def centroid(step):
        sw = se = sn = 0.0
        for i, serie in enumerate(series):
            if step >= len(serie):
                continue
            w = serie[step]
            if w < ACTIVE_THRESHOLD_MM:
                continue
            sw += w
            se += w * offsets[i][0]
            sn += w * offsets[i][1]
        if sw <= ACTIVE_THRESHOLD_MM:
            return None
        return se / sw, sn / sw

    c0, c1 = centroid(0), centroid(2)
    if c0 is None or c1 is None:
        return None
    dt = 0.5
    ve, vn = (c1[0] - c0[0]) / dt, (c1[1] - c0[1]) / dt
    speed = math.hypot(ve, vn)
    if speed < 3 or speed > 130:
        return None
    return dict(toward=normalize_degrees(math.degrees(math.atan2(ve, vn))), speed_kmh=speed)


def steering_wind(base, key, lat, lon):
    # StormApproachService.fetchSteeringWind — 850/700/500 hPa vector mean.
    url = om_url(base, {
        "latitude": "%.6f" % lat, "longitude": "%.6f" % lon,
        "hourly": ("wind_speed_850hPa,wind_direction_850hPa,wind_speed_700hPa,"
                   "wind_direction_700hPa,wind_speed_500hPa,wind_direction_500hPa"),
        "timeformat": "unixtime", "timezone": "GMT", "forecast_days": "1",
    }, key)
    try:
        data = http_get_json(url)
    except Exception:  # noqa: BLE001 — app treats steering as best-effort
        return None
    hourly = data.get("hourly") or {}
    times = hourly.get("time")
    if not times:
        return None
    now = time.time()
    idx = next((i for i, t in enumerate(times) if t >= now), None)
    idx = max(0, idx - 1) if idx is not None else 0
    se = sn = 0.0
    count = 0
    for lvl in ("850hPa", "700hPa", "500hPa"):
        speeds = hourly.get("wind_speed_" + lvl)
        dirs = hourly.get("wind_direction_" + lvl)
        if not speeds or not dirs or idx >= len(speeds) or idx >= len(dirs):
            continue
        speed, direction = speeds[idx], dirs[idx]
        if speed is None or direction is None:
            continue
        toward = math.radians(math.fmod(direction + 180, 360))
        se += speed * math.sin(toward)
        sn += speed * math.cos(toward)
        count += 1
    if count == 0:
        return None
    me, mn = se / count, sn / count
    speed = math.hypot(me, mn)
    if speed < 1:
        return None
    return dict(toward=normalize_degrees(math.degrees(math.atan2(me, mn))), speed_kmh=speed)


def precip_type(code):
    if code is None: return "unknown"
    if code in SNOW_CODES: return "snow"
    if code in MIXED_CODES: return "mixed"
    if code in RAIN_CODES: return "rain"
    return "unknown"


PRECIP_TYPE_NOUN = {"rain": "rain", "snow": "snow", "mixed": "wintry mix", "unknown": "precipitation"}


def classify_point(serie, code, kind):
    # classifyCity / classifyPlace shared shape (trend + arrival + intensity).
    now_mm = serie[0] if serie else 0.0
    if now_mm >= ACTIVE_THRESHOLD_MM:
        return dict(trend="rainingNow", arrival=None, mm=now_mm, type=precip_type(code))
    for step in range(1, HORIZON_STEPS + 1):
        if step < len(serie) and serie[step] >= ACTIVE_THRESHOLD_MM:
            return dict(trend="arriving", arrival=step * 15, mm=serie[step], type=precip_type(code))
    return dict(trend="clear", arrival=None, mm=0.0, type="unknown")


def analyse_storm_approach(samples, sample_forecasts, now_epoch, improved, steering,
                           town_points, town_forecasts, saved_points, saved_forecasts,
                           displayed_condition_code):
    """Port of StormApproachService.analyse (nowcast-port version, including the
    re-pointed thunderstorm gate)."""
    series = [extract_series(f, now_epoch) for f in sample_forecasts]
    centre = series[0] if series else []
    here_mm = centre[0] if centre else 0.0
    raining_here = here_mm >= ACTIVE_THRESHOLD_MM

    arrival = None
    if not raining_here:
        for step in range(1, HORIZON_STEPS + 1):
            if step < len(centre) and centre[step] >= ACTIVE_THRESHOLD_MM:
                arrival = step * 15
                break

    nearest = None  # (distance_km, bearing, mm)
    for i, s in enumerate(samples):
        if i == 0:
            continue
        mm = series[i][0] if series[i] else 0.0
        if mm < ACTIVE_THRESHOLD_MM:
            continue
        if (nearest is None or s["distance_km"] < nearest[0] or
                (s["distance_km"] == nearest[0] and mm > nearest[2])):
            nearest = (s["distance_km"], s["bearing"], mm)

    centroid = centroid_motion(samples, series)
    if improved:
        if steering:
            motion = steering
            if centroid:
                diff = angular_difference(steering["toward"], centroid["toward"])
                confidence = "high" if diff < 45 else ("medium" if diff < 90 else "low")
            else:
                confidence = "medium"
        elif centroid:
            motion, confidence = centroid, "low"
        else:
            motion, confidence = None, "low"
    else:
        motion, confidence = centroid, "high"   # legacy never hedges

    if raining_here:
        situation = "rainingHere"
    elif arrival is not None:
        situation = "approaching"
    elif nearest is not None:
        situation = "nearbyNotApproaching"
    else:
        situation = "clear"

    # nowcast-port gate: keys off the DISPLAYED condition; suppressed when the
    # caller can't supply it and the WeatherKit overlay is on. Outside the app
    # the displayed (WeatherKit-informed) condition is unknowable, so this
    # mirrors the suppress branch; the raw Open-Meteo answer is reported
    # separately for phantom-detection.
    centre_code_raw = (sample_forecasts[0].get("current") or {}).get("weather_code") if sample_forecasts else None
    if displayed_condition_code is not None:
        thunder = displayed_condition_code in THUNDER_CODES
    else:
        thunder = False  # weatherKitConditionsEnabled defaults ON -> suppressed

    towns = []
    for pt, f in zip(town_points, town_forecasts):
        serie = extract_series(f, now_epoch)
        code = (f.get("current") or {}).get("weather_code")
        c = classify_point(serie, code, "place")
        towns.append(dict(c, name=pt["name"], distance_km=pt["distance_km"], bearing=pt["bearing"],
                          type=precip_type(code)))

    saved = []
    for pt, f in zip(saved_points, saved_forecasts):
        serie = extract_series(f, now_epoch)
        code = (f.get("current") or {}).get("weather_code")
        c = classify_point(serie, code, "city")
        if c["trend"] == "clear" and motion:
            if angular_difference(motion["toward"], pt["bearing"]) < 60:
                c = dict(c, trend="trackingToward")
        saved.append(dict(c, name=pt["name"]))

    return dict(situation=situation, here_mm=here_mm, arrival=arrival, nearest=nearest,
                motion=motion, centroid=centroid, confidence=confidence, improved=improved,
                thunder=thunder, centre_code_raw=centre_code_raw, towns=towns, saved=saved,
                ring_radius_km=max(IMPROVED_RADII if improved else LEGACY_RADII),
                ring_max_mm=max((s[0] for s in series[1:] if s), default=0.0),
                ring_active=sum(1 for s in series[1:] if s and s[0] >= ACTIVE_THRESHOLD_MM))


def storm_headline(sa):
    # Port of StormApproach.headline (legacy + improved variants).
    def motion_clause_legacy(m):
        return (" The band is moving %s at about %s." %
                (cardinal_name(m["toward"]).lower(), format_speed_mph(m["speed_kmh"])))

    def motion_verb_improved(m, conf):
        d = cardinal_name(m["toward"]).lower()
        if conf == "high":
            return "moving %s at about %s" % (d, format_speed_mph(m["speed_kmh"]))
        if conf == "medium":
            return "moving generally %s" % d
        return "moving %s, though its track is uncertain" % d

    situation, motion = sa["situation"], sa["motion"]
    here_adj = INTENSITY_ADJ[intensity_rank(sa["here_mm"] * 4)]
    nearest = sa["nearest"]
    near_adj = INTENSITY_ADJ[intensity_rank(nearest[2] * 4)] if nearest else "no"

    if situation == "rainingHere":
        s = "%s precipitation at your location now." % cap_first(here_adj)
        if motion:
            if sa["improved"]:
                s += " The band is %s." % motion_verb_improved(motion, sa["confidence"])
            else:
                s += motion_clause_legacy(motion)
        return s
    if situation == "approaching":
        direction = cardinal_name(nearest[1]).lower() if nearest else "nearby"
        s = "%s precipitation to the %s" % (cap_first(near_adj), direction)
        if nearest:
            s += ", about %s away" % format_distance_mi(nearest[0])
        if sa["arrival"] is not None:
            s += ", reaching you in %s" % minutes_phrase(sa["arrival"])
        s += "."
        if motion:
            if sa["improved"]:
                s += " %s." % cap_first(motion_verb_improved(motion, sa["confidence"]))
            else:
                s += motion_clause_legacy(motion)
        return s
    if situation == "nearbyNotApproaching":
        direction = cardinal_name(nearest[1]).lower() if nearest else "nearby"
        s = "%s precipitation to the %s" % (cap_first(near_adj), direction)
        if nearest:
            s += ", about %s away" % format_distance_mi(nearest[0])
        s += ", but it is not heading your way right now."
        if sa["thunder"]:
            s += " " + THUNDERSTORM_NOTE
        return s
    if sa["thunder"]:
        return THUNDERSTORM_NOTE
    return ("No precipitation within %s of you, now or in the next 2 hours."
            % format_distance_mi(sa["ring_radius_km"]))


def place_lines(sa):
    # Port of StormApproach.placeLines — active/arriving only, nearest 5.
    lines = []
    for t in sa["towns"]:
        if t["trend"] not in ("rainingNow", "arriving"):
            continue
        if len(lines) >= 5:
            break
        direction = cardinal_name(t["bearing"]).lower()
        dist = format_distance_mi(t["distance_km"])
        noun = PRECIP_TYPE_NOUN[t["type"]] if sa["improved"] else "precipitation"
        if t["trend"] == "rainingNow":
            rank = intensity_rank(t["mm"] * 4)
            lead = ("%s %s" % (cap_first(INTENSITY_ADJ[rank]), noun)) if rank >= 2 else cap_first(noun)
            lines.append("%s over %s, %s %s." % (lead, t["name"], dist, direction))
        else:
            when = minutes_phrase(t["arrival"]) if t["arrival"] is not None else "soon"
            lines.append(("%s reaching %s in %s, %s %s." % (cap_first(noun), t["name"], when, dist, direction))
                         if sa["improved"] else
                         ("Reaching %s in %s, %s %s." % (t["name"], when, dist, direction)))
    return lines


def city_lines(sa):
    lines = []
    for c in sa["saved"]:
        if c["trend"] == "rainingNow":
            lines.append("Precipitation now at %s." % c["name"])
        elif c["trend"] == "arriving":
            when = minutes_phrase(c["arrival"]) if c["arrival"] is not None else "soon"
            lines.append("Precipitation reaching %s in %s." % (c["name"], when))
        elif c["trend"] == "trackingToward":
            lines.append("Storm tracking toward %s." % c["name"])
        else:
            lines.append("Clear at %s." % c["name"])
    return lines


# ---------------------------------------------------------------------------
# Legacy RadarService path (OLD behavior) + Next Hour narration (NEW)
# ---------------------------------------------------------------------------

def fetch_legacy_nowcast(base, key, lat, lon):
    # RadarService.fetchOpenMeteoNowcast query — identical params except
    # unixtime/GMT for index math (deviation #1 in the module docstring).
    url = om_url(base, {
        "latitude": "%.6f" % lat, "longitude": "%.6f" % lon,
        "minutely_15": "precipitation",
        "hourly": "precipitation,weather_code,wind_direction_10m,wind_speed_10m",
        "current": "precipitation,weather_code,wind_direction_10m",
        "timeformat": "unixtime", "timezone": "GMT",
        "forecast_days": "1",
    }, key)
    return http_get_json(url)


def determine_current_status(current):
    precip = current.get("precipitation")
    if precip is not None and precip > 0:
        code = current.get("weather_code")
        desc = WEATHER_CODE_DESC.get(code, "Precipitation") if code is not None else "Precipitation"
        return "%s at your location" % desc
    return "No precipitation at your location"


def find_nearest_precipitation_old(forecast, now_epoch):
    # RadarService.findNearestPrecipitation — the OLD wind-inferred block.
    m15 = forecast.get("minutely_15") or {}
    times, precip = m15.get("time"), m15.get("precipitation")
    if not times or precip is None:
        return None
    hourly = forecast.get("hourly") or {}
    wind_dirs = hourly.get("wind_direction_10m") or []
    wind_speeds = hourly.get("wind_speed_10m") or []

    current_index = next((i for i, t in enumerate(times) if t > now_epoch), 0)
    for index in range(current_index, len(precip)):
        p = precip[index]
        if p is not None and p > 0.01:
            minutes_away = (index - current_index) * 15
            if minutes_away == 0:
                return None  # already precipitating
            intensity = format_precipitation_intensity(p)
            arrival = ("%d minutes" % minutes_away if minutes_away < 60 else
                       "Approximately %d hour%s" % (minutes_away // 60,
                                                    "" if minutes_away // 60 == 1 else "s"))
            hour_index = min(index // 4, max(0, len(wind_dirs) - 1))  # Swift: index/4 (absolute)
            wind_dir = wind_dirs[hour_index] if hour_index < len(wind_dirs) and wind_dirs[hour_index] is not None else 0
            from_direction = rs_opposite_direction(int(wind_dir))
            wind_kmh = wind_speeds[hour_index] if hour_index < len(wind_speeds) and wind_speeds[hour_index] is not None else 0
            wind_mph = max(5, wind_kmh * 0.621371) if wind_kmh > 0 else 15
            return dict(distance_miles=int(minutes_away * wind_mph / 60.0),
                        direction=from_direction,
                        type=intensity, intensity=intensity,
                        movement_direction=rs_cardinal(int(wind_dir)),
                        speed_mph=int(wind_mph), arrival=arrival,
                        minutes_away=minutes_away, wind_dir_deg=int(wind_dir))
    return None


def build_next_hour_summary(samples, window_minutes):
    # RadarService.buildNextHourSummary — exact port (locked by NextHourSummaryTests).
    if len(samples) <= 1:
        return None
    window_label = "hour" if window_minutes <= 60 else "%d hours" % (window_minutes // 60)
    now_active = samples[0][2] if samples else False
    if now_active:
        end = next((s for s in samples if s[0] > 0 and not s[2]), None)
        if end:
            return "Precipitation now, easing off in %s." % minutes_phrase(end[0])
        return "Precipitation now, continuing through the next %s." % window_label
    onset = next((s for s in samples if s[2]), None)
    if onset is None:
        return "No precipitation expected in the next %s." % window_label
    onset_min = onset[0]
    after = [s for s in samples if s[0] >= onset_min]
    end_min = next((s[0] for s in after if not s[2]), None)
    active_stretch = []
    for s in after:
        if not s[2]:
            break
        active_stretch.append(s)
    peak = max(active_stretch, key=lambda s: s[1], default=None)
    peak_rank = intensity_rank(peak[1]) if peak else 0
    out = "Precipitation starting in %s" % minutes_phrase(onset_min)
    if end_min is not None:
        out += ", lasting about %d minutes" % (end_min - onset_min)
    else:
        out += ", continuing through the next %s" % window_label
    out += "."
    if peak_rank >= 2 and peak and peak[0] != onset_min:
        out += " Heaviest %s from now." % minutes_phrase(peak[0])
    return out


def next_hour_from_minutely15(forecast, now_epoch):
    # RadarService.buildNextHourSummaryFromMinutely15 — (first > now) - 1, steps 0..8.
    m15 = forecast.get("minutely_15") or {}
    times, precip = m15.get("time"), m15.get("precipitation")
    if not times or precip is None:
        return None, None
    current_index = 0
    for i, t in enumerate(times):
        if t > now_epoch:
            current_index = max(0, i - 1)
            break
    samples = []
    onset_min = None
    for step in range(0, 9):
        idx = current_index + step
        if idx >= len(precip):
            break
        mm15 = precip[idx] if precip[idx] is not None else 0
        active = mm15 >= 0.1
        if active and onset_min is None and step > 0:
            onset_min = step * 15
        samples.append((step * 15, mm15 * 4, active))
    return build_next_hour_summary(samples, 120), onset_min


# ---------------------------------------------------------------------------
# Per-city evaluation
# ---------------------------------------------------------------------------

def nearby_towns(pool, lat, lon, exclude_keys):
    # StormApproachService.nearbyPlaces — window prefilter, >1km, <=80km, nearest 12.
    lat_window = PLACE_RADIUS_KM / 111.0
    lon_window = PLACE_RADIUS_KM / (111.0 * max(0.2, math.cos(math.radians(lat))))
    out = []
    for c in pool:
        if abs(c["lat"] - lat) > lat_window or abs(c["lon"] - lon) > lon_window:
            continue
        d = haversine_km(lat, lon, c["lat"], c["lon"])
        if d <= 1.0 or d > PLACE_RADIUS_KM:
            continue
        key = "%.2f,%.2f" % (c["lat"], c["lon"])
        if key in exclude_keys:
            continue
        out.append(dict(name=c["name"], lat=c["lat"], lon=c["lon"], distance_km=d,
                        bearing=bearing_deg(lat, lon, c["lat"], c["lon"])))
    out.sort(key=lambda t: t["distance_km"])
    return out[:MAX_PLACES]


def pseudo_saved_cities(pool, lat, lon):
    # Stand-ins for the user's saved cities (deviation #3): 3 nearest 40–250 km.
    out = []
    for c in pool:
        if abs(c["lat"] - lat) > 3.0 or abs(c["lon"] - lon) > 4.0:
            continue
        d = haversine_km(lat, lon, c["lat"], c["lon"])
        if 40.0 <= d <= MAX_CITY_KM:
            out.append(dict(name=c["name"], lat=c["lat"], lon=c["lon"], distance_km=d,
                            bearing=bearing_deg(lat, lon, c["lat"], c["lon"])))
    out.sort(key=lambda t: t["distance_km"])
    return out[:3]


def evaluate_city(city, pool, base, key, log):
    lat, lon = city["lat"], city["lon"]
    now_epoch = time.time()

    saved = pseudo_saved_cities(pool, lat, lon)
    saved_keys = {"%.2f,%.2f" % (s["lat"], s["lon"]) for s in saved}
    towns = nearby_towns(pool, lat, lon, saved_keys)

    imp_samples = ring_samples(lat, lon, improved=True)
    leg_samples = ring_samples(lat, lon, improved=False)

    # One multi-coordinate request, same params as the app's fetchForecasts.
    coords = ([(s["lat"], s["lon"]) for s in imp_samples] +
              [(s["lat"], s["lon"]) for s in leg_samples[1:]] +   # centre shared
              [(t["lat"], t["lon"]) for t in towns] +
              [(s["lat"], s["lon"]) for s in saved])
    url = om_url(base, {
        "latitude": ",".join("%.6f" % c[0] for c in coords),
        "longitude": ",".join("%.6f" % c[1] for c in coords),
        "minutely_15": "precipitation",
        "current": "precipitation,weather_code",
        "timeformat": "unixtime", "timezone": "GMT", "forecast_days": "2",
    }, key)
    forecasts = http_get_json(url)
    if not isinstance(forecasts, list):
        forecasts = [forecasts]
    if len(forecasts) != len(coords):
        raise RuntimeError("expected %d forecasts, got %d" % (len(coords), len(forecasts)))

    n_imp = len(imp_samples)
    n_leg = len(leg_samples) - 1
    imp_fx = forecasts[:n_imp]
    leg_fx = [forecasts[0]] + forecasts[n_imp:n_imp + n_leg]
    town_fx = forecasts[n_imp + n_leg:n_imp + n_leg + len(towns)]
    saved_fx = forecasts[n_imp + n_leg + len(towns):]

    steering = steering_wind(base, key, lat, lon)

    sa_new = analyse_storm_approach(imp_samples, imp_fx, now_epoch, True, steering,
                                    towns, town_fx, saved, saved_fx, None)
    sa_leg = analyse_storm_approach(leg_samples, leg_fx, now_epoch, False, None,
                                    towns, town_fx, saved, saved_fx, None)

    legacy = fetch_legacy_nowcast(base, key, lat, lon)
    old_nearest = find_nearest_precipitation_old(legacy, now_epoch)
    old_status = determine_current_status(legacy.get("current") or {})
    narration, narration_onset = next_hour_from_minutely15(legacy, now_epoch)

    # WeatherKit centre nowcast (REST) — what the app's US narration path sees.
    # Instruments the WK-vs-OM seam the in-app bug reports came from.
    wk = None
    iso = WK_MINUTE_COUNTRIES.get(city["country"])
    if WEATHERKIT_ENABLED and iso:
        try:
            wk = WK.centre_nowcast(lat, lon, country=iso)
        except Exception as e:  # noqa: BLE001 — best-effort, like steering
            log("  wk fetch failed for %s: %s" % (city["name"], e))
    # NWS observation referee (US only) — adjudicates "raining now" disputes.
    obs = nws_observation(lat, lon) if city["country"] == "United States" else None

    wk_narration = None
    if wk and wk["has_next_hour"]:
        # Mirror RadarService.fetchWeatherKitNowcast summarySamples: 61 minutes,
        # active[0] from the condition-based effectiveIsPrecip.
        samples = [(m[0], m[1], (wk["is_precipitating"] if i == 0 else m[2]))
                   for i, m in enumerate(wk["minutes"][:61])]
        wk_narration = build_next_hour_summary(samples, 60)

    # --- Fix simulation: floor applied at the shared source (RadarService's
    # WK path), so BOTH the narration and Storm Approach's centre read the same
    # floored WeatherKit view. Storm Approach centre falls back to Open-Meteo
    # beyond WK's ~60-minute horizon (preserves the 2-hour promise).
    wk_fixed_narration = None
    fixed_centre = None   # dict(now_active, active_hour, arrival_min, source)
    if wk and wk["has_next_hour"]:
        floor = WK_INTENSITY_FLOOR_MMHR
        now_active_fixed = wk["is_precipitating"] and wk["intensity_now"] >= floor
        fsamples = [(m[0], m[1], (now_active_fixed if i == 0 else m[1] >= floor))
                    for i, m in enumerate(wk["minutes"][:61])]
        wk_fixed_narration = build_next_hour_summary(fsamples, 60)
        arrival = next((m[0] for m in fsamples if m[0] > 0 and m[2]), None)
        if arrival is None and not now_active_fixed:
            # WK horizon dry: check Open-Meteo for the 60-120 min window only.
            for step in range(5, HORIZON_STEPS + 1):   # 75..120 min
                serie = extract_series({"minutely_15": legacy.get("minutely_15")}, now_epoch)
                if step < len(serie) and serie[step] >= ACTIVE_THRESHOLD_MM:
                    arrival = step * 15
                    break
        fixed_centre = dict(now_active=now_active_fixed,
                            active_hour=now_active_fixed or any(m[2] for m in fsamples),
                            arrival_min=arrival, source="weatherkit+floor")

    return dict(sa_new=sa_new, sa_leg=sa_leg, old_nearest=old_nearest, old_status=old_status,
                narration=narration, narration_onset=narration_onset,
                towns_count=len(towns), saved_names=[s["name"] for s in saved],
                legacy_current=legacy.get("current") or {},
                wk=wk, wk_narration=wk_narration, obs=obs,
                wk_fixed_narration=wk_fixed_narration, fixed_centre=fixed_centre)


# ---------------------------------------------------------------------------
# Row + check construction
# ---------------------------------------------------------------------------

CARDINAL_DEG = {name.lower(): i * 45.0 for i, name in enumerate(CARDINALS)}


def build_rows(city, ev):
    """results.csv rows: data_name / app_location / new_value / old_value + checks."""
    rows = []
    sa, leg = ev["sa_new"], ev["sa_leg"]
    ctx = dict(city=city["name"], region=city["region"], country=city["country"],
               latitude=round(city["lat"], 4), longitude=round(city["lon"], 4),
               selection_reason=city.get("reason", ""))

    def row(name, location, new, old, flags, check, result, details=""):
        rows.append(dict(ctx, data_name=name, app_location=location,
                         new_value=new, old_value=old, flags_compared=flags,
                         check=check, check_result=result, details=details))

    # 1. Direction of nearest precipitation: ring-sampled vs wind-inferred.
    new_dir = cardinal_name(sa["nearest"][1]).lower() if sa["nearest"] else "(none nearby)"
    old_dir = ev["old_nearest"]["direction"] if ev["old_nearest"] else "(none in forecast)"
    if sa["nearest"] and ev["old_nearest"]:
        delta = angular_difference(sa["nearest"][1], CARDINAL_DEG[ev["old_nearest"]["direction"]])
        result = "ok" if delta <= 67.5 else "mismatch"
        details = "ring bearing %.0f° vs wind-inferred %s (Δ %.0f°) — the old method guesses from surface wind and is expected to be wrong at times; mismatches here justify the feature" % (
            sa["nearest"][1], ev["old_nearest"]["direction"], delta)
    elif sa["nearest"] is None and ev["old_nearest"] is None:
        result, details = "ok", "both methods agree: nothing nearby"
    else:
        result = "review"
        details = "one method sees precipitation, the other does not (spatial ring vs single-point forecast — not necessarily an error)"
    row("precip_direction", "Weather Around Me > Storm Approach card",
        ("%s (%s, %s away)" % (new_dir, INTENSITY_ADJ[intensity_rank(sa["nearest"][2] * 4)],
                               format_distance_mi(sa["nearest"][0])) if sa["nearest"] else new_dir),
        ("from the %s, ~%d mi (movement %s at %d mph)" % (
            old_dir, ev["old_nearest"]["distance_miles"], ev["old_nearest"]["movement_direction"],
            ev["old_nearest"]["speed_mph"]) if ev["old_nearest"] else old_dir),
        "stormApproachEnabled on vs off (old wind-inferred block)",
        "direction agreement (new ring vs old wind guess)", result, details)

    # 2. Storm motion: steering+confidence vs centroid-only.
    new_motion = ("toward %s at %.0f km/h (confidence %s)" % (
        cardinal_name(sa["motion"]["toward"]), sa["motion"]["speed_kmh"], sa["confidence"])
        if sa["motion"] else "(no motion estimate)")
    old_motion = ("toward %s at %.0f km/h (stated crisply)" % (
        cardinal_name(leg["motion"]["toward"]), leg["motion"]["speed_kmh"])
        if leg["motion"] else "(no motion estimate)")
    if sa["motion"] and sa["centroid"]:
        delta = angular_difference(sa["motion"]["toward"], sa["centroid"]["toward"])
        result = "ok" if delta < 90 else "review"
        details = "steering %.0f° vs centroid %.0f° (Δ %.0f°) → confidence %s" % (
            sa["motion"]["toward"], sa["centroid"]["toward"], delta, sa["confidence"])
    else:
        result, details = "n_a", "not enough precipitation mass or steering data for a cross-check"
    row("storm_motion", "Weather Around Me > Storm Approach card",
        new_motion, old_motion,
        "weatherAroundMeImprovementsEnabled on vs off",
        "steering vs centroid agreement", result, details)

    # 3. Headline text, improved vs legacy.
    row("storm_headline", "Weather Around Me > Storm Approach card",
        storm_headline(sa), storm_headline(leg),
        "weatherAroundMeImprovementsEnabled on vs off",
        "wording review (hedging should appear only in new, and only at medium/low confidence)",
        "ok" if (sa["confidence"] == "high" or not sa["motion"] or
                 "generally" in storm_headline(sa) or "uncertain" in storm_headline(sa) or
                 sa["situation"] in ("clear", "nearbyNotApproaching")) else "review",
        "situation=%s confidence=%s" % (sa["situation"], sa["confidence"]))

    # 4. Arrival estimate: centre-series onset vs old wind/distance arithmetic.
    new_arr = ("%d min" % sa["arrival"]) if sa["arrival"] is not None else (
        "(raining now)" if sa["situation"] == "rainingHere" else "(none within 2 h)")
    old_arr = ev["old_nearest"]["arrival"] if ev["old_nearest"] else "(none in forecast)"
    if sa["arrival"] is not None and ev["old_nearest"]:
        delta = abs(sa["arrival"] - ev["old_nearest"]["minutes_away"])
        result = "ok" if delta <= 15 else ("review" if delta <= 30 else "mismatch")
        details = "new %d min vs old %d min (Δ %d) — both derive from the same minutely_15 series; >15 min apart needs a look" % (
            sa["arrival"], ev["old_nearest"]["minutes_away"], delta)
    else:
        result, details = "n_a", ""
    row("arrival_at_location", "Storm Approach card / old Nearest Precipitation block",
        new_arr, old_arr, "stormApproachEnabled on vs off",
        "arrival agreement (same source data)", result, details)

    # 5. Next Hour narration vs old status line.
    narr = ev["narration"] or "(no sentence — insufficient data)"
    if ev["narration"]:
        says_dry = ev["narration"].startswith("No precipitation")
        centre_wet_or_coming = sa["situation"] in ("rainingHere", "approaching")
        if says_dry and centre_wet_or_coming:
            result = "mismatch"
            details = "narration says dry but Storm Approach centre sees precipitation (situation=%s) — same-city surfaces must agree" % sa["situation"]
        elif (not says_dry) and sa["situation"] == "clear" and ev["narration_onset"] is not None:
            result = "review"
            details = "narration expects precipitation but Storm Approach ring+centre is clear — check thresholds (narration >now-1 index vs storm >=now index)"
        else:
            result, details = "ok", ""
    else:
        result, details = "n_a", ""
    row("next_hour_summary", "City Detail > Next Hour card; Next Hour screen (first card)",
        narr, ev["old_status"] + " (old summary card lead)",
        "nextHourNarrationEnabled / nowcastRefinementsEnabled on vs off",
        "narration vs Storm Approach same-city agreement", result, details)

    # 6. Nearby towns layer.
    pl_new, pl_leg = place_lines(sa), place_lines(leg)
    row("nearby_towns", "Weather Around Me > Storm Approach card > Nearby towns",
        " | ".join(pl_new) or "(no towns with active/arriving precipitation)",
        " | ".join(pl_leg) or "(feature off: not shown; legacy wording: %s)" % ("none" if not pl_leg else ""),
        "weatherAroundMeImprovementsEnabled (rain/snow nouns) on vs off",
        "type labels only where measurable precipitation exists",
        "ok" if all(t["mm"] >= ACTIVE_THRESHOLD_MM for t in sa["towns"]
                    if t["trend"] in ("rainingNow", "arriving")) else "mismatch",
        "%d towns sampled, %d active/arriving" % (
            ev["towns_count"], sum(1 for t in sa["towns"] if t["trend"] in ("rainingNow", "arriving"))))

    # 7. Saved-city impacts (pseudo-saved stand-ins).
    row("saved_city_impacts", "Weather Around Me > Storm Approach card > Your saved cities",
        " | ".join(city_lines(sa)) or "(no nearby cities)",
        "(feature off: not shown)",
        "stormApproachEnabled on vs off",
        "informational (pseudo-saved stand-ins: %s)" % ", ".join(ev["saved_names"]) if ev["saved_names"] else "informational",
        "n_a", "app uses the user's real saved cities; harness uses 3 nearest 40-250 km")

    # 8b (inserted as its own row below). WK-vs-OM centre seam.
    if ev.get("wk") is not None:
        wk = ev["wk"]
        wk_active_hour = wk["is_precipitating"] or any(m[2] for m in wk["minutes"][:61])
        om_active_hour = sa["situation"] == "rainingHere" or (
            sa["arrival"] is not None and sa["arrival"] <= 60)
        if wk_active_hour == om_active_hour:
            seam_result, seam_details = "ok", ""
        else:
            seam_result = "mismatch"
            seam_details = ("WeatherKit (radar-informed) and Open-Meteo (model) disagree about "
                            "precipitation at this location within the hour — in the app the Next Hour "
                            "narration would contradict Storm Approach here (the east-Madison bug class)")
        # Referee: the nearest NWS station can adjudicate the "now" component.
        obs = ev.get("obs")
        if obs is not None:
            wk_now = wk["is_precipitating"]
            om_now = sa["situation"] == "rainingHere"
            if obs["raining"] == wk_now and obs["raining"] == om_now:
                verdict = "observation agrees with both"
            elif obs["raining"] == wk_now:
                verdict = "observation supports WeatherKit"
            elif obs["raining"] == om_now:
                verdict = "observation supports Open-Meteo"
            else:
                verdict = "observation contradicts both"
            seam_details = (seam_details + " | " if seam_details else "") +                 "NWS %s says '%s' (%s min old) -> %s" % (
                    obs["station"], obs["text"], obs["age_min"], verdict)
        row("centre_precip_source_seam",
            "Next Hour narration (WeatherKit) vs Storm Approach centre (Open-Meteo)",
            ev.get("wk_narration") or ("WK current: %s, intensity %.2f mm/h, no next-hour minutes"
                                       % (wk["condition"], wk["intensity_now"])),
            ev["narration"] or "(no Open-Meteo narration)",
            "same city, two sources — the seam the in-app harness could not test before",
            "WK-vs-OM precipitation-within-the-hour agreement", seam_result, seam_details)

    # 8c. Fix simulation: what the app would say after the proposed fix
    # (WeatherKit authority at the centre + intensity floor at the shared
    # source), classified against the current behavior and the NWS referee.
    if ev.get("fixed_centre") is not None:
        wk = ev["wk"]
        cur_wet = wk["is_precipitating"] or any(m[2] for m in wk["minutes"][:61])
        fix_wet = ev["fixed_centre"]["active_hour"]
        obs = ev.get("obs")
        if cur_wet and not fix_wet:
            if obs is not None and not obs["raining"]:
                fix_class, fix_result = "phantom suppressed (observation confirms dry)", "ok"
            elif obs is not None and obs["raining"]:
                fix_class, fix_result = "OVERSUPPRESSED - floor removed rain the station reports", "mismatch"
            else:
                fix_class, fix_result = "low-intensity claim suppressed (no referee)", "review"
        elif cur_wet and fix_wet:
            fix_class, fix_result = "real precipitation preserved above floor", "ok"
        elif not cur_wet and not fix_wet:
            fix_class, fix_result = "dry, unchanged", "ok"
        else:
            fix_class, fix_result = "unexpected: fix wetter than current", "review"
        # After the fix the seam closes BY CONSTRUCTION for WK cities (both
        # cards read the same floored data); what remains meaningful is the
        # single story's accuracy vs the referee, captured in fix_class.
        row("intensity_floor_fix_sim",
            "simulated: RadarService WK path with 0.2 mm/h floor; Storm Approach centre reads it",
            ev.get("wk_fixed_narration") or "(no WK next-hour data)",
            ev.get("wk_narration") or "(no WK next-hour data)",
            "proposed fix ON vs current nowcast-port behavior",
            fix_class, fix_result,
            "fixed arrival=%s src=%s" % (ev["fixed_centre"]["arrival_min"],
                                         ev["fixed_centre"]["source"]))

    # 8. Thunderstorm reconciliation (phantom detection).
    code = sa["centre_code_raw"]
    phantom = code in THUNDER_CODES and sa["here_mm"] < ACTIVE_THRESHOLD_MM
    row("thunderstorm_reconciliation", "Storm Approach card (note under headline)",
        "suppressed unless the DISPLAYED (WeatherKit-informed) condition says thunderstorm — not knowable outside the app",
        ("note shown (old gate: raw Open-Meteo code %s)" % code) if phantom else "(no note)",
        "port change: displayedConditionCode gate vs raw weather_code gate",
        "phantom-thunderstorm candidate (code %s, centre %.2f mm/15min)" % (code, sa["here_mm"]),
        "review" if phantom else "ok",
        "phantom candidates are where the old gate would contradict the app's WeatherKit-informed condition — verify these in-app" if phantom else "")

    return rows


def build_city_row(city, ev):
    sa, leg = ev["sa_new"], ev["sa_leg"]
    old = ev["old_nearest"]
    cur = ev["legacy_current"]
    dir_delta = ""
    if sa["nearest"] and old:
        dir_delta = "%.0f" % angular_difference(sa["nearest"][1], CARDINAL_DEG[old["direction"]])
    steer_cent = ""
    if sa["motion"] and sa["centroid"]:
        steer_cent = "%.0f" % angular_difference(sa["motion"]["toward"], sa["centroid"]["toward"])
    return dict(
        city=city["name"], region=city["region"], country=city["country"],
        latitude=round(city["lat"], 4), longitude=round(city["lon"], 4),
        selection_reason=city.get("reason", ""),
        weather_code=cur.get("weather_code"),
        weather_desc=WEATHER_CODE_DESC.get(cur.get("weather_code"), ""),
        current_precip_mm=cur.get("precipitation"),
        situation_new=sa["situation"], situation_legacy=leg["situation"],
        centre_mm15=round(sa["here_mm"], 3),
        ring_max_mm15_new=round(sa["ring_max_mm"], 3), ring_active_pts_new=sa["ring_active"],
        ring_max_mm15_legacy=round(leg["ring_max_mm"], 3), ring_active_pts_legacy=leg["ring_active"],
        nearest_km_new=round(sa["nearest"][0], 1) if sa["nearest"] else "",
        nearest_bearing_new=round(sa["nearest"][1]) if sa["nearest"] else "",
        nearest_compass_new=cardinal_name(sa["nearest"][1]) if sa["nearest"] else "",
        old_from_compass=old["direction"] if old else "",
        old_distance_mi=old["distance_miles"] if old else "",
        old_wind_dir_deg=old["wind_dir_deg"] if old else "",
        direction_delta_deg=dir_delta,
        arrival_min_new=sa["arrival"] if sa["arrival"] is not None else "",
        arrival_min_old=old["minutes_away"] if old else "",
        steering_toward_deg=round(sa["motion"]["toward"]) if sa["motion"] and sa["improved"] else "",
        steering_kmh=round(sa["motion"]["speed_kmh"], 1) if sa["motion"] and sa["improved"] else "",
        centroid_toward_deg=round(sa["centroid"]["toward"]) if sa["centroid"] else "",
        centroid_kmh=round(sa["centroid"]["speed_kmh"], 1) if sa["centroid"] else "",
        steering_centroid_delta_deg=steer_cent,
        confidence=sa["confidence"],
        phantom_thunderstorm=(cur.get("weather_code") in THUNDER_CODES and
                              sa["here_mm"] < ACTIVE_THRESHOLD_MM),
        towns_sampled=ev["towns_count"],
        towns_active=sum(1 for t in sa["towns"] if t["trend"] in ("rainingNow", "arriving")),
        narration=ev["narration"] or "",
        wk_available=ev.get("wk") is not None,
        wk_condition=(ev["wk"]["condition"] if ev.get("wk") else ""),
        wk_intensity_now=(ev["wk"]["intensity_now"] if ev.get("wk") else ""),
        wk_active_minutes=(sum(1 for m in ev["wk"]["minutes"] if m[2]) if ev.get("wk") else ""),
        wk_narration=ev.get("wk_narration") or "",
        nws_station=(ev["obs"]["station"] if ev.get("obs") else ""),
        nws_obs_text=(ev["obs"]["text"] if ev.get("obs") else ""),
        nws_obs_age_min=(ev["obs"]["age_min"] if ev.get("obs") else ""),
        nws_obs_raining=(ev["obs"]["raining"] if ev.get("obs") else ""),
        headline_new=storm_headline(sa),
        headline_legacy=storm_headline(leg),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--cities", type=int, default=100)
    ap.add_argument("--output-root", default=None,
                    help="default: <script dir>/datatesting when run from RadarData, else ./datatesting")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--baseline", action="store_true",
                    help="skip the interesting-weather finder (quiet-day baseline sample)")
    args = ap.parse_args()

    if args.repo:
        REPO_CANDIDATES.insert(0, args.repo)
    repo = find_repo()
    key = load_api_key(repo)
    base = om_base(key)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_root = args.output_root or os.path.join(script_dir, "datatesting")
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%SZ")
    run_dir = os.path.join(out_root, run_id)
    os.makedirs(run_dir, exist_ok=True)

    log_path = os.path.join(run_dir, "run.log")
    log_file = open(log_path, "a")

    def log(msg):
        line = "[%s] %s" % (datetime.now(timezone.utc).strftime("%H:%M:%SZ"), msg)
        print(line, flush=True)
        log_file.write(line + "\n")
        log_file.flush()

    log("Nowcast data test %s" % run_id)
    log("Repo: %s | API tier: %s" % (repo, "paid (customer endpoint)" if key else "free"))
    pool = load_city_pools(repo)
    log("City pool: %d bundled locations" % len(pool))

    cities = build_city_list(pool, args.cities, log, baseline_only=args.baseline)
    log("Testing %d cities (%d interesting, %d baseline/fill)" % (
        len(cities),
        sum(1 for c in cities if not c.get("reason", "").startswith(("baseline", "fill"))),
        sum(1 for c in cities if c.get("reason", "").startswith(("baseline", "fill")))))

    all_rows, city_rows, errors = [], [], []

    def work(city):
        try:
            time.sleep(random.uniform(0, 0.8))  # stagger concurrent TLS handshakes
            ev = evaluate_city(city, pool, base, key, log)
            return city, ev, None
        except Exception as e:  # noqa: BLE001
            return city, None, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool_exec:
        futures = [pool_exec.submit(work, c) for c in cities]
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            city, ev, err = fut.result()
            done += 1
            if err:
                errors.append(dict(city=city["name"], country=city["country"], error=err))
                log("(%d/%d) %s, %s — ERROR: %s" % (done, len(cities), city["name"], city["country"], err))
                continue
            all_rows.extend(build_rows(city, ev))
            city_rows.append(build_city_row(city, ev))
            log("(%d/%d) %s, %s — %s / conf %s" % (
                done, len(cities), city["name"], city["country"],
                ev["sa_new"]["situation"], ev["sa_new"]["confidence"]))

    # results.csv — the requested long format.
    results_path = os.path.join(run_dir, "results.csv")
    fields = ["city", "region", "country", "latitude", "longitude", "selection_reason",
              "data_name", "app_location", "new_value", "old_value",
              "flags_compared", "check", "check_result", "details"]
    with open(results_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_rows)

    # cities.csv — wide per-city metrics.
    cities_path = os.path.join(run_dir, "cities.csv")
    if city_rows:
        with open(cities_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(city_rows[0].keys()))
            w.writeheader()
            w.writerows(city_rows)

    checks = {}
    for r in all_rows:
        checks.setdefault(r["data_name"], {}).setdefault(r["check_result"], 0)
        checks[r["data_name"]][r["check_result"]] += 1
    summary = dict(
        run_id=run_id, generated_utc=datetime.now(timezone.utc).isoformat(),
        branch="nowcast-port", api_tier="paid" if key else "free",
        api_calls=API_CALLS["count"],
        customer_endpoint_fallbacks=API_CALLS["customer_fallbacks"],
        cities_requested=args.cities,
        cities_completed=len(city_rows), errors=errors,
        phantom_thunderstorm_count=sum(1 for c in city_rows if c["phantom_thunderstorm"]),
        baseline_mode=args.baseline,
        weatherkit_enabled=WEATHERKIT_ENABLED,
        weatherkit_cities_sampled=sum(1 for c in city_rows if c["wk_available"]),
        wk_om_seam_mismatches=sum(1 for r in all_rows
                                  if r["data_name"] == "centre_precip_source_seam"
                                  and r["check_result"] == "mismatch"),
        nws_referee_cities=sum(1 for c in city_rows if c["nws_station"]),
        fix_sim={cls: sum(1 for r in all_rows
                          if r["data_name"] == "intensity_floor_fix_sim"
                          and r["check"] == cls)
                 for cls in ("phantom suppressed (observation confirms dry)",
                             "OVERSUPPRESSED - floor removed rain the station reports",
                             "low-intensity claim suppressed (no referee)",
                             "real precipitation preserved above floor",
                             "dry, unchanged")},
        referee_verdicts={v: sum(1 for r in all_rows
                                 if r["data_name"] == "centre_precip_source_seam"
                                 and v in r["details"])
                          for v in ("observation agrees with both",
                                    "observation supports WeatherKit",
                                    "observation supports Open-Meteo",
                                    "observation contradicts both")},
        active_weather_cities=sum(1 for c in city_rows if c["situation_new"] != "clear"),
        check_results_by_data_name=checks,
        deviations_from_app=[
            "unixtime indexing on the legacy path (equivalent index math; app uses DateParser on local ISO)",
            "WeatherKit sampled via REST (same backend as the app's framework) when weatherkit.json is in the signing kit (or ~/.fastweather-keys); REST minutes lack a precipitation-type field so per-minute active = intensity>0 (approximation of the Swift path)",
            "pseudo-saved cities: 3 nearest bundled cities 40-250 km stand in for user's saved list",
        ])
    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    log("Done: %d cities, %d result rows, %d API calls, %d errors" % (
        len(city_rows), len(all_rows), API_CALLS["count"], len(errors)))
    log("Results: %s" % results_path)
    print("\nRUN_DIR=%s" % run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

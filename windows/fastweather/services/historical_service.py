"""Historical weather via the Open-Meteo archive API (+ forecast past_days).

The archive lags real time by a few days; for very recent dates the forecast
API's past_days provides the same daily fields with no lag. Results are disk-
cached (historical data never changes). Multi-year lookups fetch each year
concurrently.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from ..cache.disk_cache import DiskCache
from ..constants import OPEN_METEO_API_URL, OPEN_METEO_ARCHIVE_URL
from ..models.historical import HistoricalDay
from . import http

_DAILY = "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum,windspeed_10m_max"

_cache = None


def _disk():
    global _cache
    if _cache is None:
        _cache = DiskCache("historical", max_age=None)  # permanent
    return _cache


def _day_from(daily, idx):
    def g(key):
        arr = daily.get(key)
        return arr[idx] if arr and idx < len(arr) else None
    return HistoricalDay(
        date=daily.get("time", [None])[idx] if idx < len(daily.get("time", [])) else None,
        temp_max=g("temperature_2m_max"),
        temp_min=g("temperature_2m_min"),
        precip_sum=g("precipitation_sum"),
        snowfall_sum=g("snowfall_sum"),
        wind_max=g("windspeed_10m_max"),
        weather_code=g("weathercode"),
    )


def _fetch_range_raw(lat, lon, start_date, end_date):
    """Fetch a date range, choosing archive vs forecast-past_days by recency."""
    today = date.today()
    end = date.fromisoformat(end_date)
    recent_cutoff = today - timedelta(days=10)

    if end >= recent_cutoff:
        # Use forecast past_days for recency (archive lags a few days).
        past_days = min(92, (today - date.fromisoformat(start_date)).days + 1)
        data = http.get_json(OPEN_METEO_API_URL, params={
            "latitude": lat, "longitude": lon, "timezone": "auto",
            "daily": _DAILY, "past_days": max(1, past_days), "forecast_days": 1,
        })
    else:
        data = http.get_json(OPEN_METEO_ARCHIVE_URL, params={
            "latitude": lat, "longitude": lon, "timezone": "auto",
            "daily": _DAILY, "start_date": start_date, "end_date": end_date,
        })
    return data.get("daily", {})


def fetch_range(lat, lon, start_date, end_date):
    """Return HistoricalDay list for [start_date, end_date] inclusive."""
    key = f"range:{lat:.3f},{lon:.3f}:{start_date}:{end_date}"
    cached = _disk().get(key)
    if cached is not None:
        return [HistoricalDay(**d) for d in cached]

    daily = _fetch_range_raw(lat, lon, start_date, end_date)
    times = daily.get("time", [])
    days = []
    for i, t in enumerate(times):
        if start_date <= t <= end_date:
            days.append(_day_from(daily, i))
    _disk().set(key, [d.__dict__ for d in days])
    return days


def fetch_single_day(lat, lon, day_iso):
    days = fetch_range(lat, lon, day_iso, day_iso)
    return days[0] if days else HistoricalDay(date=day_iso, error="No data")


def fetch_multi_year(lat, lon, month, day, years_back, end_year=None):
    """Same calendar day across `years_back` years ending at `end_year`
    (default last year), newest first. Years before the 1940 archive start
    are left out."""
    if end_year is None:
        end_year = date.today().year - 1
    years = [y for y in range(end_year, end_year - years_back, -1) if y >= 1940]

    def one(year):
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        try:
            return fetch_single_day(lat, lon, iso)
        except Exception as e:  # noqa: BLE001
            return HistoricalDay(date=iso, error=str(e))

    with ThreadPoolExecutor(max_workers=5) as ex:
        return list(ex.map(one, years))

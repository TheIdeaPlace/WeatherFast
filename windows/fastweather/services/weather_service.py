"""Open-Meteo forecast fetching (current / hourly / daily).

Pure data: given coordinates and a detail level, returns the parsed API JSON.
Parameter sets are preserved verbatim from the original monolith.
"""

from ..constants import OPEN_METEO_API_URL
from . import http

_CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,dewpoint_2m,is_day,"
    "precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,"
    "surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m,visibility"
)

_FULL_HOURLY_FIELDS = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,dewpoint_2m,precipitation,"
    "precipitation_probability,rain,showers,snowfall,snow_depth,weathercode,pressure_msl,"
    "surface_pressure,cloudcover,cloudcover_low,cloudcover_mid,cloudcover_high,visibility,"
    "evapotranspiration,et0_fao_evapotranspiration,vapor_pressure_deficit,windspeed_10m,"
    "winddirection_10m,windgusts_10m,uv_index,uv_index_clear_sky,is_day,cape,"
    "freezing_level_height,soil_temperature_0cm"
)

_FULL_DAILY_FIELDS = (
    "weathercode,temperature_2m_max,temperature_2m_min,apparent_temperature_max,"
    "apparent_temperature_min,sunrise,sunset,daylight_duration,sunshine_duration,"
    "uv_index_max,uv_index_clear_sky_max,precipitation_sum,rain_sum,showers_sum,"
    "snowfall_sum,precipitation_hours,precipitation_probability_max,windspeed_10m_max,"
    "windgusts_10m_max,winddirection_10m_dominant,shortwave_radiation_sum,"
    "et0_fao_evapotranspiration"
)


def fetch_weather(lat, lon, detail="basic", forecast_days=16, past_days=7):
    """Fetch forecast data for a coordinate. Returns parsed JSON dict.

    detail="basic": lightweight (list summary). detail="full": complete
    hourly + daily forecast for the detailed view, including ``past_days`` of
    history so the detailed view's date navigation can browse recent days.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": _CURRENT_FIELDS,
        "timezone": "auto",
    }
    if detail == "full":
        params["hourly"] = _FULL_HOURLY_FIELDS
        params["daily"] = _FULL_DAILY_FIELDS
        params["forecast_days"] = forecast_days
        params["past_days"] = past_days
    else:
        params["hourly"] = "cloudcover"
        params["daily"] = "temperature_2m_max,temperature_2m_min"
        params["forecast_days"] = 1

    return http.get_json(OPEN_METEO_API_URL, params=params)


# What ui/city_row.city_row_text reads from "current" (plus today's high/low).
_ROW_CURRENT_FIELDS = "temperature_2m,weather_code,cloud_cover,rain,showers,snowfall"


def fetch_basic_many(coords):
    """Today's basic weather for many places in one request.

    Open-Meteo takes comma-separated coordinates and answers with one result
    per place, in the same order. It still counts each place as an API call
    (and more for requests over 10 variables), so this asks only for what a
    city row reads: 8 variables. Returns a list as long as ``coords``; raises
    on a network error or an answer of the wrong length.
    """
    if not coords:
        return []
    params = {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in coords),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in coords),
        "current": _ROW_CURRENT_FIELDS,
        "daily": "temperature_2m_max,temperature_2m_min",
        "forecast_days": 1,
        "timezone": "auto",
    }
    data = http.get_json(OPEN_METEO_API_URL, params=params)
    if isinstance(data, dict):  # a single place comes back as an object, not a list
        data = [data]
    if not isinstance(data, list) or len(data) != len(coords):
        raise ValueError(f"expected {len(coords)} results from Open-Meteo")
    return data

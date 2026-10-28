"""The one-line summary each city gets in the Your Cities list.

Kept free of wx so the wording can be tested. The row is built only from the
"basic" fetch (today only); the Full Weather fetch carries seven past days, so
its first daily entry is a week ago. Reading that as today put last week's
high and low on the row after you opened Full Weather.
"""

from ..models.weather import condition_summary


def _today_index(data):
    """Index of today in the daily arrays: the day the current reading is in."""
    days = (data.get("daily") or {}).get("time") or []
    today = str((data.get("current") or {}).get("time", ""))[:10]
    return days.index(today) if today and today in days else 0


def city_row_text(city, data, fmt):
    """``"<city> - 72°F, Partly cloudy [Rain] (High: 78°F, Low: 61°F)"``.

    The sky word is the same one Full Weather's Condition line uses (the
    weather code, falling back to cloud cover), so the list and the report
    can't disagree ("mostly cloudy" in the list, "Mainly clear" in the report).
    Returns None when the data has no current temperature (the caller
    shows the error row rather than leaving "Loading...").
    """
    curr = data.get("current") or data.get("current_weather") or {}
    temp_c = curr.get("temperature_2m", curr.get("temperature"))
    if temp_c is None:
        return None
    text = f"{city} - {fmt.temperature_short(temp_c)}"

    sky = condition_summary(curr.get("weather_code"), curr.get("cloud_cover"))
    if sky and sky != "—":
        text += f", {sky}"

    if (curr.get("snowfall") or 0) >= 0.01:
        text += " [Snow]"
    elif (curr.get("rain") or 0) >= 0.01 or (curr.get("showers") or 0) >= 0.01:
        text += " [Rain]"

    daily = data.get("daily") or {}
    highs, lows = daily.get("temperature_2m_max"), daily.get("temperature_2m_min")
    i = _today_index(data)
    if (highs and lows and i < len(highs) and i < len(lows)
            and highs[i] is not None and lows[i] is not None):
        text += (f" (High: {fmt.temperature_short(highs[i])}, "
                 f"Low: {fmt.temperature_short(lows[i])})")
    return text


def city_row_error(city):
    """The row for a city whose weather couldn't be fetched. Without it the
    row said "Loading..." for good."""
    return f"{city} - Couldn't get the weather. Press F5 to try again."

import unittest

from fastweather.models.settings import AppSettings
from fastweather.ui.city_row import city_row_error, city_row_text
from fastweather.ui.formatters import Formatter


def _fmt(temp="F"):
    s = AppSettings()
    s["units"]["temperature"] = temp
    return Formatter(s)


def _basic(**current):
    """A basic-detail payload (today only), as weather_service returns it."""
    cur = {"time": "2026-10-27T15:00", "temperature_2m": 18.0,
           "weather_code": 3, "cloud_cover": 95}
    cur.update(current)
    return {
        "current": cur,
        "daily": {"time": ["2026-10-27"],
                  "temperature_2m_max": [18.3], "temperature_2m_min": [6.7]},
    }


class CityRowTests(unittest.TestCase):
    def test_basic_row(self):
        self.assertEqual(
            city_row_text("Madison, Wisconsin, United States", _basic(), _fmt()),
            "Madison, Wisconsin, United States - 64°F, Overcast (High: 65°F, Low: 44°F)")

    def test_high_low_are_todays_not_the_first_day(self):
        # The full payload starts seven days back. The row must use today's
        # entry, not daily[0] (it showed last week's high and low).
        data = _basic()
        data["daily"] = {
            "time": ["2026-10-20", "2026-10-21", "2026-10-27", "2026-10-28"],
            "temperature_2m_max": [20.0, 21.0, 18.3, 22.0],
            "temperature_2m_min": [3.3, 4.0, 6.7, 8.0],
        }
        self.assertIn("(High: 65°F, Low: 44°F)", city_row_text("X", data, _fmt()))

    def test_sky_word_matches_full_weather_condition(self):
        # Weather code 1 is "Mainly clear" in Full Weather; the row used to say
        # "mostly cloudy" from the cloud cover at the same moment.
        row = city_row_text("Miami", _basic(weather_code=1, cloud_cover=70), _fmt())
        self.assertIn(", Mainly clear", row)
        self.assertNotIn("cloudy", row)

    def test_sky_word_falls_back_to_cloud_cover(self):
        row = city_row_text("X", _basic(weather_code=None, cloud_cover=50), _fmt())
        self.assertIn(", Partly Cloudy", row)

    def test_no_sky_word_without_code_or_cloud(self):
        row = city_row_text("X", _basic(weather_code=None, cloud_cover=None), _fmt())
        self.assertTrue(row.startswith("X - 64°F (High:"), row)

    def test_rain_and_snow_markers(self):
        self.assertIn("[Rain]", city_row_text("X", _basic(rain=0.2), _fmt()))
        self.assertIn("[Rain]", city_row_text("X", _basic(showers=0.5), _fmt()))
        self.assertIn("[Snow]", city_row_text("X", _basic(snowfall=0.3, rain=0.2), _fmt()))
        self.assertNotIn("[", city_row_text("X", _basic(rain=0.0), _fmt()))

    def test_celsius(self):
        self.assertIn("X - 18°C", city_row_text("X", _basic(), _fmt("C")))

    def test_missing_daily_or_none_values(self):
        data = _basic()
        del data["daily"]
        self.assertEqual(city_row_text("X", data, _fmt()), "X - 64°F, Overcast")
        data = _basic()
        data["daily"]["temperature_2m_max"] = [None]
        self.assertNotIn("High", city_row_text("X", data, _fmt()))

    def test_no_current_conditions(self):
        self.assertIsNone(city_row_text("X", {"daily": {}}, _fmt()))

    def test_error_row_keeps_the_city_prefix(self):
        # _refresh_city_row finds a row by "<city> - ".
        self.assertTrue(city_row_error("Sydney").startswith("Sydney - "))
        self.assertIn("F5", city_row_error("Sydney"))


if __name__ == "__main__":
    unittest.main()

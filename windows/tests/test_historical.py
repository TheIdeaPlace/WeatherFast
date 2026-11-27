import unittest
from datetime import date
from unittest import mock

from fastweather.models.historical import HistoricalDay
from fastweather.models.settings import AppSettings
from fastweather.services import historical_service
from fastweather.ui.dialogs.historical_dialog import (
    browse_end, can_shift_browse_year, format_day_line, in_archive,
    multi_year_end_limit, shift_year)
from fastweather.ui.formatters import Formatter


class HistoricalTests(unittest.TestCase):
    def test_day_from(self):
        daily = {
            "time": ["2000-01-01", "2000-01-02"],
            "temperature_2m_max": [1.0, 2.0],
            "temperature_2m_min": [-3.0, -2.0],
            "precipitation_sum": [0.0, 5.0],
            "snowfall_sum": [0.0, 1.0],
            "windspeed_10m_max": [10.0, 20.0],
            "weathercode": [3, 71],
        }
        day = historical_service._day_from(daily, 1)
        self.assertEqual(day.date, "2000-01-02")
        self.assertEqual(day.temp_max, 2.0)
        self.assertEqual(day.weather_code, 71)

    def test_format_day_line(self):
        fmt = Formatter(AppSettings())
        day = HistoricalDay(date="2000-01-02", temp_max=2.0, temp_min=-2.0,
                            precip_sum=5.0, weather_code=71)
        line = format_day_line(day, fmt)
        self.assertIn("2000-01-02", line)
        self.assertIn("High 36°F", line)   # 2C -> 36F
        self.assertIn("Slight snow fall", line)

    def test_format_day_line_error(self):
        fmt = Formatter(AppSettings())
        line = format_day_line(HistoricalDay(date="2000-01-02", error="No data"), fmt)
        self.assertIn("unavailable", line)

    def test_multi_year_dates(self):
        captured = []
        orig = historical_service.fetch_single_day
        historical_service.fetch_single_day = (
            lambda lat, lon, iso: captured.append(iso) or HistoricalDay(date=iso))
        try:
            days = historical_service.fetch_multi_year(1.0, 2.0, 7, 4, 3)
        finally:
            historical_service.fetch_single_day = orig
        self.assertEqual(len(days), 3)
        # all requested dates end in -07-04
        self.assertTrue(all(iso.endswith("-07-04") for iso in captured))

    def test_shift_year(self):
        self.assertEqual(shift_year(date(2020, 7, 4), -1), date(2019, 7, 4))
        self.assertEqual(shift_year(date(2024, 2, 29), 1), date(2025, 2, 28))

    def test_can_shift_browse_year(self):
        today = date(2026, 11, 26)
        self.assertTrue(can_shift_browse_year(date(2024, 11, 1), 1, today))
        # The shifted range would start after today.
        self.assertFalse(can_shift_browse_year(date(2025, 12, 1), 1, today))
        # The archive begins in 1940.
        self.assertTrue(can_shift_browse_year(date(1941, 1, 1), -1, today))
        self.assertFalse(can_shift_browse_year(date(1940, 1, 1), -1, today))

    def test_browse_end_stops_at_today(self):
        today = date(2026, 11, 26)
        self.assertEqual(browse_end(date(2026, 10, 1), 30, today), date(2026, 10, 30))
        # The archive rejects end dates after today.
        self.assertEqual(browse_end(date(2026, 11, 10), 30, today), today)

    def test_in_archive(self):
        today = date(2026, 11, 26)
        self.assertTrue(in_archive(date(1940, 1, 1), today))
        self.assertFalse(in_archive(date(1939, 12, 31), today))
        self.assertTrue(in_archive(today, today))
        self.assertFalse(in_archive(date(2026, 11, 27), today))

    def test_multi_year_end_limit(self):
        self.assertEqual(multi_year_end_limit(date(2026, 11, 26)), 2025)

    def test_multi_year_window_end_year(self):
        captured = []
        with mock.patch.object(historical_service, "fetch_single_day",
                               lambda lat, lon, iso: captured.append(iso) or HistoricalDay(date=iso)):
            days = historical_service.fetch_multi_year(1.0, 2.0, 7, 4, 3, end_year=1990)
        # Fetches run on a thread pool, so only the result order is guaranteed.
        self.assertEqual(sorted(captured), ["1988-07-04", "1989-07-04", "1990-07-04"])
        self.assertEqual([d.date for d in days], ["1990-07-04", "1989-07-04", "1988-07-04"])

    def test_multi_year_window_stops_at_1940(self):
        captured = []
        with mock.patch.object(historical_service, "fetch_single_day",
                               lambda lat, lon, iso: captured.append(iso) or HistoricalDay(date=iso)):
            days = historical_service.fetch_multi_year(1.0, 2.0, 7, 4, 5, end_year=1941)
        self.assertEqual([d.date for d in days], ["1941-07-04", "1940-07-04"])
        self.assertEqual(sorted(captured), ["1940-07-04", "1941-07-04"])

    def test_multi_year_feb_29_uses_feb_28_in_non_leap_years(self):
        with mock.patch.object(historical_service, "fetch_single_day",
                               lambda lat, lon, iso: HistoricalDay(date=iso)):
            days = historical_service.fetch_multi_year(1.0, 2.0, 2, 29, 5, end_year=2024)
        self.assertEqual([d.date for d in days],
                         ["2024-02-29", "2023-02-28", "2022-02-28", "2021-02-28", "2020-02-29"])

    def test_fetch_range_caches_only_settled_results(self):
        store = {}
        disk = mock.Mock(get=store.get, set=store.__setitem__)
        old_iso, recent_iso = "2000-01-02", date.today().isoformat()
        daily = lambda iso: {"time": [iso], "temperature_2m_max": [1.0]}
        with mock.patch.object(historical_service, "_disk", return_value=disk):
            # An empty result isn't cached, so the next lookup asks again.
            with mock.patch.object(historical_service, "_fetch_range_raw", return_value={}):
                self.assertEqual(historical_service.fetch_range(1.0, 2.0, old_iso, old_iso), [])
            self.assertEqual(store, {})
            with mock.patch.object(historical_service, "_fetch_range_raw",
                                   side_effect=lambda lat, lon, s, e: daily(s)) as raw:
                historical_service.fetch_range(1.0, 2.0, old_iso, old_iso)
                historical_service.fetch_range(1.0, 2.0, old_iso, old_iso)
                self.assertEqual(raw.call_count, 1)
                # Recent days can still change, so they're fetched every time.
                historical_service.fetch_range(1.0, 2.0, recent_iso, recent_iso)
                historical_service.fetch_range(1.0, 2.0, recent_iso, recent_iso)
                self.assertEqual(raw.call_count, 3)
            self.assertEqual(len(store), 1)


if __name__ == "__main__":
    unittest.main()

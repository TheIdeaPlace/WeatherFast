"""Places of the World: the shared data file and the wx-free helpers."""
import json
import os
import unittest

from fastweather import places
from fastweather.ui.dialogs.location_browser import row_label

_HERE = os.path.dirname(os.path.abspath(__file__))
_WINDOWS = os.path.dirname(_HERE)
_REPO = os.path.dirname(_WINDOWS)

GOLDEN_GATE = {
    "name": "Golden Gate Bridge",
    "description": "Art Deco suspension bridge across the Golden Gate strait",
    "city": "San Francisco", "state": "California", "country": "United States",
    "lat": 37.8197, "lon": -122.4786,
}
VOSTOK = {
    "name": "Vostok Station", "description": "Coldest temperature ever measured",
    "city": None, "state": None, "country": "Antarctica", "lat": -78.46, "lon": 106.84,
}


class HelperTests(unittest.TestCase):
    def test_location_line(self):
        self.assertEqual(places.location_line(GOLDEN_GATE),
                         "San Francisco, California, United States")
        self.assertEqual(places.location_line(VOSTOK), "Antarctica")

    def test_saved_name_matches_ios(self):
        self.assertEqual(places.saved_name(GOLDEN_GATE), "Golden Gate Bridge, San Francisco")
        self.assertEqual(places.saved_name(VOSTOK), "Vostok Station")
        same = dict(GOLDEN_GATE, name="Venice", city="Venice")
        self.assertEqual(places.saved_name(same), "Venice")

    def test_about_text(self):
        self.assertEqual(
            places.about_text(GOLDEN_GATE),
            "San Francisco, California, United States. "
            "Art Deco suspension bridge across the Golden Gate strait")
        self.assertEqual(places.about_text(dict(VOSTOK, description="")), "Antarctica")

    def test_category_label(self):
        self.assertEqual(places.category_label({"name": "Beaches", "places": [1, 2]}),
                         "Beaches (2 places)")
        self.assertEqual(places.category_label({"name": "One", "places": [1]}),
                         "One (1 place)")


class ParseTests(unittest.TestCase):
    def test_bad_entries_are_skipped(self):
        data = {"categories": [
            {"name": "Ok", "description": "d", "places": [
                GOLDEN_GATE,
                {"name": "No coords"},
                {"name": "Bad lat", "lat": "north", "lon": 1},
                {"lat": 1, "lon": 2},
                "not a dict",
                dict(VOSTOK, lat="-78.46"),   # numeric strings are fine
            ]},
            {"description": "no name", "places": []},
            "junk",
        ]}
        cats = places.parse_categories(data)
        self.assertEqual([c["name"] for c in cats], ["Ok"])
        self.assertEqual([p["name"] for p in cats[0]["places"]],
                         ["Golden Gate Bridge", "Vostok Station"])
        self.assertEqual(cats[0]["places"][1]["lat"], -78.46)

    def test_not_a_file(self):
        self.assertEqual(places.parse_categories(None), [])
        self.assertEqual(places.parse_categories([]), [])
        self.assertEqual(places.parse_categories({"categories": None}), [])


class BundledFileTests(unittest.TestCase):
    def test_windows_copy_matches_citydata(self):
        with open(os.path.join(_WINDOWS, places.FILENAME), encoding="utf-8") as f:
            ours = json.load(f)
        with open(os.path.join(_REPO, "CityData", places.FILENAME), encoding="utf-8") as f:
            source = json.load(f)
        self.assertEqual(ours, source, "run CityData/distribute-caches to update windows/")

    def test_loads_every_place(self):
        cats = places.load_categories()
        self.assertGreaterEqual(len(cats), 3)
        for cat in cats:
            self.assertTrue(cat["places"], cat["name"])
            self.assertTrue(cat["description"], cat["name"])
            for p in cat["places"]:
                self.assertTrue(-90 <= p["lat"] <= 90, p["name"])
                self.assertTrue(-180 <= p["lon"] <= 180, p["name"])
                self.assertTrue(places.location_line(p), p["name"])


def _row(**kw):
    c = {"display": "Golden Gate Bridge", "row": None, "badge": "", "failed": False,
         "about": places.about_text(GOLDEN_GATE)}
    c.update(kw)
    return c


class PlaceRowTests(unittest.TestCase):
    ABOUT = ("San Francisco, California, United States. "
             "Art Deco suspension bridge across the Golden Gate strait")

    def test_loading(self):
        self.assertEqual(row_label(_row()), f"Golden Gate Bridge - Loading. {self.ABOUT}")

    def test_weather_then_where_and_why(self):
        c = _row(row="Golden Gate Bridge - 55°F, Clear (High: 60°F, Low: 50°F)")
        self.assertEqual(row_label(c),
                         f"Golden Gate Bridge - 55°F, Clear (High: 60°F, Low: 50°F). {self.ABOUT}")

    def test_badge_before_about(self):
        c = _row(row="Golden Gate Bridge - 55°F, Clear", badge="  [MODERATE: Wind Advisory]")
        self.assertEqual(
            row_label(c),
            f"Golden Gate Bridge - 55°F, Clear  [MODERATE: Wind Advisory]. {self.ABOUT}")

    def test_failed(self):
        self.assertEqual(row_label(_row(failed=True)),
                         f"Golden Gate Bridge - weather unavailable. {self.ABOUT}")


if __name__ == "__main__":
    unittest.main()

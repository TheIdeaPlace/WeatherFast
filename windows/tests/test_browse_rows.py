"""Browse Cities rows and its background-result gate. No windows are created:
these are module-level helpers (importing wx doesn't open anything)."""
import types
import unittest

from fastweather.ui.dialogs.location_browser import _deliver, row_label


def _city(**kw):
    c = {"display": "Algoma, Wisconsin, United States", "row": None, "badge": "",
         "failed": False}
    c.update(kw)
    return c


class RowLabelTests(unittest.TestCase):
    def test_loading_like_your_cities(self):
        self.assertEqual(row_label(_city()), "Algoma, Wisconsin, United States - Loading...")

    def test_weather_row_and_badge(self):
        c = _city(row="Algoma, Wisconsin, United States - 45°F, Overcast",
                  badge="  [SEVERE: Gale Warning]")
        self.assertEqual(row_label(c),
                         "Algoma, Wisconsin, United States - 45°F, Overcast  [SEVERE: Gale Warning]")

    def test_failed(self):
        self.assertEqual(row_label(_city(failed=True)),
                         "Algoma, Wisconsin, United States - weather unavailable")


class DeliverTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.state = types.SimpleNamespace(alive=True, gen=3)

    def fn(self, *args):
        self.calls.append(args)

    def test_current_result_runs(self):
        _deliver(self.state, 3, self.fn, "a", 1)
        self.assertEqual(self.calls, [("a", 1)])

    def test_stale_generation_is_dropped(self):
        # Another region was loaded after this fetch started.
        _deliver(self.state, 2, self.fn, "a")
        self.assertEqual(self.calls, [])

    def test_closed_dialog_is_dropped(self):
        self.state.alive = False
        _deliver(self.state, 3, self.fn, "a")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()

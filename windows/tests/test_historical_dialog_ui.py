"""Drives the real Historical Weather dialog with wxPython.

Skipped when wxPython can't be imported or no display is available, so
wx-less environments still pass. Network calls are patched out and the
dialog's worker thread runs synchronously.
"""

import unittest
from datetime import date, timedelta
from unittest import mock

try:
    import wx
except Exception as exc:  # noqa: BLE001
    raise unittest.SkipTest(f"wxPython not available: {exc}")

from fastweather.models.historical import HistoricalDay
from fastweather.models.settings import AppSettings
from fastweather.services import historical_service
from fastweather.ui.dialogs import historical_dialog
from fastweather.ui.dialogs.historical_dialog import (
    ARCHIVE_START, HistoricalDialog, shift_year)
from fastweather.ui.formatters import Formatter

_app = None


def setUpModule():
    global _app
    _app = wx.GetApp()
    if _app is None:
        try:
            _app = wx.App(False)
        except BaseException as exc:  # noqa: BLE001 - wx may SystemExit without a display
            raise unittest.SkipTest(f"No display for wxPython: {exc}")
    if not _app.IsDisplayAvailable():
        raise unittest.SkipTest("No display for wxPython")


class _SyncThread:
    """Stands in for threading.Thread: runs the target on start()."""

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        self._target()


class HistoricalDialogUITests(unittest.TestCase):
    def setUp(self):
        self.today = date.today()
        self.calls = {"range": [], "single": [], "multi": []}

        def fake_range(lat, lon, start_date, end_date):
            self.calls["range"].append((start_date, end_date))
            return []

        def fake_single(lat, lon, day_iso):
            self.calls["single"].append(day_iso)
            # The dialog wraps this in a list, so return a real day to render.
            return HistoricalDay(date=day_iso, temp_max=20.0, temp_min=10.0)

        def fake_multi(lat, lon, month, day, years_back, end_year=None):
            self.calls["multi"].append((month, day, years_back, end_year))
            return []

        patches = [
            mock.patch.object(historical_service, "fetch_range", fake_range),
            mock.patch.object(historical_service, "fetch_single_day", fake_single),
            mock.patch.object(historical_service, "fetch_multi_year", fake_multi),
            mock.patch.object(historical_dialog.threading, "Thread", _SyncThread),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        self.dlg = HistoricalDialog(
            None, ("Madison", 43.07, -89.38), {"options": {}},
            Formatter(AppSettings()))

    def tearDown(self):
        self._flush()
        self.dlg._alive = False
        self.dlg.Destroy()
        self._flush()

    # -- helpers --------------------------------------------------------------
    def _flush(self):
        # Run pending wx.CallAfter calls (the dialog's _render).
        _app.ProcessPendingEvents()
        _app.Yield(True)

    def click(self, button):
        event = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
        event.SetEventObject(button)
        button.GetEventHandler().ProcessEvent(event)
        self._flush()

    def set_spin(self, spin, value):
        spin.SetValue(value)
        event = wx.SpinEvent(wx.wxEVT_SPINCTRL, spin.GetId())
        event.SetEventObject(spin)
        event.SetPosition(value)
        spin.GetEventHandler().ProcessEvent(event)
        self._flush()

    def set_date(self, picker, d):
        picker.SetValue(historical_dialog._to_wxdate(d))
        event = wx.adv.DateEvent(picker, picker.GetValue(), wx.adv.wxEVT_DATE_CHANGED)
        picker.GetEventHandler().ProcessEvent(event)
        self._flush()

    @staticmethod
    def picker_date(picker):
        return HistoricalDialog._picker_date(picker)

    def leap_day_in_past(self):
        """A Feb 29 whose following year's Feb 28 is still before today."""
        year = self.today.year - 2
        while year % 4 or (year % 100 == 0 and year % 400):
            year -= 1
        return date(year, 2, 29)

    # -- Single Day -----------------------------------------------------------
    def test_single_steps_and_fetches(self):
        start = self.today - timedelta(days=10)
        self.set_date(self.dlg.single_date, start)
        self.click(self.dlg.single_prev)
        self.assertEqual(self.picker_date(self.dlg.single_date), start - timedelta(days=1))
        self.click(self.dlg.single_next)
        self.click(self.dlg.single_next)
        self.assertEqual(self.picker_date(self.dlg.single_date), start + timedelta(days=1))
        self.assertEqual(self.calls["single"], [
            (start - timedelta(days=1)).isoformat(),
            start.isoformat(),
            (start + timedelta(days=1)).isoformat(),
        ])

    def test_single_next_disabled_at_today(self):
        self.set_date(self.dlg.single_date, self.today - timedelta(days=1))
        self.assertTrue(self.dlg.single_next.IsEnabled())
        self.click(self.dlg.single_next)
        self.assertEqual(self.picker_date(self.dlg.single_date), self.today)
        self.assertFalse(self.dlg.single_next.IsEnabled())
        self.assertTrue(self.dlg.single_prev.IsEnabled())
        # Even if the event arrives, the guard keeps the date at today.
        self.click(self.dlg.single_next)
        self.assertEqual(self.picker_date(self.dlg.single_date), self.today)
        self.assertEqual(self.calls["single"], [self.today.isoformat()])

    def test_single_prev_disabled_at_archive_start(self):
        self.set_date(self.dlg.single_date, ARCHIVE_START + timedelta(days=1))
        self.assertTrue(self.dlg.single_prev.IsEnabled())
        self.click(self.dlg.single_prev)
        self.assertEqual(self.picker_date(self.dlg.single_date), ARCHIVE_START)
        self.assertFalse(self.dlg.single_prev.IsEnabled())
        self.assertTrue(self.dlg.single_next.IsEnabled())
        self.click(self.dlg.single_prev)
        self.assertEqual(self.picker_date(self.dlg.single_date), ARCHIVE_START)
        self.assertEqual(self.calls["single"], [ARCHIVE_START.isoformat()])

    def test_single_picker_limited_to_archive(self):
        ok, lo, hi = self.dlg.single_date.GetRange()
        self.assertTrue(ok)
        self.assertEqual(historical_dialog._wxdate_to_iso(lo), ARCHIVE_START.isoformat())
        self.assertEqual(historical_dialog._wxdate_to_iso(hi), self.today.isoformat())

    # -- Multi-Year -----------------------------------------------------------
    def test_multiyear_initial_state(self):
        last_year = self.today.year - 1
        self.assertEqual(self.dlg.my_end_year, last_year)
        self.assertEqual(self.dlg.my_years.GetValue(), 20)
        self.assertEqual(self.dlg.my_prev.GetLabel(), "Previous 20 Years")
        self.assertEqual(self.dlg.my_next.GetLabel(), "Next 20 Years")
        self.assertTrue(self.dlg.my_prev.IsEnabled())
        self.assertFalse(self.dlg.my_next.IsEnabled())

    def test_multiyear_labels_follow_spin(self):
        self.set_spin(self.dlg.my_years, 7)
        self.assertEqual(self.dlg.my_prev.GetLabel(), "Previous 7 Years")
        self.assertEqual(self.dlg.my_next.GetLabel(), "Next 7 Years")

    def test_multiyear_steps_and_clamps_to_last_year(self):
        last_year = self.today.year - 1
        self.set_date(self.dlg.my_date, date(2020, 7, 4))
        self.click(self.dlg.my_prev)
        self.assertEqual(self.dlg.my_end_year, last_year - 20)
        self.assertTrue(self.dlg.my_next.IsEnabled())
        self.assertEqual(self.calls["multi"][-1], (7, 4, 20, last_year - 20))
        # A smaller window then a larger step: Next lands past last year and clamps.
        self.set_spin(self.dlg.my_years, 15)
        self.click(self.dlg.my_next)
        self.assertEqual(self.dlg.my_end_year, last_year - 5)
        self.click(self.dlg.my_next)
        self.assertEqual(self.dlg.my_end_year, last_year)
        self.assertEqual(self.calls["multi"][-1], (7, 4, 15, last_year))
        self.assertFalse(self.dlg.my_next.IsEnabled())
        self.assertEqual(self.dlg.settings["options"]["historical_years_back"], 15)

    def test_multiyear_prev_stops_at_1940(self):
        self.set_spin(self.dlg.my_years, 85)
        end = self.dlg.my_end_year
        while self.dlg.my_prev.IsEnabled():
            self.click(self.dlg.my_prev)
            self.assertLess(self.dlg.my_end_year, end)
            end = self.dlg.my_end_year
        self.assertGreaterEqual(self.dlg.my_end_year, ARCHIVE_START.year)
        self.assertLess(self.dlg.my_end_year - 85, ARCHIVE_START.year)
        count = len(self.calls["multi"])
        self.click(self.dlg.my_prev)  # guard: window would end before 1940
        self.assertEqual(self.dlg.my_end_year, end)
        self.assertEqual(len(self.calls["multi"]), count)

    # -- Daily Browse ---------------------------------------------------------
    def test_browse_labels_follow_spin(self):
        self.assertEqual(self.dlg.browse_prev.GetLabel(), "Previous 7 Days")
        self.assertEqual(self.dlg.browse_next.GetLabel(), "Next 7 Days")
        self.set_spin(self.dlg.browse_days, 1)
        self.assertEqual(self.dlg.browse_prev.GetLabel(), "Previous 1 Day")
        self.assertEqual(self.dlg.browse_next.GetLabel(), "Next 1 Day")
        self.set_spin(self.dlg.browse_days, 14)
        self.assertEqual(self.dlg.browse_prev.GetLabel(), "Previous 14 Days")

    def test_browse_steps_by_range(self):
        start = self.today - timedelta(days=60)
        self.set_date(self.dlg.browse_date, start)
        self.click(self.dlg.browse_prev)
        new = start - timedelta(days=7)
        self.assertEqual(self.picker_date(self.dlg.browse_date), new)
        self.assertEqual(self.calls["range"][-1],
                         (new.isoformat(), (new + timedelta(days=6)).isoformat()))
        self.click(self.dlg.browse_next)
        self.assertEqual(self.picker_date(self.dlg.browse_date), start)

    def test_browse_end_clamps_to_today(self):
        start = self.today - timedelta(days=10)
        self.set_date(self.dlg.browse_date, start)
        self.click(self.dlg.browse_next)
        new = start + timedelta(days=7)
        self.assertEqual(self.picker_date(self.dlg.browse_date), new)
        self.assertEqual(self.calls["range"][-1], (new.isoformat(), self.today.isoformat()))
        # Next 7 Days would start after today.
        self.assertFalse(self.dlg.browse_next.IsEnabled())
        count = len(self.calls["range"])
        self.click(self.dlg.browse_next)
        self.assertEqual(self.picker_date(self.dlg.browse_date), new)
        self.assertEqual(len(self.calls["range"]), count)

    def test_browse_prev_disabled_near_archive_start(self):
        self.set_date(self.dlg.browse_date, ARCHIVE_START + timedelta(days=6))
        self.assertFalse(self.dlg.browse_prev.IsEnabled())
        self.assertFalse(self.dlg.browse_prev_year.IsEnabled())
        self.set_date(self.dlg.browse_date, ARCHIVE_START + timedelta(days=7))
        self.assertTrue(self.dlg.browse_prev.IsEnabled())
        self.click(self.dlg.browse_prev)
        self.assertEqual(self.picker_date(self.dlg.browse_date), ARCHIVE_START)
        self.assertFalse(self.dlg.browse_prev.IsEnabled())

    def test_browse_year_jump(self):
        start = self.today - timedelta(days=400)
        self.set_date(self.dlg.browse_date, start)
        self.click(self.dlg.browse_prev_year)
        back = shift_year(start, -1)
        self.assertEqual(self.picker_date(self.dlg.browse_date), back)
        self.assertEqual(self.calls["range"][-1],
                         (back.isoformat(), (back + timedelta(days=6)).isoformat()))
        self.click(self.dlg.browse_next_year)
        self.assertEqual(self.picker_date(self.dlg.browse_date), shift_year(back, 1))

    def test_browse_year_jump_leap_day(self):
        leap = self.leap_day_in_past()
        self.set_date(self.dlg.browse_date, leap)
        self.click(self.dlg.browse_next_year)
        self.assertEqual(self.picker_date(self.dlg.browse_date), date(leap.year + 1, 2, 28))
        self.set_date(self.dlg.browse_date, leap)
        self.click(self.dlg.browse_prev_year)
        self.assertEqual(self.picker_date(self.dlg.browse_date), date(leap.year - 1, 2, 28))

    def test_browse_next_year_disabled_when_shift_reaches_today(self):
        start = shift_year(self.today, -1)
        if shift_year(start, 1) < self.today:  # today is Feb 29
            start += timedelta(days=1)
        self.set_date(self.dlg.browse_date, start)
        self.assertFalse(self.dlg.browse_next_year.IsEnabled())
        self.assertTrue(self.dlg.browse_prev_year.IsEnabled())
        count = len(self.calls["range"])
        self.click(self.dlg.browse_next_year)
        self.assertEqual(self.picker_date(self.dlg.browse_date), start)
        self.assertEqual(len(self.calls["range"]), count)
        # One day earlier, the shifted start lands before today.
        self.set_date(self.dlg.browse_date, start - timedelta(days=1))
        self.assertTrue(self.dlg.browse_next_year.IsEnabled())

    def test_browse_next_year_disabled_for_recent_start(self):
        self.set_date(self.dlg.browse_date, self.today - timedelta(days=100))
        self.assertFalse(self.dlg.browse_next_year.IsEnabled())

    def test_browse_load_clamps_end(self):
        start = self.today - timedelta(days=3)
        self.set_date(self.dlg.browse_date, start)
        self.set_spin(self.dlg.browse_days, 10)
        load = next(c for c in self.dlg.browse_date.GetParent().GetChildren()
                    if isinstance(c, wx.Button) and c.GetLabel() == "Load")
        self.click(load)
        self.assertEqual(self.calls["range"][-1], (start.isoformat(), self.today.isoformat()))


if __name__ == "__main__":
    unittest.main()

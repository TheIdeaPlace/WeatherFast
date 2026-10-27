"""Historical weather sheet: Single Day, Multi-Year, and Daily Browse modes."""

import threading
from datetime import date, timedelta

import wx
import wx.adv

from ...models.weather import describe_weather_code
from ...services import historical_service
from ..accessible_list import AccessibleLinesPanel


def _wxdate_to_iso(d):
    return f"{d.GetYear():04d}-{d.GetMonth() + 1:02d}-{d.GetDay():02d}"


def format_day_line(day, fmt):
    if day.error:
        return f"{day.date}: unavailable ({day.error})"
    parts = [f"{day.date}:"]
    if day.temp_max is not None:
        parts.append(f"High {fmt.temperature_short(day.temp_max)}")
    if day.temp_min is not None:
        parts.append(f"Low {fmt.temperature_short(day.temp_min)}")
    if day.precip_sum:
        parts.append(f"{fmt.precipitation(day.precip_sum)} precip")
    if day.snowfall_sum:
        parts.append(f"{fmt.precipitation(day.snowfall_sum)} snow")
    if day.wind_max is not None:
        parts.append(f"Max wind {fmt.wind_speed(day.wind_max)}")
    desc = describe_weather_code(day.weather_code)
    if desc:
        parts.append(desc)
    return " ".join(parts)


class HistoricalDialog(wx.Dialog):
    def __init__(self, parent, center, settings, fmt):
        super().__init__(parent, title=f"Historical Weather - {center[0]}", size=(680, 560))
        self.center = center
        self.settings = settings
        self.fmt = fmt
        self._alive = True

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.nb = wx.Notebook(panel)
        self._build_single()
        self._build_multiyear()
        self._build_browse()
        vbox.Add(self.nb, 1, wx.EXPAND | wx.ALL, 8)
        btns = wx.StdDialogButtonSizer()
        btns.AddButton(wx.Button(panel, wx.ID_CLOSE))
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        panel.SetSizer(vbox)
        self.Bind(wx.EVT_BUTTON, lambda e: self.Close(), id=wx.ID_CLOSE)
        # Escape presses Close: without an escape id, a dialog with no Cancel
        # button ignores Escape.
        self.SetEscapeId(wx.ID_CLOSE)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    # -- tabs -----------------------------------------------------------------
    def _build_single(self):
        p = wx.Panel(self.nb)
        s = wx.BoxSizer(wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(p, label="Date:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.single_date = wx.adv.DatePickerCtrl(p, style=wx.adv.DP_DROPDOWN)
        yesterday = wx.DateTime.Now(); yesterday.Subtract(wx.TimeSpan.Days(2))
        self.single_date.SetValue(yesterday)
        row.Add(self.single_date, 0, wx.RIGHT, 8)
        b = wx.Button(p, label="Load")
        row.Add(b, 0)
        s.Add(row, 0, wx.ALL, 8)
        self.single_lines = AccessibleLinesPanel(p, name="Single day results")
        s.Add(self.single_lines, 1, wx.EXPAND | wx.ALL, 8)
        p.SetSizer(s)
        self.nb.AddPage(p, "Single Day")
        b.Bind(wx.EVT_BUTTON, self.on_single)

    def _build_multiyear(self):
        p = wx.Panel(self.nb)
        s = wx.BoxSizer(wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(p, label="Calendar day:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.my_date = wx.adv.DatePickerCtrl(p, style=wx.adv.DP_DROPDOWN)
        row.Add(self.my_date, 0, wx.RIGHT, 8)
        row.Add(wx.StaticText(p, label="Years back:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.my_years = wx.SpinCtrl(p, min=1, max=85,
                                    initial=self.settings["options"].get("historical_years_back", 20))
        row.Add(self.my_years, 0, wx.RIGHT, 8)
        b = wx.Button(p, label="Load")
        row.Add(b, 0)
        s.Add(row, 0, wx.ALL, 8)
        self.my_lines = AccessibleLinesPanel(p, name="Multi-year results")
        s.Add(self.my_lines, 1, wx.EXPAND | wx.ALL, 8)
        p.SetSizer(s)
        self.nb.AddPage(p, "Multi-Year")
        b.Bind(wx.EVT_BUTTON, self.on_multiyear)

    def _build_browse(self):
        p = wx.Panel(self.nb)
        s = wx.BoxSizer(wx.VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(p, label="Start date:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.browse_date = wx.adv.DatePickerCtrl(p, style=wx.adv.DP_DROPDOWN)
        start = wx.DateTime.Now(); start.Subtract(wx.TimeSpan.Days(9))
        self.browse_date.SetValue(start)
        row.Add(self.browse_date, 0, wx.RIGHT, 8)
        row.Add(wx.StaticText(p, label="Days:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.browse_days = wx.SpinCtrl(p, min=1, max=31, initial=7)
        row.Add(self.browse_days, 0, wx.RIGHT, 8)
        b = wx.Button(p, label="Load")
        row.Add(b, 0)
        s.Add(row, 0, wx.ALL, 8)
        self.browse_lines = AccessibleLinesPanel(p, name="Daily results")
        s.Add(self.browse_lines, 1, wx.EXPAND | wx.ALL, 8)
        p.SetSizer(s)
        self.nb.AddPage(p, "Daily Browse")
        b.Bind(wx.EVT_BUTTON, self.on_browse)

    # -- actions --------------------------------------------------------------
    def _run(self, target_panel, fn):
        target_panel.set_message("Loading...")
        name, lat, lon = self.center

        def work():
            try:
                days = fn(lat, lon)
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(target_panel.set_message, f"Error: {e}")
                return
            wx.CallAfter(self._render, target_panel, days)

        threading.Thread(target=work, daemon=True).start()

    def _render(self, target_panel, days):
        if not self._alive:
            return
        if not days:
            target_panel.set_message("No historical data available.")
            return
        target_panel.set_lines([format_day_line(d, self.fmt) for d in days])
        target_panel.set_focus()

    def on_single(self, event):
        iso = _wxdate_to_iso(self.single_date.GetValue())
        self._run(self.single_lines,
                  lambda lat, lon: [historical_service.fetch_single_day(lat, lon, iso)])

    def on_multiyear(self, event):
        d = self.my_date.GetValue()
        month, day = d.GetMonth() + 1, d.GetDay()
        years = self.my_years.GetValue()
        self.settings["options"]["historical_years_back"] = years
        self._run(self.my_lines,
                  lambda lat, lon: historical_service.fetch_multi_year(lat, lon, month, day, years))

    def on_browse(self, event):
        start = _wxdate_to_iso(self.browse_date.GetValue())
        n = self.browse_days.GetValue()
        end = (date.fromisoformat(start) + timedelta(days=n - 1)).isoformat()
        self._run(self.browse_lines,
                  lambda lat, lon: historical_service.fetch_range(lat, lon, start, end))

    def _on_close(self, event):
        self._alive = False
        event.Skip()

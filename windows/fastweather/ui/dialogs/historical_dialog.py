"""Historical weather sheet: Single Day, Multi-Year, and Daily Browse modes."""

import threading
from datetime import date, timedelta

import wx
import wx.adv

from ...models.weather import describe_weather_code
from ...services import historical_service
from ..accessible_list import AccessibleLinesPanel


# The Open-Meteo archive begins in 1940 and ends today.
ARCHIVE_START = date(1940, 1, 1)


def _wxdate_to_iso(d):
    return f"{d.GetYear():04d}-{d.GetMonth() + 1:02d}-{d.GetDay():02d}"


def _to_wxdate(d):
    return wx.DateTime.FromDMY(d.day, d.month - 1, d.year)


def shift_year(d, years):
    """Same calendar day ``years`` away; Feb 29 lands on Feb 28 in non-leap years."""
    year = d.year + years
    try:
        return d.replace(year=year)
    except ValueError:
        return d.replace(year=year, day=28)


def in_archive(d, today=None):
    return ARCHIVE_START <= d <= (today or date.today())


def can_shift_browse_year(start, years, today=None):
    """A browse range can move only within the archive and must start before today."""
    shifted = shift_year(start, years)
    return shifted >= ARCHIVE_START and shifted < (today or date.today())


def browse_end(start, days, today=None):
    """Last day of a ``days``-long range; the archive rejects end dates after today."""
    return min(start + timedelta(days=days - 1), today or date.today())


def multi_year_end_limit(today=None):
    """Multi-Year windows end no later than last year."""
    return (today or date.today()).year - 1


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
        self.Bind(wx.EVT_BUTTON, self._on_close_button, id=wx.ID_CLOSE)
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
        row.Add(b, 0, wx.RIGHT, 8)
        self.single_prev = wx.Button(p, label="Previous Day")
        self.single_next = wx.Button(p, label="Next Day")
        row.Add(self.single_prev, 0, wx.RIGHT, 8)
        row.Add(self.single_next, 0)
        s.Add(row, 0, wx.ALL, 8)
        self.single_lines = AccessibleLinesPanel(p, name="Single day results")
        s.Add(self.single_lines, 1, wx.EXPAND | wx.ALL, 8)
        p.SetSizer(s)
        self.nb.AddPage(p, "Single Day")
        b.Bind(wx.EVT_BUTTON, self.on_single)
        self.single_prev.Bind(wx.EVT_BUTTON, lambda e: self.on_single_step(-1))
        self.single_next.Bind(wx.EVT_BUTTON, lambda e: self.on_single_step(1))
        self.single_date.Bind(wx.adv.EVT_DATE_CHANGED, lambda e: self._update_single_buttons())
        self._limit_picker(self.single_date)
        self._update_single_buttons()

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
        row.Add(b, 0, wx.RIGHT, 8)
        # The window of years ends at my_end_year; these shift it a window at a time.
        self.my_end_year = multi_year_end_limit()
        self.my_prev = wx.Button(p)
        self.my_next = wx.Button(p)
        row.Add(self.my_prev, 0, wx.RIGHT, 8)
        row.Add(self.my_next, 0)
        s.Add(row, 0, wx.ALL, 8)
        self.my_lines = AccessibleLinesPanel(p, name="Multi-year results")
        s.Add(self.my_lines, 1, wx.EXPAND | wx.ALL, 8)
        p.SetSizer(s)
        self.nb.AddPage(p, "Multi-Year")
        b.Bind(wx.EVT_BUTTON, self.on_multiyear)
        self.my_prev.Bind(wx.EVT_BUTTON, lambda e: self.on_multiyear_step(-1))
        self.my_next.Bind(wx.EVT_BUTTON, lambda e: self.on_multiyear_step(1))
        self.my_years.Bind(wx.EVT_SPINCTRL, lambda e: self._update_multiyear_buttons())
        self._update_multiyear_buttons()

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
        # Step a whole range at a time, or jump the same range a year.
        nav = wx.BoxSizer(wx.HORIZONTAL)
        self.browse_prev = wx.Button(p)
        self.browse_next = wx.Button(p)
        nav.Add(self.browse_prev, 0, wx.RIGHT, 8)
        nav.Add(self.browse_next, 0, wx.RIGHT, 8)
        self.browse_prev_year = wx.Button(p, label="Previous Year")
        self.browse_next_year = wx.Button(p, label="Next Year")
        nav.Add(self.browse_prev_year, 0, wx.RIGHT, 8)
        nav.Add(self.browse_next_year, 0)
        s.Add(nav, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.browse_lines = AccessibleLinesPanel(p, name="Daily results")
        s.Add(self.browse_lines, 1, wx.EXPAND | wx.ALL, 8)
        p.SetSizer(s)
        self.nb.AddPage(p, "Daily Browse")
        b.Bind(wx.EVT_BUTTON, self.on_browse)
        self.browse_prev.Bind(wx.EVT_BUTTON, lambda e: self.on_browse_step(-1))
        self.browse_next.Bind(wx.EVT_BUTTON, lambda e: self.on_browse_step(1))
        self.browse_prev_year.Bind(wx.EVT_BUTTON, lambda e: self.on_browse_year(-1))
        self.browse_next_year.Bind(wx.EVT_BUTTON, lambda e: self.on_browse_year(1))
        self.browse_date.Bind(wx.adv.EVT_DATE_CHANGED, lambda e: self._update_browse_buttons())
        self.browse_days.Bind(wx.EVT_SPINCTRL, lambda e: self._update_browse_buttons())
        self._limit_picker(self.browse_date)
        self._update_browse_buttons()

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
        end_year = self.my_end_year
        self.settings["options"]["historical_years_back"] = years
        self._run(self.my_lines,
                  lambda lat, lon: historical_service.fetch_multi_year(
                      lat, lon, month, day, years, end_year=end_year))

    def on_browse(self, event):
        start = self._picker_date(self.browse_date)
        n = self.browse_days.GetValue()
        start_iso, end_iso = start.isoformat(), browse_end(start, n).isoformat()
        self._run(self.browse_lines,
                  lambda lat, lon: historical_service.fetch_range(lat, lon, start_iso, end_iso))

    # -- stepping -------------------------------------------------------------
    @staticmethod
    def _picker_date(picker):
        return date.fromisoformat(_wxdate_to_iso(picker.GetValue()))

    @staticmethod
    def _limit_picker(picker):
        picker.SetRange(_to_wxdate(ARCHIVE_START), _to_wxdate(date.today()))

    def _update_single_buttons(self):
        d = self._picker_date(self.single_date)
        self.single_prev.Enable(in_archive(d - timedelta(days=1)))
        self.single_next.Enable(in_archive(d + timedelta(days=1)))

    def on_single_step(self, days):
        new = self._picker_date(self.single_date) + timedelta(days=days)
        if not in_archive(new):
            return
        self.single_date.SetValue(_to_wxdate(new))
        self._update_single_buttons()
        self.on_single(None)

    def _update_multiyear_buttons(self):
        years = self.my_years.GetValue()
        self.my_prev.SetLabel(f"Previous {years} Years")
        self.my_next.SetLabel(f"Next {years} Years")
        # Previous stays available while the window still reaches 1940.
        self.my_prev.Enable(self.my_end_year - years >= ARCHIVE_START.year)
        self.my_next.Enable(self.my_end_year < multi_year_end_limit())
        self.my_prev.GetParent().Layout()

    def on_multiyear_step(self, direction):
        years = self.my_years.GetValue()
        end_year = min(self.my_end_year + direction * years, multi_year_end_limit())
        if end_year < ARCHIVE_START.year:
            return
        self.my_end_year = end_year
        self._update_multiyear_buttons()
        self.on_multiyear(None)

    def _browse_start(self):
        return self._picker_date(self.browse_date)

    def _update_browse_buttons(self):
        start = self._browse_start()
        n = self.browse_days.GetValue()
        unit = "Day" if n == 1 else "Days"
        self.browse_prev.SetLabel(f"Previous {n} {unit}")
        self.browse_next.SetLabel(f"Next {n} {unit}")
        self.browse_prev.Enable(in_archive(start - timedelta(days=n)))
        self.browse_next.Enable(in_archive(start + timedelta(days=n)))
        self.browse_prev_year.Enable(can_shift_browse_year(start, -1))
        self.browse_next_year.Enable(can_shift_browse_year(start, 1))
        self.browse_prev.GetParent().Layout()

    def on_browse_step(self, direction):
        n = self.browse_days.GetValue()
        new = self._browse_start() + timedelta(days=direction * n)
        if not in_archive(new):
            return
        self.browse_date.SetValue(_to_wxdate(new))
        self._update_browse_buttons()
        self.on_browse(None)

    def on_browse_year(self, years):
        start = self._browse_start()
        if not can_shift_browse_year(start, years):
            return
        new = shift_year(start, years)
        self.browse_date.SetValue(_to_wxdate(new))
        self._update_browse_buttons()
        self.on_browse(None)

    def _on_close_button(self, event):
        # EndModal rather than Close(): with Escape mapped to ID_CLOSE, Close()
        # sends EVT_CLOSE, whose default handler presses ID_CLOSE again, and
        # wx's re-entry guard then leaves the dialog open. Escape and the
        # title bar's X both come here too.
        self._alive = False
        self.EndModal(wx.ID_CLOSE)

    def _on_close(self, event):
        self._alive = False
        event.Skip()

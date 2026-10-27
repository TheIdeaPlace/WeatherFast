"""Marine forecast sheet: current waves, swell, currents, and sea temperature.

Marine data is only available for coastal/ocean points; inland coordinates
return empty values, which is reported clearly rather than as an error.
"""

import threading

import wx

from ...services import marine_service
from ..accessible_list import AccessibleLinesPanel
from ..formatters import degrees_to_cardinal

_FIELDS = [
    ("wave_height", "Wave Height", "m"),
    ("wave_direction", "Wave Direction", "dir"),
    ("wave_period", "Wave Period", "s"),
    ("wind_wave_height", "Wind Wave Height", "m"),
    ("swell_wave_height", "Swell Height", "m"),
    ("swell_wave_direction", "Swell Direction", "dir"),
    ("swell_wave_period", "Swell Period", "s"),
    ("ocean_current_velocity", "Current Velocity", "km/h"),
    ("ocean_current_direction", "Current Direction", "dir"),
    ("sea_surface_temperature", "Sea Surface Temp", "temp"),
]


class MarineDialog(wx.Dialog):
    def __init__(self, parent, center, fmt):
        super().__init__(parent, title=f"Marine Forecast - {center[0]}", size=(560, 480))
        self.center = center
        self.fmt = fmt
        self._alive = True

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.status = wx.StaticText(panel, label="Loading marine conditions...")
        vbox.Add(self.status, 0, wx.ALL, 8)
        self.lines = AccessibleLinesPanel(panel, name="Marine forecast")
        vbox.Add(self.lines, 1, wx.EXPAND | wx.ALL, 8)
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

        wx.CallAfter(self.load)

    def load(self):
        self.lines.set_message("Loading...")
        name, lat, lon = self.center

        def work():
            try:
                data = marine_service.fetch_marine_summary(lat, lon)
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._error, str(e))
                return
            wx.CallAfter(self._ready, data)

        threading.Thread(target=work, daemon=True).start()

    def _error(self, err):
        if not self._alive:
            return
        self.status.SetLabel(f"Error: {err}")
        self.lines.set_message(f"Error: {err}")

    def _ready(self, data):
        if not self._alive:
            return
        curr = data.get("current", {})
        lines = []
        any_value = False
        for key, label, kind in _FIELDS:
            v = curr.get(key)
            if v is None:
                continue
            any_value = True
            if kind == "temp":
                text = self.fmt.temperature(v)
            elif kind == "dir":
                text = f"{degrees_to_cardinal(v)} ({v:.0f}°)"
            else:
                text = f"{v:.1f} {kind}"
            lines.append(f"{label}: {text}")

        if not any_value:
            self.status.SetLabel("No marine data for this location (inland?).")
            self.lines.set_message("No marine data available for this location.")
            return
        self.status.SetLabel(f"Marine conditions near {self.center[0]}.")
        self.lines.set_lines(lines)
        self.lines.set_focus()

    def _on_close(self, event):
        self._alive = False
        event.Skip()

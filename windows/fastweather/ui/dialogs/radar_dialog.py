"""Expected Precipitation (nowcast) sheet - text timeline, no map."""

import threading

import wx

from ...services import radar_service
from ..accessible_list import AccessibleLinesPanel


class RadarDialog(wx.Dialog):
    def __init__(self, parent, center, fmt):
        super().__init__(parent, title=f"Expected Precipitation - {center[0]}", size=(560, 480))
        self.center = center
        self.fmt = fmt
        self._alive = True

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.status = wx.StaticText(panel, label="Loading nowcast...")
        vbox.Add(self.status, 0, wx.ALL, 8)
        self.lines = AccessibleLinesPanel(panel, name="Expected precipitation")
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
                nowcast = radar_service.fetch_nowcast(lat, lon)
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._error, str(e))
                return
            wx.CallAfter(self._ready, nowcast)

        threading.Thread(target=work, daemon=True).start()

    def _error(self, err):
        if not self._alive:
            return
        self.status.SetLabel("Error")
        self.lines.set_message(f"Error: {err}")

    def _ready(self, nowcast):
        if not self._alive:
            return
        self.status.SetLabel(nowcast.status)
        lines = [nowcast.status, "", "Next hour (15-minute steps):"]
        for pt in nowcast.timeline:
            when = "Now" if pt.minutes_from_now == 0 else f"+{pt.minutes_from_now} min"
            if pt.mm > 0:
                lines.append(f"  {when}: {pt.intensity} ({self.fmt.precipitation(pt.mm)})")
            else:
                lines.append(f"  {when}: None")
        lines.append("")
        lines.append("Source: Open-Meteo 15-minute nowcast")
        self.lines.set_lines(lines)
        self.lines.set_focus()

    def _on_close(self, event):
        self._alive = False
        event.Skip()

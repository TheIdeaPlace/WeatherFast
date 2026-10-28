"""Astronomy sheet: current moon phase, illumination, and upcoming phases."""

import wx

from ...services import astronomy
from ..accessible_list import AccessibleLinesPanel


class AstronomyDialog(wx.Dialog):
    def __init__(self, parent, center):
        super().__init__(parent, title=f"Astronomy - {center[0]}", size=(480, 360))
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        lines = AccessibleLinesPanel(panel, name="Moon")
        vbox.Add(lines, 1, wx.EXPAND | wx.ALL, 10)
        btns = wx.StdDialogButtonSizer()
        btns.AddButton(wx.Button(panel, wx.ID_CLOSE))
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        panel.SetSizer(vbox)
        self.Bind(wx.EVT_BUTTON, self._on_close_button, id=wx.ID_CLOSE)
        # Escape presses Close: without an escape id, a dialog with no Cancel
        # button ignores Escape.
        self.SetEscapeId(wx.ID_CLOSE)

        s = astronomy.summary()
        lines.set_lines([
            "Moon (today):",
            f"  Phase: {s['phase']}",
            f"  Illumination: {s['illumination_pct']}%",
            f"  Moon age: {s['age_days']} days",
            "",
            f"Next new moon: {s['next_new_moon']}",
            f"Next full moon: {s['next_full_moon']}",
        ])
        wx.CallAfter(lines.set_focus)

    def _on_close_button(self, event):
        # EndModal rather than Close(): with Escape mapped to ID_CLOSE, Close()
        # sends EVT_CLOSE, whose default handler presses ID_CLOSE again, and
        # wx's re-entry guard then leaves the dialog open. Escape and the
        # title bar's X both come here too.
        self._alive = False
        self.EndModal(wx.ID_CLOSE)

"""Per-city Weather Alerts sheet: browsable list -> single-alert detail.

Three clearly separated states on the list page: active alerts (severity-
sorted, selectable), no active alerts, and "couldn't check" (a fetch failure is
never shown as "no alerts").
"""

import threading

import wx

from ...services import alert_service
from ..accessible_list import AccessibleLinesPanel
from ..alert_format import detail_lines, summary_row


class AlertsDialog(wx.Dialog):
    def __init__(self, parent, center):
        super().__init__(parent, title=f"Weather Alerts - {center[0]}", size=(700, 560))
        self.center = center
        self.alerts = []
        self._alive = True

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.book = wx.Simplebook(panel)

        # List page
        list_page = wx.Panel(self.book)
        ls = wx.BoxSizer(wx.VERTICAL)
        self.status = wx.StaticText(list_page, label="Checking for alerts...")
        ls.Add(self.status, 0, wx.ALL, 8)
        self.list_box = wx.ListBox(list_page, style=wx.LB_SINGLE)
        ls.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 8)
        self.view_btn = wx.Button(list_page, label="View Details")
        self.view_btn.Disable()
        ls.Add(self.view_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 8)
        list_page.SetSizer(ls)

        # Detail page
        detail_page = wx.Panel(self.book)
        ds = wx.BoxSizer(wx.VERTICAL)
        self.back_btn = wx.Button(detail_page, label="<- Back to Alerts")
        ds.Add(self.back_btn, 0, wx.ALL, 8)
        self.detail = AccessibleLinesPanel(detail_page, name="Alert")
        ds.Add(self.detail, 1, wx.EXPAND | wx.ALL, 8)
        detail_page.SetSizer(ds)

        self.book.AddPage(list_page, "List")
        self.book.AddPage(detail_page, "Detail")
        vbox.Add(self.book, 1, wx.EXPAND)

        btns = wx.StdDialogButtonSizer()
        btns.AddButton(wx.Button(panel, wx.ID_CLOSE))
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        panel.SetSizer(vbox)

        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view)
        self.list_box.Bind(wx.EVT_LISTBOX, lambda e: self.view_btn.Enable(
            self.list_box.GetSelection() != wx.NOT_FOUND))
        self.list_box.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view)
        # Enter on the list opens the alert. It's caught at the dialog, so the
        # list keeps the system's Tab and Escape handling.
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.back_btn.Bind(wx.EVT_BUTTON, self.on_back)
        self.Bind(wx.EVT_BUTTON, self._on_close_button, id=wx.ID_CLOSE)
        # Escape presses Close: without an escape id, a dialog with no Cancel
        # button ignores Escape.
        self.SetEscapeId(wx.ID_CLOSE)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        wx.CallAfter(self.load)

    def load(self):
        self.list_box.Clear()
        self.list_box.Append("Checking...")
        name, lat, lon = self.center

        def work():
            try:
                alerts = alert_service.fetch_alerts(lat, lon)
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._error, str(e))
                return
            wx.CallAfter(self._ready, alerts)

        threading.Thread(target=work, daemon=True).start()

    def _error(self, err):
        if not self._alive:
            return
        self.status.SetLabel("Could not check alerts.")
        self.list_box.Clear()
        # Safety invariant: a failure is NOT "no alerts".
        self.list_box.Append("Could not check for weather alerts.")
        self.list_box.Append(f"Reason: {err}")
        self.list_box.Append("This does NOT mean there are no alerts - try again.")
        self.list_box.SetSelection(0)

    def _ready(self, alerts):
        if not self._alive:
            return
        self.alerts = alerts
        self.list_box.Clear()
        if not alerts:
            self.status.SetLabel("No active alerts.")
            self.list_box.Append(f"No active weather alerts for {self.center[0]}.")
            self.list_box.SetSelection(0)
            return
        self.status.SetLabel(
            f"{len(alerts)} active alert{'s' if len(alerts) != 1 else ''} - "
            "select one for details.")
        for a in alerts:
            self.list_box.Append(summary_row(a))
        self.list_box.SetSelection(0)
        self.view_btn.Enable()
        self.list_box.SetFocus()

    def _on_char_hook(self, event):
        if (event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
                and wx.Window.FindFocus() is self.list_box):
            self.on_view(event)
            return
        event.Skip()

    def on_view(self, event):
        sel = self.list_box.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self.alerts):
            return
        self.detail.set_lines(detail_lines(self.alerts[sel]))
        self.book.SetSelection(1)
        self.detail.set_focus()

    def on_back(self, event):
        self.book.SetSelection(0)
        self.list_box.SetFocus()

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

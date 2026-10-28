"""My Data: a user-configurable custom section of Open-Meteo parameters.

MyDataConfigDialog picks parameters (checkboxes grouped by category).
MyDataDialog shows the current value of each selected parameter, fetched across
the forecast / marine / air-quality endpoints. Selection persists in settings.
"""

import threading

import wx

from ...models import mydata
from ...services import mydata_service
from ..accessible_list import AccessibleLinesPanel


class MyDataConfigDialog(wx.Dialog):
    """Pick which parameters appear, grouped into category tabs."""

    def __init__(self, parent, selected_keys):
        super().__init__(parent, title="Choose My Data Parameters", size=(600, 620))
        self._checks = {}

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(panel, label="Select parameters to display:"), 0, wx.ALL, 8)

        nb = wx.Notebook(panel)
        for cat in mydata.categories():
            p = wx.ScrolledWindow(nb)
            p.SetScrollRate(0, 10)
            s = wx.BoxSizer(wx.VERTICAL)
            for param in mydata.params_in(cat):
                cb = wx.CheckBox(p, label=param.name)
                cb.SetValue(param.key in selected_keys)
                cb.SetToolTip(param.explanation)
                self._checks[param.key] = cb
                s.Add(cb, 0, wx.ALL, 4)
            p.SetSizer(s)
            nb.AddPage(p, cat)
        vbox.Add(nb, 1, wx.EXPAND | wx.ALL, 8)

        btns = wx.StdDialogButtonSizer()
        btns.AddButton(wx.Button(panel, wx.ID_OK))
        btns.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        panel.SetSizer(vbox)

    def selected_keys(self):
        """Return selected keys in catalog order."""
        return [p.key for p in mydata.CATALOG if self._checks[p.key].GetValue()]


class MyDataDialog(wx.Dialog):
    def __init__(self, parent, center, settings, fmt):
        super().__init__(parent, title=f"My Data - {center[0]}", size=(640, 560))
        self.center = center
        self.settings = settings
        self.fmt = fmt
        self._alive = True

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.choose_btn = wx.Button(panel, label="Choose Parameters...")
        self.refresh_btn = wx.Button(panel, label="Refresh")
        row.Add(self.choose_btn, 0, wx.RIGHT, 6)
        row.Add(self.refresh_btn, 0)
        vbox.Add(row, 0, wx.ALL, 8)

        self.status = wx.StaticText(panel, label="")
        vbox.Add(self.status, 0, wx.LEFT | wx.BOTTOM, 8)

        self.lines = AccessibleLinesPanel(panel, name="My data")
        vbox.Add(self.lines, 1, wx.EXPAND | wx.ALL, 8)

        btns = wx.StdDialogButtonSizer()
        btns.AddButton(wx.Button(panel, wx.ID_CLOSE))
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        panel.SetSizer(vbox)

        self.choose_btn.Bind(wx.EVT_BUTTON, self.on_choose)
        self.refresh_btn.Bind(wx.EVT_BUTTON, lambda e: self.load())
        self.Bind(wx.EVT_BUTTON, self._on_close_button, id=wx.ID_CLOSE)
        # Escape presses Close: without an escape id, a dialog with no Cancel
        # button ignores Escape.
        self.SetEscapeId(wx.ID_CLOSE)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        wx.CallAfter(self.load)

    def _selection(self):
        return self.settings["options"].get("mydata_selection", [])

    def on_choose(self, event):
        dlg = MyDataConfigDialog(self, self._selection())
        if dlg.ShowModal() == wx.ID_OK:
            self.settings["options"]["mydata_selection"] = dlg.selected_keys()
            self.load()
        dlg.Destroy()

    def load(self):
        keys = self._selection()
        if not keys:
            self.status.SetLabel("No parameters selected.")
            self.lines.set_message('Click "Choose Parameters..." to add data.')
            return
        params = [mydata.CATALOG_BY_KEY[k] for k in keys if k in mydata.CATALOG_BY_KEY]
        self.status.SetLabel("Loading...")
        self.lines.set_message("Loading...")
        self.refresh_btn.Disable()
        name, lat, lon = self.center

        def work():
            try:
                values, errors = mydata_service.fetch_mydata(lat, lon, params)
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._error, str(e))
                return
            wx.CallAfter(self._ready, params, values, errors)

        threading.Thread(target=work, daemon=True).start()

    def _error(self, err):
        if not self._alive:
            return
        self.refresh_btn.Enable()
        self.status.SetLabel(f"Error: {err}")
        self.lines.set_message(f"Error: {err}")

    def _ready(self, params, values, errors):
        if not self._alive:
            return
        self.refresh_btn.Enable()
        lines = []
        current_cat = None
        for p in params:
            if p.category != current_cat:
                current_cat = p.category
                lines.append(f"{current_cat}:")
            val = mydata.format_value(p, values.get(p.key), self.fmt)
            lines.append(f"  {p.name}: {val}")
        if errors:
            lines.append("")
            for group, msg in errors.items():
                lines.append(f"({group} unavailable: {msg})")
        self.status.SetLabel(f"My Data for {self.center[0]}.")
        self.lines.set_lines(lines)
        self.lines.set_focus()

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

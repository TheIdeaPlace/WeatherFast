"""Alert Browser: browse and filter national alert digests by region.

Flow (a Simplebook of pages, each with Back and managed focus):
  Region picker -> filtered digest (severity + hazard) -> group areas -> detail.
The digest collapses many area-level products into one row per severity|event
with an area count, matching the iOS alert browser. Filter defaults are seeded
from settings and can be saved back.
"""

import threading

import wx

from ...models import alert as A
from ...services import alert_browser_service as svc
from ..accessible_list import AccessibleLinesPanel
from ..alert_format import detail_lines, fmt_time

_ALL_TYPES = "All types"


class AlertBrowserDialog(wx.Dialog):
    def __init__(self, parent, settings):
        super().__init__(parent, title="Browse Weather Alerts", size=(760, 620))
        self.settings = settings
        self.region_alerts = []
        self.groups = []
        self.current_group = None
        self.severity_filter = "All"
        self.hazard_filter = None
        self._alive = True
        self._enter_handlers = {}   # list -> what Enter on it does (the pages fill it)
        self._load_state = "idle"   # idle | loading | error | ok, for the region shown

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.book = wx.Simplebook(panel)
        self._build_region_page()
        self._build_digest_page()
        self._build_group_page()
        self._build_detail_page()
        vbox.Add(self.book, 1, wx.EXPAND)

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
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        wx.CallAfter(self._load_counts)

    # -- region page ----------------------------------------------------------
    def _build_region_page(self):
        p = wx.Panel(self.book)
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(p, label="Choose a region to browse active alerts:"),
              0, wx.ALL, 8)
        self.region_list = wx.ListBox(p, style=wx.LB_SINGLE)
        for r in svc.REGIONS:
            self.region_list.Append(r["name"])
        self.region_list.SetSelection(0)
        s.Add(self.region_list, 1, wx.EXPAND | wx.ALL, 8)
        b = wx.Button(p, label="Browse Alerts")
        s.Add(b, 0, wx.ALIGN_CENTER | wx.BOTTOM, 8)
        p.SetSizer(s)
        self.book.AddPage(p, "Regions")
        b.Bind(wx.EVT_BUTTON, self.on_pick_region)
        self.region_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_pick_region)
        self._bind_enter(self.region_list, self.on_pick_region)

    def _load_counts(self):
        def work():
            counts = {}
            for r in svc.REGIONS:
                counts[r["id"]] = svc.alert_count(r["id"])
            wx.CallAfter(self._apply_counts, counts)
        threading.Thread(target=work, daemon=True).start()

    def _apply_counts(self, counts):
        if not self._alive:
            return
        for i, r in enumerate(svc.REGIONS):
            n = counts.get(r["id"])
            label = r["name"]
            if n is not None:
                label += f"  ({n} active)"
            self.region_list.SetString(i, label)

    # -- digest page ----------------------------------------------------------
    def _build_digest_page(self):
        p = wx.Panel(self.book)
        s = wx.BoxSizer(wx.VERTICAL)
        top = wx.BoxSizer(wx.HORIZONTAL)
        self.digest_back = wx.Button(p, label="<- Regions")
        top.Add(self.digest_back, 0, wx.RIGHT, 8)
        self.digest_title = wx.StaticText(p, label="Alerts")
        top.Add(self.digest_title, 1, wx.ALIGN_CENTER_VERTICAL)
        s.Add(top, 0, wx.EXPAND | wx.ALL, 8)

        filt = wx.BoxSizer(wx.HORIZONTAL)
        self.sev_radio = wx.RadioBox(p, label="Severity", choices=A.SEVERITY_FILTERS,
                                     style=wx.RA_SPECIFY_COLS)
        filt.Add(self.sev_radio, 0, wx.RIGHT, 8)
        haz_box = wx.BoxSizer(wx.VERTICAL)
        haz_box.Add(wx.StaticText(p, label="Hazard type:"), 0)
        self.hazard_choice = wx.Choice(p, choices=[_ALL_TYPES])
        haz_box.Add(self.hazard_choice, 0)
        self.save_btn = wx.Button(p, label="Save Current Filters as Default")
        haz_box.Add(self.save_btn, 0, wx.TOP, 6)
        filt.Add(haz_box, 0)
        s.Add(filt, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.digest_status = wx.StaticText(p, label="")
        s.Add(self.digest_status, 0, wx.LEFT | wx.BOTTOM, 8)
        self.group_list = wx.ListBox(p, style=wx.LB_SINGLE)
        s.Add(self.group_list, 1, wx.EXPAND | wx.ALL, 8)
        self.open_group_btn = wx.Button(p, label="View Affected Areas")
        self.open_group_btn.Disable()
        s.Add(self.open_group_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 8)
        p.SetSizer(s)
        self.book.AddPage(p, "Digest")

        self.digest_back.Bind(wx.EVT_BUTTON, lambda e: self._goto(0, self.region_list))
        self.sev_radio.Bind(wx.EVT_RADIOBOX, self.on_filter_change)
        self.hazard_choice.Bind(wx.EVT_CHOICE, self.on_filter_change)
        self.save_btn.Bind(wx.EVT_BUTTON, self.on_save_defaults)
        self.group_list.Bind(wx.EVT_LISTBOX, lambda e: self.open_group_btn.Enable(
            self.group_list.GetSelection() != wx.NOT_FOUND))
        self.group_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open_group)
        self._bind_enter(self.group_list, self.on_open_group)
        self.open_group_btn.Bind(wx.EVT_BUTTON, self.on_open_group)

    # -- group page -----------------------------------------------------------
    def _build_group_page(self):
        p = wx.Panel(self.book)
        s = wx.BoxSizer(wx.VERTICAL)
        self.group_back = wx.Button(p, label="<- Alerts")
        s.Add(self.group_back, 0, wx.ALL, 8)
        self.group_title = wx.StaticText(p, label="")
        s.Add(self.group_title, 0, wx.LEFT | wx.BOTTOM, 8)
        self.area_list = wx.ListBox(p, style=wx.LB_SINGLE)
        s.Add(self.area_list, 1, wx.EXPAND | wx.ALL, 8)
        self.open_area_btn = wx.Button(p, label="View Details")
        self.open_area_btn.Disable()
        s.Add(self.open_area_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 8)
        p.SetSizer(s)
        self.book.AddPage(p, "Group")

        self.group_back.Bind(wx.EVT_BUTTON, lambda e: self._goto(1, self.group_list))
        self.area_list.Bind(wx.EVT_LISTBOX, lambda e: self.open_area_btn.Enable(
            self.area_list.GetSelection() != wx.NOT_FOUND))
        self.area_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open_area)
        self._bind_enter(self.area_list, self.on_open_area)
        self.open_area_btn.Bind(wx.EVT_BUTTON, self.on_open_area)

    # -- detail page ----------------------------------------------------------
    def _build_detail_page(self):
        p = wx.Panel(self.book)
        s = wx.BoxSizer(wx.VERTICAL)
        self.detail_back = wx.Button(p, label="<- Areas")
        s.Add(self.detail_back, 0, wx.ALL, 8)
        self.detail = AccessibleLinesPanel(p, name="Alert")
        s.Add(self.detail, 1, wx.EXPAND | wx.ALL, 8)
        p.SetSizer(s)
        self.book.AddPage(p, "Detail")
        self.detail_back.Bind(wx.EVT_BUTTON, lambda e: self._goto(2, self.area_list))

    def _goto(self, page, focus_ctrl=None):
        self.book.SetSelection(page)
        if focus_ctrl is not None:
            focus_ctrl.SetFocus()

    def _bind_enter(self, ctrl, handler):
        """Enter on a list advances to the next level (as elsewhere in the app).

        Enter is caught at the dialog (EVT_CHAR_HOOK) before the dialog's own
        navigation sees it, so the lists keep the system's Tab handling. They
        used to be WANTS_CHARS with Tab re-implemented, and Tab from the filter
        buttons could skip straight past the alert list.
        """
        self._enter_handlers[ctrl] = handler

    def _on_char_hook(self, evt):
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            handler = self._enter_handlers.get(wx.Window.FindFocus())
            if handler is not None:
                handler(evt)
                return
        evt.Skip()

    # -- region selected ------------------------------------------------------
    def on_pick_region(self, event):
        sel = self.region_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        region = svc.REGIONS[sel]
        self.current_region = region
        # Forget the last region's groups: with "Loading..." selected, Enter
        # would otherwise open the previous region's first alert.
        self.groups = []
        self.region_alerts = []
        self._load_state = "loading"
        self.open_group_btn.Disable()
        self.digest_title.SetLabel(f"{region['name']} - active alerts")
        self.digest_status.SetLabel("Loading alerts...")
        self.group_list.Clear()
        self.group_list.Append("Loading...")
        self.group_list.SetSelection(0)
        # Focus the alert list now: leaving it on the hidden region list meant
        # the screen reader said nothing at all when the page changed.
        self._goto(1, self.group_list)

        def work():
            try:
                alerts = svc.fetch_region_alerts(region["id"])
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._region_error, region["id"], str(e))
                return
            wx.CallAfter(self._region_ready, region["id"], alerts)

        threading.Thread(target=work, daemon=True).start()

    def _is_current(self, region_id):
        """A late result for a region you've since left is dropped."""
        return (self._alive and getattr(self, "current_region", None) is not None
                and self.current_region["id"] == region_id)

    def _region_error(self, region_id, err):
        if not self._is_current(region_id):
            return
        self._load_state = "error"
        self.digest_status.SetLabel("Could not load alerts.")
        self.group_list.Clear()
        self.group_list.Append(f"Could not load alerts: {err}")
        self.group_list.Append("This does NOT mean there are none - try again.")
        self.group_list.SetSelection(0)

    def _region_ready(self, region_id, alerts):
        if not self._is_current(region_id):
            return
        self._load_state = "ok"
        self.region_alerts = alerts
        # Seed filters from saved defaults (once per open is fine here).
        opts = self.settings["options"]
        self.severity_filter = opts.get("default_alert_severity_filter", "All")
        if self.severity_filter not in A.SEVERITY_FILTERS:
            self.severity_filter = "All"
        self.sev_radio.SetStringSelection(self.severity_filter)
        self.hazard_filter = opts.get("default_alert_hazard_type") or None
        self._rebuild_hazard_choice()
        self._rebuild_groups()

    def _rebuild_hazard_choice(self):
        present = A.hazard_counts(self.region_alerts)
        items = [_ALL_TYPES]
        for h in A.HAZARD_ORDER:
            if present.get(h):
                items.append(f"{h} ({present[h]})")
        self.hazard_choice.Set(items)
        # restore selection
        if self.hazard_filter:
            for i, it in enumerate(items):
                if it.startswith(self.hazard_filter + " ") or it == self.hazard_filter:
                    self.hazard_choice.SetSelection(i)
                    break
            else:
                self.hazard_choice.SetSelection(0)
                self.hazard_filter = None
        else:
            self.hazard_choice.SetSelection(0)

    def on_filter_change(self, event):
        if self._load_state != "ok":
            # Nothing to filter yet (loading, or the load failed): rebuilding
            # now would claim "No active alerts", which isn't known.
            return
        self.severity_filter = self.sev_radio.GetStringSelection()
        sel = self.hazard_choice.GetStringSelection()
        self.hazard_filter = None if sel == _ALL_TYPES else sel.rsplit(" (", 1)[0]
        self._rebuild_groups()

    def _rebuild_groups(self):
        self.groups = A.build_digest(self.region_alerts, self.severity_filter, self.hazard_filter)
        self.group_list.Clear()
        if not self.region_alerts:
            self.digest_status.SetLabel("No active alerts right now.")
            self.group_list.Append("No active alerts for this region.")
            self.group_list.SetSelection(0)  # selected, so it's read on arrival
            self.open_group_btn.Disable()
            return
        if not self.groups:
            self.digest_status.SetLabel("No alerts match this filter.")
            self.group_list.Append("No alerts match. Try All severities or All types.")
            self.group_list.SetSelection(0)
            self.open_group_btn.Disable()
            return
        total = sum(g.count for g in self.groups)
        self.digest_status.SetLabel(
            f"{len(self.groups)} alert types, {total} areas "
            f"(severity: {self.severity_filter}"
            + (f", {self.hazard_filter}" if self.hazard_filter else "") + ")")
        for g in self.groups:
            until = fmt_time(g.soonest_expires.isoformat()) if g.soonest_expires else ""
            label = f"[{g.severity}] {g.event}  -  {g.count} area{'s' if g.count != 1 else ''}"
            if until:
                label += f"  (soonest until {until})"
            self.group_list.Append(label)
        self.group_list.SetSelection(0)
        self.open_group_btn.Enable()

    def on_save_defaults(self, event):
        self.settings["options"]["default_alert_severity_filter"] = self.severity_filter
        self.settings["options"]["default_alert_hazard_type"] = self.hazard_filter or ""
        self.save_btn.SetLabel("Saved as Default")
        wx.CallLater(2000, lambda: self.save_btn.SetLabel("Save Current Filters as Default")
                     if self._alive else None)

    # -- group -> areas -------------------------------------------------------
    def on_open_group(self, event):
        sel = self.group_list.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self.groups):
            return
        group = self.groups[sel]
        self.current_group = group
        self.group_title.SetLabel(f"[{group.severity}] {group.event} - {group.count} areas")
        self.area_list.Clear()
        for a in group.alerts:
            until = fmt_time(a.ends) if a.ends else ""
            label = a.area or a.event
            if until:
                label += f"  (until {until})"
            self.area_list.Append(label)
        self.area_list.SetSelection(0)
        self.open_area_btn.Enable()
        self._goto(2, self.area_list)

    def on_open_area(self, event):
        sel = self.area_list.GetSelection()
        if not self.current_group or sel == wx.NOT_FOUND or sel >= len(self.current_group.alerts):
            return
        self.detail.set_lines(detail_lines(self.current_group.alerts[sel]))
        self._goto(3, None)
        self.detail.set_focus()

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

"""Search-results dialog: an arrow-through list of geocoding matches.

Shown for every non-empty search (including a single result), so keyboard and
screen-reader users always get the same selectable list to review and confirm,
rather than a place being added silently.
"""

import wx


class CitySelectionDialog(wx.Dialog):
    def __init__(self, parent, matches, original_input):
        super().__init__(parent, title="Search Results", size=(620, 420))
        self.matches = matches
        self.selected_match = None

        n = len(matches)
        if n == 1:
            prompt = (f"1 result for '{original_input}'. "
                      "Press Enter to add it, or Escape to cancel.")
        else:
            prompt = (f"{n} results for '{original_input}'. "
                      "Use the arrow keys to choose, then press Enter to add.")

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(panel, label=prompt), 0, wx.ALL, 10)

        self.city_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        for match in matches:
            self.city_list.Append(match["display"])
        if matches:
            self.city_list.SetSelection(0)

        vbox.Add(self.city_list, 1, wx.EXPAND | wx.ALL, 10)

        btns = wx.StdDialogButtonSizer()
        add_btn = wx.Button(panel, wx.ID_OK, "Add")
        # The default button, so Enter in the list adds the selected place, as
        # the prompt says. The list's own key handler never saw Enter: a dialog
        # takes it for its default button, and there wasn't one.
        add_btn.SetDefault()
        btns.AddButton(add_btn)
        btns.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        panel.SetSizer(vbox)

        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.city_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_ok)
        # Land focus on the list so a screen reader starts on the results.
        wx.CallAfter(self.city_list.SetFocus)

    def on_ok(self, event):
        sel = self.city_list.GetSelection()
        if sel != wx.NOT_FOUND:
            self.selected_match = self.matches[sel]
            self.EndModal(wx.ID_OK)
        else:
            event.Skip()

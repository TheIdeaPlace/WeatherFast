"""Reusable screen-reader-friendly "ListBox of lines" widget.

This is the accessibility backbone: weather data is rendered as individual
list items so screen-reader users navigate datum-by-datum with the arrow keys.
Empty and separator (---/===) lines are filtered out, matching the monolith.
"""

import wx


def _is_visible_line(line):
    stripped = line.strip()
    return bool(stripped) and not all(c in "-=" for c in stripped)


class _ListName(wx.Accessible):
    """Name a list box for screen readers.

    A Win32 list box has no name of its own: screen readers borrow the
    nearest label, so result lists were read as "List box" with no name, or
    under the wrong label ("Years back: List box" in Historical Weather).
    ``SetName`` doesn't reach MSAA, so the name comes from here. childId 0 is
    the list itself; its rows defer to wx, so each row still reads as its own
    text.
    """

    def __init__(self, window, label):
        super().__init__(window)
        self._label = label

    def GetName(self, childId):
        if childId:
            return (wx.ACC_NOT_IMPLEMENTED, "")
        return (wx.ACC_OK, self._label)


def name_list(listbox, label):
    """Give a wx.ListBox (or any control) a screen reader name."""
    listbox.SetName(label)
    try:
        acc = _ListName(listbox, label)
        listbox.SetAccessible(acc)
        listbox._fw_accessible = acc  # keep it alive as long as the control
    except (NotImplementedError, AttributeError):
        pass  # a wx build without accessibility support: keep the default


class AccessibleLinesPanel(wx.Panel):
    """A monospace single-select ListBox that renders a list of text lines."""

    def __init__(self, parent, activatable=False, name=None):
        """``activatable`` enables Enter on rows carrying a payload (see
        set_lines). It is opt-in because it requires wx.WANTS_CHARS, which
        stops Enter from reaching a dialog's default button; panels that are
        pure output keep the plain style and their existing key behavior.

        ``name`` is what a screen reader calls the list ("Moon", "Results").
        """
        super().__init__(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        # HSCROLL: alert text is rendered a whole paragraph per row, which can
        # run well past the window width.
        style = wx.LB_SINGLE | wx.LB_HSCROLL
        if activatable:
            style |= wx.WANTS_CHARS
        self.listbox = wx.ListBox(self, style=style)
        self.listbox.SetFont(
            wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        )
        sizer.Add(self.listbox, 1, wx.EXPAND)
        self.SetSizer(sizer)
        if name:
            name_list(self.listbox, name)

        self._row_data = {}       # listbox row -> caller payload
        self._on_activate = None
        if activatable:
            self.listbox.Bind(wx.EVT_KEY_DOWN, self._on_key)
            self.listbox.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._activate())

    def set_lines(self, lines, row_data=None, keep_selection=False):
        """Replace contents with the given lines (filtered for accessibility).

        ``row_data`` optionally maps an index in ``lines`` to a payload for that
        line; indexes are re-keyed to surviving rows so filtering can't misalign
        them. Activating such a row (Enter or double-click) invokes the handler
        registered with set_activate_handler().

        ``keep_selection`` re-selects the previously selected line by its text
        rather than its index, so a background refresh that inserts lines above
        the reading position doesn't move the user.
        """
        visible, data = [], {}
        for i, line in enumerate(lines):
            if not _is_visible_line(line):
                continue
            if row_data and i in row_data:
                data[len(visible)] = row_data[i]
            visible.append(line)
        if keep_selection and visible == list(self.listbox.GetStrings()):
            # Nothing changed (a refresh that brought the same report): leave
            # the list alone. Rebuilding it made the screen reader re-read the
            # current line once per refresh.
            self._row_data = data
            return
        prev = (self.listbox.GetStringSelection()
                if keep_selection and self.listbox.GetSelection() != wx.NOT_FOUND
                else None)
        self.listbox.Clear()
        self._row_data = data
        if visible:
            self.listbox.Append(visible)
        if self.listbox.GetCount() > 0:
            restored = self.listbox.FindString(prev) if prev else wx.NOT_FOUND
            self.listbox.SetSelection(restored if restored != wx.NOT_FOUND else 0)

    def set_activate_handler(self, handler):
        """Register ``handler(payload)`` for Enter / double-click on data rows."""
        self._on_activate = handler

    def _activate(self):
        """Fire the handler for the selected row; True if the row had one."""
        payload = self._row_data.get(self.listbox.GetSelection())
        if payload is None or not self._on_activate:
            return False
        self._on_activate(payload)
        return True

    def _on_key(self, event):
        """Enter activates a data row; Tab is re-implemented because
        WANTS_CHARS also intercepts it, which would trap focus in the list."""
        kc = event.GetKeyCode()
        if kc in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            if self._activate():
                return
            event.Skip()
        elif kc == wx.WXK_TAB:
            flags = (wx.NavigationKeyEvent.IsBackward if event.ShiftDown()
                     else wx.NavigationKeyEvent.IsForward)
            self.listbox.Navigate(flags)
        else:
            event.Skip()

    def set_message(self, text):
        """Show a single status line (e.g. 'Loading...' or an error)."""
        self.listbox.Clear()
        self._row_data = {}
        self.listbox.Append(text)

    def append(self, text):
        self.listbox.Append(text)

    def clear(self):
        self.listbox.Clear()
        self._row_data = {}

    def set_focus(self):
        self.listbox.SetFocus()

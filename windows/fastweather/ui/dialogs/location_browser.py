"""Browse cities by US state or country, with sorting and region favorites."""

import threading
from concurrent.futures import ThreadPoolExecutor

import wx

from ... import browse_favorites
from ...services import weather_service
from ..city_row import city_row_text

class _CheckList(wx.ListCtrl):
    """A one-column list of checkable rows that screen readers can read.

    It replaces wx.CheckListBox, whose check boxes are drawn by wx and never
    reach MSAA or UI Automation: Space checked a city silently, and arrowing
    back gave no hint which cities were checked. A native list view with
    check boxes is read as "checked" / "not checked" by JAWS, NVDA and
    Narrator, and Space toggles the focused row. The methods mirror the
    CheckListBox ones the dialog used.
    """

    def __init__(self, parent):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL)
        self.EnableCheckBoxes(True)
        self.InsertColumn(0, "City")
        self._data = []
        self.Bind(wx.EVT_SIZE, self._on_size)

    def _on_size(self, event):
        self.SetColumnWidth(0, max(100, self.GetClientSize().width - 4))
        event.Skip()

    def Clear(self):
        self.DeleteAllItems()
        self._data = []

    def Append(self, label, data=None):
        i = self.InsertItem(self.GetItemCount(), label)
        self._data.append(data)
        if i == 0:
            # Select and focus the first row, so arriving in the list reads a
            # city rather than an empty list.
            self.SetItemState(0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                              wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
        return i

    def GetCount(self):
        return self.GetItemCount()

    def SetLabelFor(self, data, label):
        """Change the text of the row holding ``data``, in place."""
        for i, d in enumerate(self._data):
            if d is data:
                if self.GetItemText(i) != label:
                    self.SetItemText(i, label)
                return

    def GetClientData(self, i):
        return self._data[i]

    def Check(self, i, check=True):
        self.CheckItem(i, check)

    def IsChecked(self, i):
        return self.IsItemChecked(i)


_LIST_LABEL = "Select cities to add (check multiple cities):"

_SORTS = [
    "Name (A-Z)", "Name (Z-A)",
    "North to South", "South to North",
    "East to West", "West to East",
    "Temperature (Warm-Cold)", "Temperature (Cold-Warm)",
]


class LocationBrowserDialog(wx.Dialog):
    """Browse cities by US State or country; multi-select add, sort, favorites."""

    def __init__(self, parent, us_cities_cache, intl_cities_cache, favorites=None, fmt=None):
        super().__init__(parent, title="Browse Cities by Location", size=(720, 640))
        self.us_cities_cache = us_cities_cache
        self.intl_cities_cache = intl_cities_cache
        self.favorites = list(favorites or [])
        self.fmt = fmt
        self.selected_cities = []
        self.loaded_cities = []           # list of dicts for the current region
        self.loaded_region = None         # (kind, region_name)
        self._alive = True
        self._weather_pending = 0   # cities whose weather hasn't arrived yet
        self._sort_waiting = False  # a Temperature sort waiting for that weather

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.notebook = wx.Notebook(panel)
        self._build_us_tab()
        self._build_intl_tab()
        self._build_fav_tab()
        vbox.Add(self.notebook, 0, wx.EXPAND | wx.ALL, 8)

        # Sort + favorite row
        ctrl_row = wx.BoxSizer(wx.HORIZONTAL)
        ctrl_row.Add(wx.StaticText(panel, label="Sort:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.sort_choice = wx.Choice(panel, choices=_SORTS)
        self.sort_choice.SetSelection(0)
        ctrl_row.Add(self.sort_choice, 0, wx.RIGHT, 8)
        self.fav_btn = wx.Button(panel, label="Add Region to Favorites")
        self.fav_btn.Disable()
        ctrl_row.Add(self.fav_btn, 0)
        vbox.Add(ctrl_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.list_label = wx.StaticText(panel, label=_LIST_LABEL)
        vbox.Add(self.list_label, 0, wx.LEFT | wx.RIGHT, 8)
        self.cities_list = _CheckList(panel)
        vbox.Add(self.cities_list, 1, wx.EXPAND | wx.ALL, 8)

        sel_box = wx.BoxSizer(wx.HORIZONTAL)
        self.select_all_btn = wx.Button(panel, label="Select All")
        self.deselect_all_btn = wx.Button(panel, label="Deselect All")
        sel_box.Add(self.select_all_btn, 0, wx.RIGHT, 5)
        sel_box.Add(self.deselect_all_btn, 0)
        vbox.Add(sel_box, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        btns = wx.StdDialogButtonSizer()
        btns.AddButton(wx.Button(panel, wx.ID_OK, "Add Selected Cities"))
        btns.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        panel.SetSizer(vbox)

        self.Bind(wx.EVT_BUTTON, self.on_load_state, self.load_state_btn)
        self.Bind(wx.EVT_BUTTON, self.on_load_country, self.load_country_btn)
        self.Bind(wx.EVT_BUTTON, self.on_select_all, self.select_all_btn)
        self.Bind(wx.EVT_BUTTON, self.on_deselect_all, self.deselect_all_btn)
        self.Bind(wx.EVT_BUTTON, self.on_add_cities, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.on_toggle_favorite, self.fav_btn)
        self.sort_choice.Bind(wx.EVT_CHOICE, lambda e: self._populate())
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _build_us_tab(self):
        us_panel = wx.Panel(self.notebook)
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(us_panel, label="Select a U.S. State:"), 0, wx.ALL, 10)
        self.state_choice = wx.Choice(us_panel)
        if self.us_cities_cache:
            self.state_choice.Append("-- Select a State --")
            for state in sorted(self.us_cities_cache.keys()):
                self.state_choice.Append(state)
            self.state_choice.SetSelection(0)
        s.Add(self.state_choice, 0, wx.EXPAND | wx.ALL, 10)
        self.load_state_btn = wx.Button(us_panel, label="Load Cities")
        s.Add(self.load_state_btn, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        us_panel.SetSizer(s)
        self.notebook.AddPage(us_panel, "U.S. States")

    def _build_intl_tab(self):
        intl_panel = wx.Panel(self.notebook)
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(intl_panel, label="Select a Country:"), 0, wx.ALL, 10)
        self.country_choice = wx.Choice(intl_panel)
        if self.intl_cities_cache:
            self.country_choice.Append("-- Select a Country --")
            for country in sorted(self.intl_cities_cache.keys()):
                self.country_choice.Append(country)
            self.country_choice.SetSelection(0)
        s.Add(self.country_choice, 0, wx.EXPAND | wx.ALL, 10)
        self.load_country_btn = wx.Button(intl_panel, label="Load Cities")
        s.Add(self.load_country_btn, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        intl_panel.SetSizer(s)
        self.notebook.AddPage(intl_panel, "International")

    def _build_fav_tab(self):
        p = wx.Panel(self.notebook)
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(p, label="Favorite regions:"), 0, wx.ALL, 10)
        self.fav_list = wx.ListBox(p, style=wx.LB_SINGLE)
        self._refresh_fav_list()
        s.Add(self.fav_list, 1, wx.EXPAND | wx.ALL, 10)
        load_fav = wx.Button(p, label="Load Favorite")
        s.Add(load_fav, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        p.SetSizer(s)
        self.notebook.AddPage(p, "Favorites")
        load_fav.Bind(wx.EVT_BUTTON, self.on_load_favorite)

    def _refresh_fav_list(self):
        self.fav_list.Clear()
        for f in self.favorites:
            label = f"{'US' if f['kind'] == 'us' else 'Intl'}: {f['region']}"
            self.fav_list.Append(label)

    # -- loading regions ------------------------------------------------------
    def on_load_state(self, event):
        sel = self.state_choice.GetSelection()
        if sel <= 0 or sel == wx.NOT_FOUND:
            wx.MessageBox("Please select a state", "No Selection", wx.OK | wx.ICON_WARNING)
            return
        self._load_region("us", self.state_choice.GetString(sel))

    def on_load_country(self, event):
        sel = self.country_choice.GetSelection()
        if sel <= 0 or sel == wx.NOT_FOUND:
            wx.MessageBox("Please select a country", "No Selection", wx.OK | wx.ICON_WARNING)
            return
        self._load_region("intl", self.country_choice.GetString(sel))

    def on_load_favorite(self, event):
        sel = self.fav_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        fav = self.favorites[sel]
        self._load_region(fav["kind"], fav["region"])

    def _load_region(self, kind, region):
        cache = self.us_cities_cache if kind == "us" else self.intl_cities_cache
        if not cache or region not in cache:
            wx.MessageBox("No data for that region.", "Unavailable", wx.OK | wx.ICON_WARNING)
            return
        self.loaded_region = (kind, region)
        self.loaded_cities = []
        for c in cache[region]:
            parts = [c["name"]]
            if c.get("state"):
                parts.append(c["state"])
            parts.append(c.get("country", region))
            self.loaded_cities.append({
                "name": c["name"], "lat": c["lat"], "lon": c["lon"],
                "state": c.get("state", ""), "country": c.get("country", region),
                "display": ", ".join(parts), "temp": None, "row": None,
            })
        self._update_fav_button()
        self._sort_waiting = False
        self._fetch_weather(self.loaded_cities)
        self._populate()
        # Go to the cities: Load Cities used to fill the list silently and leave
        # focus on the button.
        self.cities_list.SetFocus()

    def _update_fav_button(self):
        if not self.loaded_region:
            self.fav_btn.Disable()
            return
        self.fav_btn.Enable()
        kind, region = self.loaded_region
        fav = browse_favorites.is_favorite(self.favorites, kind, region)
        self.fav_btn.SetLabel("Remove Region from Favorites" if fav
                              else "Add Region to Favorites")

    def on_toggle_favorite(self, event):
        if not self.loaded_region:
            return
        kind, region = self.loaded_region
        self.favorites, _ = browse_favorites.toggle(self.favorites, kind, region)
        self._refresh_fav_list()
        self._update_fav_button()

    # -- sorting + populate ---------------------------------------------------
    def _populate(self):
        if not self.loaded_cities:
            return
        sort = self.sort_choice.GetStringSelection()
        if sort.startswith("Temperature") and self._weather_pending:
            # Sorted once every city's weather is in (_weather_ready).
            self._sort_waiting = True
            self.list_label.SetLabel("Getting the weather, then sorting by temperature...")
            if not self.cities_list.GetCount():
                self._fill_list(self._sorted("Name (A-Z)"))
            return
        self._fill_list(self._sorted(sort))

    def _sorted(self, sort):
        cities = list(self.loaded_cities)
        if sort == "Name (A-Z)":
            cities.sort(key=lambda c: c["display"].lower())
        elif sort == "Name (Z-A)":
            cities.sort(key=lambda c: c["display"].lower(), reverse=True)
        elif sort == "North to South":
            cities.sort(key=lambda c: c["lat"], reverse=True)
        elif sort == "South to North":
            cities.sort(key=lambda c: c["lat"])
        elif sort == "East to West":
            cities.sort(key=lambda c: c["lon"], reverse=True)
        elif sort == "West to East":
            cities.sort(key=lambda c: c["lon"])
        elif sort == "Temperature (Warm-Cold)":
            cities.sort(key=lambda c: (c["temp"] is None, -(c["temp"] or 0)))
        elif sort == "Temperature (Cold-Warm)":
            cities.sort(key=lambda c: (c["temp"] is None, c["temp"] or 0))
        return cities

    def _fill_list(self, cities):
        # Keep what was checked when the list is re-sorted.
        checked = {id(self.cities_list.GetClientData(i))
                   for i in range(self.cities_list.GetCount())
                   if self.cities_list.IsChecked(i)}
        self.list_label.SetLabel(_LIST_LABEL)
        self.cities_list.Clear()
        for c in cities:
            i = self.cities_list.Append(c["row"] or c["display"], c)
            if id(c) in checked:
                self.cities_list.Check(i, True)

    def _fetch_weather(self, cities):
        """Get today's weather for every city in the region, so each row says
        what it's like there ("Algoma, ... - 45°F, Overcast (High: ..., Low:
        ...)"), as the Your Cities list does. Rows fill in as results arrive;
        the text changes in place, so checks and position are kept. Before,
        only a Temperature sort fetched anything, and then only the
        temperature."""
        self._weather_pending = len(cities)
        if not cities:
            return

        def one(c):
            try:
                data = weather_service.fetch_weather(c["lat"], c["lon"], "basic")
            except Exception:  # noqa: BLE001 - a city without weather keeps its name
                data = None
            wx.CallAfter(self._weather_ready, cities, c, data)

        def work():
            with ThreadPoolExecutor(max_workers=8) as ex:
                list(ex.map(one, cities))

        threading.Thread(target=work, daemon=True).start()

    def _weather_ready(self, cities, c, data):
        # A result for a region that's no longer loaded is dropped.
        if not self._alive or cities is not self.loaded_cities:
            return
        if data:
            c["temp"] = (data.get("current") or {}).get("temperature_2m")
            if self.fmt:
                c["row"] = city_row_text(c["display"], data, self.fmt)
            if c["row"]:
                self.cities_list.SetLabelFor(c, c["row"])
        self._weather_pending -= 1
        if self._weather_pending == 0 and self._sort_waiting:
            self._sort_waiting = False
            self._fill_list(self._sorted(self.sort_choice.GetStringSelection()))

    # -- selection ------------------------------------------------------------
    def on_select_all(self, event):
        for i in range(self.cities_list.GetCount()):
            self.cities_list.Check(i, True)

    def on_deselect_all(self, event):
        for i in range(self.cities_list.GetCount()):
            self.cities_list.Check(i, False)

    def on_add_cities(self, event):
        self.selected_cities = []
        for i in range(self.cities_list.GetCount()):
            if self.cities_list.IsChecked(i):
                c = self.cities_list.GetClientData(i)
                if c:
                    self.selected_cities.append((c["display"], c["lat"], c["lon"]))
        if not self.selected_cities:
            wx.MessageBox("Please select at least one city to add", "No Cities Selected",
                          wx.OK | wx.ICON_WARNING)
            return
        self.EndModal(wx.ID_OK)

    def get_selected_cities(self):
        return self.selected_cities

    def get_favorites(self):
        return self.favorites

    def _on_close(self, event):
        self._alive = False
        event.Skip()

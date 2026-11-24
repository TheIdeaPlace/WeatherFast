"""Browse cities by US state or country, with sorting and region favorites."""

import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor

import wx

from ... import browse_favorites, places as world_places
from ...services import alert_service, weather_service
from ..alert_format import city_row_badge
from ..city_row import city_row_text

_BATCH = 50          # places per Open-Meteo request
_BATCH_GAP = 1.0     # seconds between them: each place counts against the free tier
_ALERT_GAP = 0.25    # seconds between NWS checks, two at a time, so NWS doesn't throttle
                     # the IP (the main list's alerts share it)


def row_label(c):
    """A Browse Cities row: the same line as Your Cities, as if the city were
    in your list ("<city> - Loading..." until its weather arrives).

    A place from Places of the World also says where it is and why it's
    known, after the weather, so a list can be scanned by name and weather
    first ("Golden Gate Bridge - 55°F, Clear ... San Francisco, California,
    United States. Art Deco suspension bridge ...").
    """
    if c["row"]:
        text = c["row"]
    elif c["failed"]:
        text = f"{c['display']} - weather unavailable"
    else:
        text = f"{c['display']} - Loading"
        if not c.get("about"):
            text += "..."
    text += c["badge"]
    if c.get("about"):
        text += (" " if text.endswith(".") else ". ") + c["about"]
    return text


def _deliver(state, gen, fn, *args):
    """Run a background result on the UI thread, if it's still wanted.

    ``state`` is a plain object, not the dialog: once wx has destroyed the
    dialog, touching it at all raises, and results can arrive after that.
    """
    if state.alive and state.gen == gen:
        fn(*args)


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

    def FocusedIndex(self):
        return self.GetFocusedItem()

    def FocusRow(self, i):
        self.SetItemState(i, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                          wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
        self.EnsureVisible(i)

    def Check(self, i, check=True):
        self.CheckItem(i, check)

    def IsChecked(self, i):
        return self.IsItemChecked(i)


_LIST_LABEL = "Select cities to add (check multiple cities):"
_PLACES_LIST_LABEL = "Select places to add (check multiple places):"

# Favorites list prefixes, by kind
_KIND_PREFIX = {"us": "US", "intl": "Intl", "places": "Places"}

_SORTS = [
    "Name (A-Z)", "Name (Z-A)",
    "North to South", "South to North",
    "East to West", "West to East",
    "Temperature (Warm-Cold)", "Temperature (Cold-Warm)",
]


class LocationBrowserDialog(wx.Dialog):
    """Browse cities by US State or country, or famous places by list;
    multi-select add, sort, favorites.

    ``place_categories`` is Places of the World (see ``fastweather.places``);
    its tab is left out when there are none. ``start_page`` ("us", "intl" or
    "places") picks the tab the dialog opens on.
    """

    def __init__(self, parent, us_cities_cache, intl_cities_cache, favorites=None, fmt=None,
                 place_categories=None, start_page=None):
        super().__init__(parent, title="Browse Cities by Location", size=(720, 640))
        self.us_cities_cache = us_cities_cache
        self.intl_cities_cache = intl_cities_cache
        self.place_categories = list(place_categories or [])
        # Same shape as the city caches: list name -> its places
        self.places_cache = {c["name"]: c["places"] for c in self.place_categories}
        self.favorites = list(favorites or [])
        self.fmt = fmt
        self.selected_cities = []
        self.loaded_cities = []           # list of dicts for the current region
        self.loaded_region = None         # (kind, region_name)
        # alive, and gen (bumped on each load and on close, so stale work stops).
        # Kept off the dialog so worker threads can read it after it's gone.
        self._state = types.SimpleNamespace(alive=True, gen=0)
        self._regions = {}          # (kind, region) -> its city dicts, weather and all
        self._list_cities = None    # which loaded_cities the list is showing
        self._weather_pending = 0   # cities whose weather hasn't arrived yet
        self._sort_waiting = False  # a Temperature sort waiting for that weather

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.notebook = wx.Notebook(panel)
        self._pages = {}            # "us" / "intl" / "places" -> notebook page index
        self._build_us_tab()
        self._build_intl_tab()
        self.load_places_btn = None
        if self.place_categories:
            self._build_places_tab()
        self._build_fav_tab()
        vbox.Add(self.notebook, 0, wx.EXPAND | wx.ALL, 8)
        if start_page in self._pages:
            self.notebook.SetSelection(self._pages[start_page])

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
        if self.load_places_btn:
            self.Bind(wx.EVT_BUTTON, self.on_load_places, self.load_places_btn)
        self.Bind(wx.EVT_BUTTON, self.on_select_all, self.select_all_btn)
        self.Bind(wx.EVT_BUTTON, self.on_deselect_all, self.deselect_all_btn)
        self.Bind(wx.EVT_BUTTON, self.on_add_cities, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.on_toggle_favorite, self.fav_btn)
        self.sort_choice.Bind(wx.EVT_CHOICE, lambda e: self._populate())
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

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
        self._pages["us"] = self.notebook.GetPageCount()
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
        self._pages["intl"] = self.notebook.GetPageCount()
        self.notebook.AddPage(intl_panel, "International")

    def _build_places_tab(self):
        p = wx.Panel(self.notebook)
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(p, label="Select a list of places:"), 0, wx.ALL, 10)
        self.places_choice = wx.Choice(p)
        self.places_choice.Append("-- Select a List --")
        for cat in self.place_categories:
            self.places_choice.Append(world_places.category_label(cat))
        self.places_choice.SetSelection(0)
        s.Add(self.places_choice, 0, wx.EXPAND | wx.ALL, 10)
        # What the chosen list is; read-only text, so a screen reader can
        # review it with Tab rather than only seeing it.
        self.places_desc = wx.TextCtrl(
            p, value="Famous bridges, beaches and extreme weather places, each with its weather.",
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_NO_VSCROLL | wx.BORDER_NONE,
            size=(-1, 40))
        self.places_desc.SetName("About this list")
        s.Add(self.places_desc, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.load_places_btn = wx.Button(p, label="Load Places")
        s.Add(self.load_places_btn, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        p.SetSizer(s)
        self.places_choice.Bind(wx.EVT_CHOICE, self._on_places_choice)
        self._pages["places"] = self.notebook.GetPageCount()
        self.notebook.AddPage(p, "Places of the World")

    def _on_places_choice(self, event):
        sel = self.places_choice.GetSelection()
        if sel > 0:
            self.places_desc.SetValue(self.place_categories[sel - 1]["description"])

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
            label = f"{_KIND_PREFIX.get(f.get('kind'), 'Intl')}: {f.get('region', '')}"
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

    def on_load_places(self, event):
        sel = self.places_choice.GetSelection()
        if sel <= 0 or sel == wx.NOT_FOUND:
            wx.MessageBox("Please select a list of places", "No Selection",
                          wx.OK | wx.ICON_WARNING)
            return
        self._load_region("places", self.place_categories[sel - 1]["name"])

    def on_load_favorite(self, event):
        sel = self.fav_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        fav = self.favorites[sel]
        self._load_region(fav["kind"], fav["region"])

    def _load_region(self, kind, region):
        cache = {"us": self.us_cities_cache, "places": self.places_cache}.get(
            kind, self.intl_cities_cache)
        if not cache or region not in cache:
            wx.MessageBox("No data for that region.", "Unavailable", wx.OK | wx.ICON_WARNING)
            return
        self._state.gen += 1        # the last region's fetches stop
        self.loaded_region = (kind, region)
        cities = self._regions.get((kind, region))
        if cities is None and kind == "places":
            cities = [{
                "name": p["name"], "lat": p["lat"], "lon": p["lon"],
                "state": p.get("state") or "", "country": p.get("country") or "",
                "display": p["name"],
                "saved": world_places.saved_name(p),
                "about": world_places.about_text(p),
                "temp": None, "row": None, "badge": "", "failed": False,
                "alerts_checked": False,
            } for p in cache[region]]
            self._regions[(kind, region)] = cities
        if cities is None:
            cities = []
            for c in cache[region]:
                parts = [c["name"]]
                if c.get("state"):
                    parts.append(c["state"])
                parts.append(c.get("country", region))
                cities.append({
                    "name": c["name"], "lat": c["lat"], "lon": c["lon"],
                    "state": c.get("state", ""), "country": c.get("country", region),
                    "display": ", ".join(parts),
                    "temp": None, "row": None, "badge": "", "failed": False,
                    "alerts_checked": False,
                })
            self._regions[(kind, region)] = cities
        self.loaded_cities = cities
        self._update_fav_button()
        self._fetch_weather(kind, cities)
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
        what = "List" if kind == "places" else "Region"
        self.fav_btn.SetLabel(f"Remove {what} from Favorites" if fav
                              else f"Add {what} to Favorites")

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
        waiting = sort.startswith("Temperature") and self._weather_pending > 0
        self._sort_waiting = waiting
        if waiting:
            # Sorted once every city's weather is in (_weather_ready). Until
            # then the list shows this region by name, never the last region.
            if self._list_cities is not self.loaded_cities:
                self._fill_list(self._sorted("Name (A-Z)"))
            self.list_label.SetLabel("Getting the weather, then sorting by temperature...")
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

    def _label(self, c):
        return row_label(c)

    def _list_label(self):
        if self.loaded_region and self.loaded_region[0] == "places":
            return _PLACES_LIST_LABEL
        return _LIST_LABEL

    def _fill_list(self, cities):
        # Keep what was checked, and the city you were on, when the list is
        # re-sorted (a Temperature sort can land while you're reading).
        same = self._list_cities is self.loaded_cities
        checked = {id(self.cities_list.GetClientData(i))
                   for i in range(self.cities_list.GetCount())
                   if self.cities_list.IsChecked(i)} if same else set()
        f = self.cities_list.FocusedIndex()
        focused = self.cities_list.GetClientData(f) if same and f >= 0 else None
        self.list_label.SetLabel(self._list_label())
        self.cities_list.Clear()
        for c in cities:
            i = self.cities_list.Append(self._label(c), c)
            if id(c) in checked:
                self.cities_list.Check(i, True)
            if c is focused and i:
                self.cities_list.FocusRow(i)
        self._list_cities = self.loaded_cities

    def _fetch_weather(self, kind, cities):
        """Get today's weather for every city in the region, so each row reads
        like a line in Your Cities ("Algoma, ... - 45°F, Overcast (High: ...,
        Low: ...)", with the alert marker for US cities). Rows change in place
        as results arrive, so checks and position are kept.

        Weather comes 50 places to a request, so a state costs a few requests
        rather than one per city (Open-Meteo's free tier, shared with the main
        list, allows 600 a minute). A region's results are kept while the
        dialog is open, and everything stops when you load another region or
        close the dialog.
        """
        todo = [c for c in cities if c["row"] is None]   # new, or failed last time
        for c in todo:
            c["failed"] = False   # trying again: "Loading..." until it answers
        # Alerts separately: a check cut short by loading another region, or
        # one that failed, is done again, so a missing marker never wrongly
        # means "no alerts".
        # NWS covers the US only: a US state's cities, or the US places in a
        # Places of the World list.
        alert_todo = [c for c in cities if not c["alerts_checked"]
                      and (kind == "us"
                           or (kind == "places" and c["country"] == "United States"))]
        self._weather_pending = len(todo)
        if not todo and not alert_todo:
            return
        state = self._state
        gen = state.gen
        # Looked up now: the worker must not touch the dialog, which may be gone.
        weather_ready, badge_ready = self._weather_ready, self._badge_ready

        def work():
            for i in range(0, len(todo), _BATCH):
                if gen != state.gen:
                    return
                if i:
                    time.sleep(_BATCH_GAP)
                batch = todo[i:i + _BATCH]
                try:
                    datas = weather_service.fetch_basic_many(
                        [(c["lat"], c["lon"]) for c in batch])
                except Exception:  # noqa: BLE001 - those cities say "weather unavailable"
                    datas = [None] * len(batch)
                wx.CallAfter(_deliver, state, gen, weather_ready, batch, datas)
            # NWS alerts cover the US only, as in Your Cities (alert_todo is
            # empty elsewhere).
            def badge(c):
                if gen != state.gen:
                    return
                try:
                    alerts = alert_service.fetch_alerts(c["lat"], c["lon"])
                except Exception:  # noqa: BLE001 - no marker; checked again on reload
                    return
                finally:
                    time.sleep(_ALERT_GAP)
                wx.CallAfter(_deliver, state, gen, badge_ready, c, alerts)

            with ThreadPoolExecutor(max_workers=2) as ex:
                list(ex.map(badge, alert_todo))

        threading.Thread(target=work, daemon=True).start()

    def _weather_ready(self, batch, datas):
        try:
            for c, data in zip(batch, datas):
                row = city_row_text(c["display"], data, self.fmt) if data and self.fmt else None
                if data:
                    c["temp"] = (data.get("current") or {}).get("temperature_2m")
                c["row"] = row
                c["failed"] = not row
                self.cities_list.SetLabelFor(c, self._label(c))
        finally:
            self._weather_pending = max(0, self._weather_pending - len(batch))
            if self._weather_pending == 0 and self._sort_waiting:
                self._sort_waiting = False
                self._fill_list(self._sorted(self.sort_choice.GetStringSelection()))

    def _badge_ready(self, c, alerts):
        c["alerts_checked"] = True
        c["badge"] = city_row_badge(alerts)
        if c["badge"]:
            self.cities_list.SetLabelFor(c, self._label(c))

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
                    # A place is saved as "Golden Gate Bridge, San Francisco"
                    self.selected_cities.append((c.get("saved") or c["display"],
                                                 c["lat"], c["lon"]))
        if not self.selected_cities:
            what = ("place" if self.loaded_region and self.loaded_region[0] == "places"
                    else "city")
            wx.MessageBox(f"Please select at least one {what} to add", "Nothing Selected",
                          wx.OK | wx.ICON_WARNING)
            return
        self.EndModal(wx.ID_OK)

    def get_selected_cities(self):
        return self.selected_cities

    def get_favorites(self):
        return self.favorites

    def _stop(self):
        """Stop background work. OK, Cancel and Escape end the dialog without
        EVT_CLOSE, so this is also called from EndModal and on destroy."""
        self._state.alive = False
        self._state.gen += 1

    def EndModal(self, retCode):
        self._stop()
        super().EndModal(retCode)

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._stop()
        event.Skip()

    def _on_close(self, event):
        self._stop()
        event.Skip()

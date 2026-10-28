"""MainFrame: the application window and controller.

Ported from the original AccessibleWeatherApp monolith onto the layered
package (CityStore, AppSettings, Formatter, services via FetchManager,
AccessibleLinesPanel, dialogs). Behavior and layout are preserved.
"""

import json
import os
import sys

import wx

from . import __version__, browse_favorites
from .constants import USER_GUIDE_URL
from .city_data import flatten_cities, load_cached_cities
from .locale_units import locale_default_units
from .models.city import CityStore
from .models.settings import AppSettings
from .services import geocoding_service, weather_service
from .services.fetch_manager import FetchManager
from .ui.accessible_list import AccessibleLinesPanel
from .ui.city_row import city_row_error, city_row_text
from .ui.dialogs.city_select import CitySelectionDialog
from .ui.dialogs.config_dialog import WeatherConfigDialog
from .ui.dialogs.location_browser import LocationBrowserDialog
from .ui.events import EVT_FETCH_RESULT
from .services import alert_service, location_service, updater
from .ui.alert_format import RETRY, city_row_badge, highest, section_lines
from .ui.dialogs.alert_browser_dialog import AlertBrowserDialog
from .ui.dialogs.alert_detail_dialog import AlertDetailDialog
from .ui.dialogs.alerts_dialog import AlertsDialog
from .ui.dialogs.around_me_dialog import AroundMeDialog
from .ui.dialogs.historical_dialog import HistoricalDialog
from .ui.dialogs.marine_dialog import MarineDialog
from .ui.dialogs.mydata_dialog import MyDataDialog
from .ui.dialogs.radar_dialog import RadarDialog
from .ui.dialogs.astronomy_dialog import AstronomyDialog
from .ui.formatters import Formatter
from .ui.full_weather_view import build_day_lines, build_full_weather_lines
from .paths import user_data_dir


class MainFrame(wx.Frame):
    def __init__(self, city_file=None):
        super().__init__(None, title="WeatherFast", size=(1000, 700))

        data_dir = user_data_dir()
        if city_file is None:
            self.city_file = os.path.join(data_dir, "city.json")
        else:
            self.city_file = city_file
        self.config_file = os.path.join(data_dir, "config.json")

        # Model / settings / helpers
        self.cities = CityStore(self.city_file)
        self.settings = AppSettings()
        self.fmt = Formatter(self.settings)

        # Cached city coordinates for browsing
        self.us_cities_cache, self.intl_cities_cache = load_cached_cities()
        self._all_cities = None  # flattened lazily for the Directional Explorer
        self.browse_favs = browse_favorites.load()
        self.day_offset = 0      # detailed-view date navigation (-7..+7)
        self.current_full_data = None

        # Alert state. Row badges are kept separately from the weather text so a
        # weather refresh can't drop a badge (and vice versa); the detailed
        # view's ALERTS section tracks its own fetch state so "couldn't check"
        # is never rendered as "no alerts".
        self._row_text = {}        # city -> weather line, without the badge
        self._row_badges = {}      # city -> badge suffix ("" when clear)
        self._row_seq = {}         # city -> number of its newest basic fetch
        self._row_stale = set()    # cities whose last refresh failed (old weather shown)
        self.full_alert_state = "off"
        self.full_alerts = []
        self.full_alert_error = ""

        self.cities.load()
        # First run only: seed units from the user's Windows region (matches
        # iOS locale-aware defaults). Saved config always wins afterward.
        if not os.path.exists(self.config_file):
            regional = locale_default_units()
            if regional:
                self.settings["units"].update(regional)
        self.load_config()

        # Background fetch manager
        self.fetch = FetchManager(self)

        self.init_ui()
        self.create_menubar()
        self.setup_shortcuts()

        self.Bind(EVT_FETCH_RESULT, self.on_fetch_result)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        wx.CallAfter(self.set_initial_focus)
        # Auto-check for updates shortly after launch (frozen build only).
        wx.CallLater(4000, self._maybe_auto_check_updates)

    # -- configuration persistence -------------------------------------------
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file) as f:
                    self.settings.merge_saved(json.load(f))
            except Exception:
                pass

    def save_config(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.settings.to_dict(), f, indent=4)
        except Exception:
            pass

    # -- UI construction ------------------------------------------------------
    def init_ui(self):
        self.panel = wx.Panel(self)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.book = wx.Simplebook(self.panel)

        # Main view
        self.main_view = wx.Panel(self.book)
        mv_sizer = wx.BoxSizer(wx.VERTICAL)

        sb_input = wx.StaticBox(self.main_view, label="Add New City")
        inp_box = wx.StaticBoxSizer(sb_input, wx.VERTICAL)
        inp_row = wx.BoxSizer(wx.HORIZONTAL)
        self.city_input = wx.TextCtrl(self.main_view, style=wx.TE_PROCESS_ENTER)
        self.city_input.SetHint("City name or zip code")
        self.add_btn = wx.Button(self.main_view, label="Add City")
        inp_row.Add(wx.StaticText(self.main_view, label="Enter city:"), 0,
                    wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        inp_row.Add(self.city_input, 1, wx.EXPAND | wx.RIGHT, 5)
        inp_row.Add(self.add_btn, 0)
        inp_box.Add(inp_row, 0, wx.EXPAND | wx.ALL, 5)

        browse_row = wx.BoxSizer(wx.HORIZONTAL)
        self.browse_btn = wx.Button(self.main_view, label="Browse Cities by State/Country")
        self.mylocation_btn = wx.Button(self.main_view, label="Add My Location")
        browse_row.Add(self.browse_btn, 1, wx.EXPAND | wx.RIGHT, 5)
        browse_row.Add(self.mylocation_btn, 0)
        inp_box.Add(browse_row, 0, wx.EXPAND | wx.ALL, 5)

        mv_sizer.Add(inp_box, 0, wx.EXPAND | wx.ALL, 10)

        sb_list = wx.StaticBox(self.main_view, label="Your Cities")
        list_box = wx.StaticBoxSizer(sb_list, wx.VERTICAL)
        self.city_list = wx.ListBox(self.main_view, style=wx.LB_SINGLE | wx.WANTS_CHARS)
        list_box.Add(self.city_list, 1, wx.EXPAND | wx.ALL, 5)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_up = wx.Button(self.main_view, label="Move Up")
        self.btn_down = wx.Button(self.main_view, label="Move Down")
        self.btn_remove = wx.Button(self.main_view, label="Remove")
        self.btn_refresh = wx.Button(self.main_view, label="Refresh")
        self.btn_full = wx.Button(self.main_view, label="Full Weather")
        self.btn_config_main = wx.Button(self.main_view, label="Configure")
        for b in [self.btn_up, self.btn_down, self.btn_remove, self.btn_refresh,
                  self.btn_full, self.btn_config_main]:
            btn_row.Add(b, 0, wx.RIGHT, 5)
        list_box.Add(btn_row, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        mv_sizer.Add(list_box, 1, wx.EXPAND | wx.ALL, 10)

        self.main_view.SetSizer(mv_sizer)

        # Full view
        self.full_view = wx.Panel(self.book)
        fv_sizer = wx.BoxSizer(wx.VERTICAL)

        head_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_back = wx.Button(self.full_view, label="<- Back")
        self.lbl_full_title = wx.StaticText(self.full_view, label="Full Weather")
        self.lbl_full_title.SetFont(
            wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        )
        self.btn_prev_day = wx.Button(self.full_view, label="Prev Day")
        self.btn_today = wx.Button(self.full_view, label="Today")
        self.btn_next_day = wx.Button(self.full_view, label="Next Day")
        self.btn_config = wx.Button(self.full_view, label="Configure")
        head_row.Add(self.btn_back, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        head_row.Add(self.lbl_full_title, 1, wx.ALIGN_CENTER_VERTICAL)
        head_row.Add(self.btn_prev_day, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        head_row.Add(self.btn_today, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        head_row.Add(self.btn_next_day, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        head_row.Add(self.btn_config, 0, wx.ALIGN_CENTER_VERTICAL)
        fv_sizer.Add(head_row, 0, wx.EXPAND | wx.ALL, 10)

        self.full_display = AccessibleLinesPanel(self.full_view, activatable=True,
                                                  name="Weather report")
        self.full_display.set_activate_handler(self._open_alert)
        fv_sizer.Add(self.full_display, 1, wx.EXPAND | wx.ALL, 10)
        self.full_view.SetSizer(fv_sizer)

        self.book.AddPage(self.main_view, "Main")
        self.book.AddPage(self.full_view, "Full")
        self.sizer.Add(self.book, 1, wx.EXPAND)
        self.panel.SetSizer(self.sizer)

        self.statusbar = self.CreateStatusBar(2)
        self.statusbar.SetStatusText("Ready", 0)
        self.statusbar.SetStatusText(
            "Weather: Open-Meteo.com | Geocoding: OpenStreetMap", 1
        )

        # Bindings
        self.Bind(wx.EVT_BUTTON, self.on_add_city, self.add_btn)
        self.city_input.Bind(wx.EVT_TEXT_ENTER, self.on_add_city)
        self.Bind(wx.EVT_BUTTON, self.on_browse_cities, self.browse_btn)
        self.Bind(wx.EVT_BUTTON, self.on_add_my_location, self.mylocation_btn)
        self.Bind(wx.EVT_LISTBOX, self.on_select, self.city_list)
        self.city_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_full_weather)
        self.Bind(wx.EVT_BUTTON, self.on_move_up, self.btn_up)
        self.Bind(wx.EVT_BUTTON, self.on_move_down, self.btn_down)
        self.Bind(wx.EVT_BUTTON, self.on_remove, self.btn_remove)
        self.Bind(wx.EVT_BUTTON, self.on_refresh, self.btn_refresh)
        self.Bind(wx.EVT_BUTTON, self.on_full_weather, self.btn_full)
        self.Bind(wx.EVT_BUTTON, self.on_back, self.btn_back)
        self.Bind(wx.EVT_BUTTON, lambda e: self.nav_day(-1), self.btn_prev_day)
        self.Bind(wx.EVT_BUTTON, lambda e: self.nav_day(0), self.btn_today)
        self.Bind(wx.EVT_BUTTON, lambda e: self.nav_day(1), self.btn_next_day)
        self.Bind(wx.EVT_BUTTON, self.on_config, self.btn_config)
        self.Bind(wx.EVT_BUTTON, self.on_config, self.btn_config_main)
        self.city_list.Bind(wx.EVT_KEY_DOWN, self.on_list_key)

        self.update_city_list()

    def on_list_key(self, event):
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_full_weather(event)
        elif keycode == wx.WXK_DELETE and not event.HasAnyModifiers():
            # Delete belongs to the list: as a window-wide accelerator it also
            # took Delete away from the search box.
            self.on_remove(event)
        elif keycode == wx.WXK_TAB:
            flags = wx.NavigationKeyEvent.IsForward
            if event.ShiftDown():
                flags = wx.NavigationKeyEvent.IsBackward
            self.city_list.Navigate(flags)
        else:
            event.Skip()

    def create_menubar(self):
        """Menu bar for discoverable, accessible access to all actions.

        Top-level menu mnemonics deliberately avoid C/F/U/D/N so they don't
        collide with the Alt+C/F/U/D/N accelerators in the accelerator table.
        Items inside an open menu are chosen without Alt, so they can use any
        letter. Feature sheets
        are added to the Weather menu by their respective phases via
        add_weather_menu_item().
        """
        mb = wx.MenuBar()

        cities_menu = wx.Menu()
        mi_add = cities_menu.Append(wx.ID_ANY, "Add City")
        mi_browse = cities_menu.Append(wx.ID_ANY, "Browse Cities by State/Country...")
        mi_myloc = cities_menu.Append(wx.ID_ANY, "Add My Location")
        cities_menu.AppendSeparator()
        mi_alertbrowser = cities_menu.Append(wx.ID_ANY, "Browse Weather Alerts...")
        cities_menu.AppendSeparator()
        mi_full = cities_menu.Append(wx.ID_ANY, "Full Weather")
        mi_refresh = cities_menu.Append(wx.ID_ANY, "Refresh")
        cities_menu.AppendSeparator()
        mi_remove = cities_menu.Append(wx.ID_ANY, "Remove City")
        mi_up = cities_menu.Append(wx.ID_ANY, "Move Up")
        mi_down = cities_menu.Append(wx.ID_ANY, "Move Down")
        cities_menu.AppendSeparator()
        mi_copy = cities_menu.Append(wx.ID_ANY, "Copy Weather Report")
        mi_save = cities_menu.Append(wx.ID_ANY, "Save Weather Report...")
        cities_menu.AppendSeparator()
        mi_exit = cities_menu.Append(wx.ID_EXIT, "Exit")
        mb.Append(cities_menu, "C&ities")

        self.weather_menu = wx.Menu()
        self._weather_placeholder = self.weather_menu.Append(
            wx.ID_ANY, "(select a city, then choose a feature)"
        )
        self._weather_placeholder.Enable(False)
        mb.Append(self.weather_menu, "&Weather")

        settings_menu = wx.Menu()
        mi_config = settings_menu.Append(wx.ID_ANY, "Configure Display && Units...")
        settings_menu.AppendSeparator()
        mi_placenames = settings_menu.AppendCheckItem(
            wx.ID_ANY, "Search: Use Specific Place Names (airports, landmarks)")
        mi_placenames.Check(self.settings["options"].get("specific_place_names", True))
        mb.Append(settings_menu, "&Settings")

        help_menu = wx.Menu()
        mi_guide = help_menu.Append(wx.ID_ANY, "User Guide\tF1")
        help_menu.AppendSeparator()
        mi_update = help_menu.Append(wx.ID_ANY, "Check for Updates...")
        mi_autoupdate = help_menu.AppendCheckItem(wx.ID_ANY, "Automatically Check for Updates")
        mi_autoupdate.Check(self.settings["options"].get("auto_check_updates", True))
        help_menu.AppendSeparator()
        mi_about = help_menu.Append(wx.ID_ABOUT, "About")
        mb.Append(help_menu, "&Help")

        self.SetMenuBar(mb)

        self.Bind(wx.EVT_MENU, self.on_focus_new_city, mi_add)
        self.Bind(wx.EVT_MENU, self.on_browse_cities, mi_browse)
        self.Bind(wx.EVT_MENU, self.on_add_my_location, mi_myloc)
        self.Bind(wx.EVT_MENU, self.on_browse_alerts, mi_alertbrowser)
        self.Bind(wx.EVT_MENU, self.on_full_weather, mi_full)
        self.Bind(wx.EVT_MENU, self.on_refresh, mi_refresh)
        self.Bind(wx.EVT_MENU, self.on_remove, mi_remove)
        self.Bind(wx.EVT_MENU, self.on_move_up, mi_up)
        self.Bind(wx.EVT_MENU, self.on_move_down, mi_down)
        self.Bind(wx.EVT_MENU, self.on_copy_report, mi_copy)
        self.Bind(wx.EVT_MENU, self.on_save_report, mi_save)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), mi_exit)
        self.Bind(wx.EVT_MENU, self.on_config, mi_config)
        self.Bind(wx.EVT_MENU, self._on_toggle_place_names, mi_placenames)
        self.Bind(wx.EVT_MENU, lambda e: wx.LaunchDefaultBrowser(USER_GUIDE_URL), mi_guide)
        self.Bind(wx.EVT_MENU, lambda e: self.check_for_updates(manual=True), mi_update)
        self.Bind(wx.EVT_MENU, self._on_toggle_auto_update, mi_autoupdate)
        self.Bind(wx.EVT_MENU, self.on_about, mi_about)

        # Feature sheets (registered per phase).
        # Each item has its own access key; first letters repeat (Weather
        # Alerts / Weather Around Me, My Data / Marine Forecast).
        self.add_weather_menu_item("Weather &Alerts...", self.on_alerts)
        self.add_weather_menu_item("&Expected Precipitation...", self.on_radar)
        self.add_weather_menu_item("Weather Around &Me...", self.on_weather_around_me)
        self.add_weather_menu_item("&Historical Weather...", self.on_historical)
        self.add_weather_menu_item("My &Data...", self.on_mydata)
        self.add_weather_menu_item("Ma&rine Forecast...", self.on_marine)
        self.add_weather_menu_item("As&tronomy (Moon)...", self.on_astronomy)

    def all_cities(self):
        """Flattened list of every cached city (built once, lazily)."""
        if self._all_cities is None:
            self._all_cities = flatten_cities(self.us_cities_cache, self.intl_cities_cache)
        return self._all_cities

    def on_weather_around_me(self, event):
        city = self.require_selected_city()
        if not city:
            return
        dlg = AroundMeDialog(self, city, self.settings, self.fmt, self.all_cities())
        dlg.ShowModal()
        dlg.Destroy()
        self.save_config()  # persist radius/mode/width chosen in the sheet

    def on_historical(self, event):
        city = self.require_selected_city()
        if not city:
            return
        dlg = HistoricalDialog(self, city, self.settings, self.fmt)
        dlg.ShowModal()
        dlg.Destroy()
        self.save_config()  # persist years-back

    def on_mydata(self, event):
        city = self.require_selected_city()
        if not city:
            return
        dlg = MyDataDialog(self, city, self.settings, self.fmt)
        dlg.ShowModal()
        dlg.Destroy()
        self.save_config()  # persist the parameter selection

    def on_marine(self, event):
        city = self.require_selected_city()
        if not city:
            return
        dlg = MarineDialog(self, city, self.fmt)
        dlg.ShowModal()
        dlg.Destroy()

    def on_astronomy(self, event):
        city = self.require_selected_city()
        if not city:
            return
        dlg = AstronomyDialog(self, city)
        dlg.ShowModal()
        dlg.Destroy()

    def on_alerts(self, event):
        city = self.require_selected_city()
        if not city:
            return
        dlg = AlertsDialog(self, city)
        dlg.ShowModal()
        dlg.Destroy()

    def on_radar(self, event):
        city = self.require_selected_city()
        if not city:
            return
        dlg = RadarDialog(self, city, self.fmt)
        dlg.ShowModal()
        dlg.Destroy()

    def add_weather_menu_item(self, label, handler):
        """Register a per-city feature sheet in the Weather menu (used by phases)."""
        if self._weather_placeholder is not None:
            self.weather_menu.DestroyItem(self._weather_placeholder)
            self._weather_placeholder = None
        item = self.weather_menu.Append(wx.ID_ANY, label)
        self.Bind(wx.EVT_MENU, handler, item)
        return item

    def selected_city(self):
        """Return (name, lat, lon) for the active city, or None.

        Uses the detailed view's city when it is showing, otherwise the
        selection in the main list.
        """
        if self.book.GetSelection() == 1 and hasattr(self, "current_full_city"):
            return self.current_full_city
        sel = self.city_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return None
        name = self._city_key_at(sel)
        if name and name in self.cities:
            lat, lon = self.cities.coords(name)
            return (name, lat, lon)
        return None

    def _city_key_at(self, index):
        """The CityStore key for a list row, recovered by position.

        The list is always built and kept in CityStore order, so the row index
        maps directly to the key. The display string cannot be used to recover
        the key because place names may themselves contain ' - '
        (e.g. "O'Hare International Airport - Chicago, Illinois, United States").
        """
        names = self.cities.names()
        if 0 <= index < len(names):
            return names[index]
        return None

    def require_selected_city(self):
        """Return the active city or show a prompt and return None."""
        city = self.selected_city()
        if city is None:
            wx.MessageBox("Select a city first.", "No City Selected",
                          wx.OK | wx.ICON_INFORMATION)
        return city

    def _report_text(self):
        """The currently displayed detailed report as text, or None."""
        lb = self.full_display.listbox
        if self.book.GetSelection() != 1 or lb.GetCount() == 0:
            return None
        return "\n".join(lb.GetString(i) for i in range(lb.GetCount()))

    def on_copy_report(self, event):
        text = self._report_text()
        if not text:
            wx.MessageBox("Open Full Weather for a city first.", "Nothing to Copy",
                          wx.OK | wx.ICON_INFORMATION)
            return
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            self.statusbar.SetStatusText("Report copied to clipboard", 0)

    def on_save_report(self, event):
        text = self._report_text()
        if not text:
            wx.MessageBox("Open Full Weather for a city first.", "Nothing to Save",
                          wx.OK | wx.ICON_INFORMATION)
            return
        default = "weather.txt"
        if hasattr(self, "current_full_city"):
            default = self.current_full_city[0].split(",")[0].strip() + " weather.txt"
        with wx.FileDialog(self, "Save Weather Report", defaultFile=default,
                           wildcard="Text files (*.txt)|*.txt",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            try:
                with open(dlg.GetPath(), "w", encoding="utf-8") as f:
                    f.write(text)
                self.statusbar.SetStatusText(f"Saved {dlg.GetPath()}", 0)
            except Exception as e:  # noqa: BLE001
                wx.MessageBox(f"Could not save: {e}", "Error", wx.OK | wx.ICON_ERROR)

    # -- updates ---------------------------------------------------------------
    def _maybe_auto_check_updates(self):
        if getattr(sys, "frozen", False) and \
                self.settings["options"].get("auto_check_updates", True):
            self.check_for_updates(manual=False)

    def _on_toggle_auto_update(self, event):
        self.settings["options"]["auto_check_updates"] = event.IsChecked()
        self.save_config()

    def _on_toggle_place_names(self, event):
        self.settings["options"]["specific_place_names"] = event.IsChecked()
        self.save_config()

    def check_for_updates(self, manual=False):
        if manual:
            self.statusbar.SetStatusText("Checking for updates...", 0)
        self.fetch.submit("update_check", updater.check_for_update,
                          request_id=("manual" if manual else "auto"))

    def _prompt_update(self, info):
        notes = info.get("notes", "")
        if len(notes) > 600:
            notes = notes[:600] + "\n..."
        if not info.get("url"):
            if wx.MessageBox(
                f"WeatherFast {info['version']} is available (you have {__version__}).\n\n"
                "Open the downloads page?", "Update Available",
                wx.YES_NO | wx.ICON_INFORMATION,
            ) == wx.YES:
                wx.LaunchDefaultBrowser(
                    f"https://github.com/{updater.GITHUB_REPO}/releases/latest")
            return
        msg = (f"WeatherFast {info['version']} is available "
               f"(you have {__version__}).\n\n{notes}\n\n"
               "Download and install now? The app will close to finish installing.")
        if wx.MessageBox(msg, "Update Available", wx.YES_NO | wx.ICON_INFORMATION) == wx.YES:
            self.statusbar.SetStatusText("Downloading update...", 0)
            url = info["url"]
            self.fetch.submit("update_download", lambda: updater.download_installer(url))

    def on_about(self, event):
        wx.MessageBox(
            f"WeatherFast for Windows\nVersion {__version__}\n\n"
            "Weather data by Open-Meteo.com (CC BY 4.0)\n"
            "Geocoding by OpenStreetMap / Nominatim",
            "About WeatherFast", wx.OK | wx.ICON_INFORMATION,
        )

    def setup_shortcuts(self):
        self.ID_REFRESH = wx.NewIdRef()
        self.ID_MOVE_UP = wx.NewIdRef()
        self.ID_MOVE_DOWN = wx.NewIdRef()
        self.ID_ESCAPE = wx.NewIdRef()
        self.ID_FULL_WEATHER = wx.NewIdRef()
        self.ID_NEW_CITY = wx.NewIdRef()
        self.ID_CONFIGURE = wx.NewIdRef()

        self.Bind(wx.EVT_MENU, self.on_refresh, id=self.ID_REFRESH)
        self.Bind(wx.EVT_MENU, self.on_move_up, id=self.ID_MOVE_UP)
        self.Bind(wx.EVT_MENU, self.on_move_down, id=self.ID_MOVE_DOWN)
        self.Bind(wx.EVT_MENU, self.on_escape, id=self.ID_ESCAPE)
        self.Bind(wx.EVT_MENU, self.on_full_weather, id=self.ID_FULL_WEATHER)
        self.Bind(wx.EVT_MENU, self.on_focus_new_city, id=self.ID_NEW_CITY)
        self.Bind(wx.EVT_MENU, self.on_config, id=self.ID_CONFIGURE)

        accel = [
            (wx.ACCEL_NORMAL, wx.WXK_F5, self.ID_REFRESH),
            (wx.ACCEL_CTRL, ord("R"), self.ID_REFRESH),
            (wx.ACCEL_ALT, ord("U"), self.ID_MOVE_UP),
            (wx.ACCEL_ALT, ord("D"), self.ID_MOVE_DOWN),
            (wx.ACCEL_NORMAL, wx.WXK_ESCAPE, self.ID_ESCAPE),
            (wx.ACCEL_ALT, ord("F"), self.ID_FULL_WEATHER),
            (wx.ACCEL_ALT, ord("N"), self.ID_NEW_CITY),
            (wx.ACCEL_ALT, ord("C"), self.ID_CONFIGURE),
        ]
        self.SetAcceleratorTable(wx.AcceleratorTable(accel))

    def on_escape(self, event):
        if self.book.GetSelection() == 1:
            self.on_back(event)

    def on_focus_new_city(self, event):
        if self.book.GetSelection() == 0:
            self.city_input.SetFocus()

    def set_initial_focus(self):
        if self.city_list.GetCount() > 0:
            self.city_list.SetSelection(0)
            self.city_list.SetFocus()
        else:
            self.city_input.SetFocus()
        self.update_buttons()
        self._update_title()

    def update_buttons(self):
        sel = self.city_list.GetSelection()
        has_sel = sel != wx.NOT_FOUND
        for b in [self.btn_remove, self.btn_refresh, self.btn_full]:
            b.Enable(has_sel)
        self.btn_up.Enable(has_sel and sel > 0)
        self.btn_down.Enable(has_sel and sel < self.city_list.GetCount() - 1)

    # -- city list ------------------------------------------------------------
    def update_city_list(self, reload=True):
        # Remember the selected row's full display string so selection can be
        # restored after the rebuild. Match by full key (names may contain
        # ' - '), not a split prefix.
        sel = self.city_list.GetSelection()
        prev = self._city_key_at(sel) if sel != wx.NOT_FOUND else None
        self.city_list.Clear()
        names = self.cities.names()
        for city in names:
            # Repaint what we already know; only a city with no weather yet
            # says Loading. (Removing a city used to put every other row back
            # to "Loading..." for good, because nothing refetched them.)
            self.city_list.Append(self._row_display(city))
        if reload:
            self.load_all_weather()

        if prev in names:
            self.city_list.SetSelection(names.index(prev))
        elif self.city_list.GetCount() > 0:
            self.city_list.SetSelection(0)
        self.update_buttons()

    def _row_display(self, city):
        base = self._row_text.get(city)
        if base is None:
            return f"{city} - Loading..."
        stale = " (couldn't refresh)" if city in self._row_stale else ""
        return base + stale + self._row_badges.get(city, "")

    def _on_list_page(self):
        """True when the city list is showing. List commands (Delete, Alt+U,
        Alt+D) act on the list's selection, so they must do nothing while Full
        Weather hides it."""
        return self.book.GetSelection() == 0

    def load_all_weather(self):
        for city in self.cities.names():
            lat, lon = self.cities.coords(city)
            self._fetch_weather(city, lat, lon, "basic")

    def _fetch_weather(self, city, lat, lon, detail):
        if detail == "basic":
            # Numbered, so a slow result (good or bad) can't overwrite a newer one.
            seq = self._row_seq.get(city, 0) + 1
            self._row_seq[city] = seq
            request_id = (city, seq)
        else:
            request_id = city
        # Basic results feed the list rows; full results feed Full Weather.
        # They used to share one handler, so a full result rewrote the row
        # from its first daily entry (a week ago), and a basic result (F5)
        # replaced the Full Weather report, dropping its hourly and daily parts.
        self.fetch.submit(
            "weather" if detail == "basic" else "weather_full",
            lambda: weather_service.fetch_weather(lat, lon, detail),
            request_id=request_id,
        )

    # -- add / browse ---------------------------------------------------------
    def on_add_city(self, event):
        if getattr(self, "_geo_in_flight", False):
            return
        val = self.city_input.GetValue().strip()
        if val:
            self._geo_in_flight = True
            self.statusbar.SetStatusText("Searching...", 0)
            self.add_btn.Disable()
            specific = self.settings["options"].get("specific_place_names", True)
            self.fetch.submit(
                "geo", lambda: geocoding_service.geocode(val, specific=specific),
                request_id=val,
            )

    def on_geo_ready(self, orig, matches):
        self._geo_in_flight = False
        self.add_btn.Enable()
        self.statusbar.SetStatusText("Ready", 0)
        if not matches:
            wx.MessageBox(f"No places found for '{orig}'.", "No Results",
                          wx.OK | wx.ICON_INFORMATION)
            self.city_input.SetFocus()
            return
        # Always present the results list (even a single match) so keyboard /
        # screen-reader users get a consistent, selectable list.
        dlg = CitySelectionDialog(self, matches, orig)
        if dlg.ShowModal() == wx.ID_OK:
            self.add_city_match(dlg.selected_match)
        else:
            self.city_input.SetFocus()
        dlg.Destroy()

    def on_geo_error(self, err):
        self._geo_in_flight = False
        self.add_btn.Enable()
        wx.MessageBox(f"Error: {err}", "Error", wx.OK | wx.ICON_ERROR)

    def add_city_match(self, match):
        name = match["display"]
        if name in self.cities:
            wx.MessageBox(f"{name} is already in your list.", "Already Added",
                          wx.OK | wx.ICON_INFORMATION)
        else:
            self.cities.add(name, match["lat"], match["lon"])
            self.update_city_list()
            self.city_input.Clear()
        # Land on the city in the list, so the screen reader says what was
        # added (focus used to go back to the empty search box).
        self.city_list.SetSelection(self.cities.names().index(name))
        self.city_list.SetFocus()
        self.update_buttons()

    def on_browse_alerts(self, event):
        dlg = AlertBrowserDialog(self, self.settings)
        dlg.ShowModal()
        dlg.Destroy()
        self.save_config()  # persist saved default filters

    def on_add_my_location(self, event):
        if wx.MessageBox(
            "Detect your approximate location and add it as a city?\n\n"
            "If precise device location is unavailable, an IP-based lookup "
            "(ipapi.co) is used to estimate your city.",
            "Add My Location", wx.YES_NO | wx.ICON_QUESTION,
        ) != wx.YES:
            return
        self.statusbar.SetStatusText("Detecting location...", 0)
        self.mylocation_btn.Disable()
        self.fetch.submit("mylocation", location_service.get_location)

    def _add_location_city(self, place):
        name = place["name"]
        if name not in self.cities:
            self.cities.add(name, place["lat"], place["lon"])
            self.update_city_list()
        for i in range(self.city_list.GetCount()):
            if self.city_list.GetString(i).startswith(name):
                self.city_list.SetSelection(i)
                self.city_list.SetFocus()
                break
        self.update_buttons()
        self.statusbar.SetStatusText(f"Added your location: {name}", 0)

    def on_browse_cities(self, event):
        if not self.us_cities_cache and not self.intl_cities_cache:
            wx.MessageBox(
                "City data files not found. Please ensure us-cities-cached.json and "
                "international-cities-cached.json are in the application directory.",
                "Data Not Available", wx.OK | wx.ICON_INFORMATION,
            )
            return

        dlg = LocationBrowserDialog(self, self.us_cities_cache, self.intl_cities_cache,
                                    self.browse_favs, self.fmt)
        result = dlg.ShowModal()
        # Persist any favorites changes regardless of OK/Cancel.
        self.browse_favs = dlg.get_favorites()
        browse_favorites.save(self.browse_favs)
        if result == wx.ID_OK:
            cities_to_add = dlg.get_selected_cities()
            added_count = 0
            skipped_count = 0
            for city_name, lat, lon in cities_to_add:
                if self.cities.add(city_name, lat, lon):
                    added_count += 1
                else:
                    skipped_count += 1

            if added_count > 0:
                self.update_city_list()
                msg = f"Added {added_count} cit{'y' if added_count == 1 else 'ies'}"
                if skipped_count > 0:
                    msg += f" ({skipped_count} already in list)"
                wx.MessageBox(msg, "Cities Added", wx.OK | wx.ICON_INFORMATION)
            elif skipped_count > 0:
                wx.MessageBox(
                    f"All {skipped_count} selected "
                    f"cit{'y was' if skipped_count == 1 else 'ies were'} already in your list",
                    "No New Cities", wx.OK | wx.ICON_INFORMATION,
                )
        dlg.Destroy()

    # -- list actions ---------------------------------------------------------
    def on_select(self, event):
        self.update_buttons()

    def on_remove(self, event):
        if not self._on_list_page():
            return
        sel = self.city_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        city = self._city_key_at(sel)
        if not city:
            return
        if wx.MessageBox(f"Remove {city}?", "Confirm", wx.YES_NO) == wx.YES:
            self.cities.remove(city)
            for d in (self._row_text, self._row_badges, self._row_seq):
                d.pop(city, None)
            self._row_stale.discard(city)
            self.update_city_list(False)
            # Stay at the same place in the list: the next city, or the new
            # last one, rather than jumping back to the top.
            if self.city_list.GetCount():
                self.city_list.SetSelection(min(sel, self.city_list.GetCount() - 1))
            self.city_list.SetFocus()
            self.update_buttons()

    def on_move_up(self, event):
        self.move_city(-1)

    def on_move_down(self, event):
        self.move_city(1)

    def move_city(self, direction):
        if not self._on_list_page():
            return
        sel = self.city_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        new_sel = sel + direction
        if not (0 <= new_sel < self.city_list.GetCount()):
            return

        self.cities.swap(sel, new_sel)
        t1, t2 = self.city_list.GetString(sel), self.city_list.GetString(new_sel)
        self.city_list.SetString(sel, t2)
        self.city_list.SetString(new_sel, t1)
        self.city_list.SetSelection(new_sel)
        self.update_buttons()

    def on_refresh(self, event):
        if not self._on_list_page():
            # F5 in Full Weather refreshes the report being read.
            if hasattr(self, "current_full_city"):
                city, lat, lon = self.current_full_city
                self.current_full_error = None
                self._fetch_weather(city, lat, lon, "full")
                self._fetch_full_alerts(city, lat, lon)
            return
        sel = self.city_list.GetSelection()
        if sel != wx.NOT_FOUND:
            city = self._city_key_at(sel)
            if not city:
                return
            lat, lon = self.cities.coords(city)
            self._fetch_weather(city, lat, lon, "basic")

    def on_full_weather(self, event):
        if not self._on_list_page() and event is not None:
            return  # Alt+F or the menu while Full Weather is already showing
        sel = self.city_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        city = self._city_key_at(sel)
        if not city:
            return
        lat, lon = self.cities.coords(city)
        self.current_full_city = (city, lat, lon)
        self.day_offset = 0
        self.current_full_data = None
        self.current_full_error = None
        self.lbl_full_title.SetLabel(f"Full Weather - {city}")
        self.full_display.set_message("Loading...")
        self.book.SetSelection(1)
        self.full_display.set_focus()
        self._update_title()
        self._fetch_weather(city, lat, lon, "full")
        self._fetch_full_alerts(city, lat, lon)

    def _fetch_full_alerts(self, city, lat, lon):
        """Load the detailed view's ALERTS section (US only - NWS has no
        coverage elsewhere, so the section is omitted rather than empty)."""
        self.full_alerts = []
        self.full_alert_error = ""
        if not self._is_us_coord(lat, lon):
            self.full_alert_state = "off"
            return
        self.full_alert_state = "loading"
        self.fetch.submit(
            "full_alerts",
            lambda: alert_service.fetch_alerts(lat, lon),
            request_id=city,
        )

    def _on_full_alerts(self, city, alerts, error):
        # Ignore results for a city the user has already navigated away from.
        if (not hasattr(self, "current_full_city")
                or self.current_full_city[0] != city):
            return
        if error:
            self.full_alert_state = "error"
            self.full_alert_error = error
            self.statusbar.SetStatusText(f"Could not check alerts for {city}", 0)
        else:
            self.full_alert_state = "ok"
            self.full_alerts = alerts or []
            n = len(self.full_alerts)
            self.statusbar.SetStatusText(
                f"{n} active alert{'s' if n != 1 else ''} for {city}" if n
                else f"No active alerts for {city}", 0)
        # Until the forecast arrives the report is just "Loading...". Drawing
        # the alerts into it then rebuilt the list an extra time, and the
        # screen reader re-read the heading for each rebuild. The forecast's
        # render includes them.
        if self.current_full_data is not None or getattr(self, "current_full_error", None):
            self._render_full()

    def _open_alert(self, payload):
        """Activate a data row in the detailed view (alert sheet, or retry)."""
        if payload == RETRY:
            city, lat, lon = self.current_full_city
            self._fetch_full_alerts(city, lat, lon)
            self._render_full()
            return
        dlg = AlertDetailDialog(self, payload)
        dlg.ShowModal()
        dlg.Destroy()

    def nav_day(self, direction):
        """Navigate the detailed view by day (direction 0 resets to today)."""
        if self.current_full_data is None:
            return
        if direction == 0:
            self.day_offset = 0
        else:
            self.day_offset = max(-7, min(7, self.day_offset + direction))
        self._render_full()

    def _day_label(self):
        n = self.day_offset
        if n == 0:
            return "Today"
        return f"{'+' if n > 0 else ''}{n} day" + ("s" if abs(n) != 1 else "")

    def _render_full(self):
        if not hasattr(self, "current_full_city"):
            return
        city = self.current_full_city[0]
        data = self.current_full_data

        # Alerts sit directly under the city heading - ahead of the forecast,
        # but never displacing the line that says which city this is. Today
        # only: a warning in force now says nothing about the forecast for
        # another day (matches iOS, which clears alerts for a date offset).
        if self.day_offset == 0:
            alert_lines, alert_rows = section_lines(
                self.full_alert_state, self.full_alerts, self.full_alert_error)
        else:
            alert_lines, alert_rows = [], {}

        if data is None:
            err = getattr(self, "current_full_error", None)
            weather_lines = [f"Report for {city}", "=" * 40,
                             f"Error: {err}" if err else "Loading forecast..."]
        elif self.day_offset == 0:
            weather_lines = build_full_weather_lines(city, data, self.settings, self.fmt)
        else:
            ref = data.get("current", {}).get("time", "")[:10]
            try:
                from datetime import date, timedelta
                target = (date.fromisoformat(ref) + timedelta(days=self.day_offset)).isoformat()
            except Exception:
                return
            weather_lines = build_day_lines(city, data, self.settings, self.fmt, target,
                                            self._day_label())

        # Alerts and forecast arrive independently, so this re-renders while the
        # user may already be reading. Hold their place unless the city or day
        # changed, which would make the old position meaningless.
        key = (city, self.day_offset)
        keep = key == getattr(self, "_last_render_key", None)
        self._last_render_key = key

        # A failed refresh of a report that's showing: keep the old report
        # and say the refresh failed at the end.
        err = getattr(self, "current_full_error", None)
        if data is not None and err:
            weather_lines = list(weather_lines) + [f"Error: couldn't refresh ({err})"]

        # Splice the alerts in after the "Report for <city>" heading and its
        # rule, shifting the activation map to match their new positions.
        lines = list(weather_lines)
        at = min(2, len(lines))
        lines[at:at] = alert_lines
        row_alerts = {i + at: a for i, a in alert_rows.items()}

        self.full_display.set_lines(lines, row_alerts, keep_selection=keep)
        self._update_title()

    def _update_title(self):
        """Keep the window title (the screen reader's window name) contextual."""
        app = "WeatherFast"
        if self.book.GetSelection() == 1 and hasattr(self, "current_full_city"):
            city = self.current_full_city[0]
            # Lead the window name with the worst active alert so the screen
            # reader announces it when the detailed view is entered.
            mark = ""
            if self.day_offset == 0 and self.full_alert_state == "ok":
                top = highest(self.full_alerts)
                if top is not None:
                    mark = f"{top.severity.upper()} ALERT - "
            if self.day_offset == 0:
                self.SetTitle(f"{mark}{city} - Full Weather - {app}")
            else:
                self.SetTitle(f"{city} - {self._day_label()} - {app}")
        else:
            self.SetTitle(f"My Cities - {app}")

    def on_back(self, event):
        self.book.SetSelection(0)
        self.city_list.SetFocus()
        self.statusbar.SetStatusText("Ready", 0)
        self._update_title()

    def on_config(self, event):
        dlg = WeatherConfigDialog(self, self.settings.to_dict())
        if dlg.ShowModal() == wx.ID_OK:
            # The same as Apply: OK used to save without reloading, so the list
            # kept the old units, and it opened Full Weather even from the list.
            self.apply_config_changes(dlg.get_configuration())
        dlg.Destroy()

    def apply_config_changes(self, new_config):
        self.settings.replace(new_config)
        self.save_config()
        self.load_all_weather()
        if hasattr(self, "current_full_city") and self.book.GetSelection() == 1:
            self.on_full_weather(None)

    # -- async result dispatch ------------------------------------------------
    def on_fetch_result(self, event):
        if event.kind == "weather":
            city, seq = event.request_id
            if seq != self._row_seq.get(city):
                return  # superseded by a newer fetch for this city
            if event.error:
                self.on_weather_error(city, event.error)
            else:
                self.on_weather_ready(city, event.payload)
        elif event.kind == "weather_full":
            if event.error:
                self.on_full_weather_error(event.request_id, event.error)
            else:
                self.on_full_weather_ready(event.request_id, event.payload)
        elif event.kind == "geo":
            if event.error:
                self.on_geo_error(event.error)
            else:
                self.on_geo_ready(event.request_id, event.payload)
        elif event.kind == "update_check":
            manual = event.request_id == "manual"
            if manual:
                self.statusbar.SetStatusText("Ready", 0)
            if event.error:
                if manual:
                    wx.MessageBox(f"Could not check for updates: {event.error}",
                                  "Update Check", wx.OK | wx.ICON_WARNING)
                return
            if not event.payload:
                if manual:
                    wx.MessageBox(f"You're up to date (version {__version__}).",
                                  "No Updates", wx.OK | wx.ICON_INFORMATION)
                return
            self._prompt_update(event.payload)
        elif event.kind == "update_download":
            self.statusbar.SetStatusText("Ready", 0)
            if event.error:
                wx.MessageBox(f"Update download failed: {event.error}",
                              "Update", wx.OK | wx.ICON_ERROR)
                return
            updater.launch_installer(event.payload)
            self.Close()
        elif event.kind == "mylocation":
            self.statusbar.SetStatusText("Ready", 0)
            self.mylocation_btn.Enable()
            if event.error:
                wx.MessageBox(f"Could not determine your location: {event.error}",
                              "Location Unavailable", wx.OK | wx.ICON_WARNING)
            else:
                self._add_location_city(event.payload)
        elif event.kind == "alert_badge":
            # Best-effort: never annotate on error (a failed check can't be
            # distinguished from "no alerts", and must not read as either).
            if not event.error:
                self._apply_alert_badge(event.request_id, event.payload or [])
        elif event.kind == "full_alerts":
            self._on_full_alerts(event.request_id, event.payload, event.error)

    @staticmethod
    def _is_us_coord(lat, lon):
        """Rough US coverage test (NWS is US-only): CONUS, AK, HI, PR."""
        boxes = (
            (24.0, 50.0, -125.0, -66.0),   # continental US
            (51.0, 72.0, -170.0, -129.0),  # Alaska
            (18.0, 23.0, -161.0, -154.0),  # Hawaii
            (17.5, 18.6, -67.5, -65.0),    # Puerto Rico
        )
        return any(la0 <= lat <= la1 and lo0 <= lon <= lo1
                   for la0, la1, lo0, lo1 in boxes)

    def _check_alert_badge(self, city, lat, lon):
        """Fire a best-effort NWS alert check for US cities to badge the row."""
        if not self._is_us_coord(lat, lon):  # NWS is US-only
            return
        self.fetch.submit(
            "alert_badge",
            lambda: alert_service.fetch_alerts(lat, lon),
            request_id=city,
        )

    def _apply_alert_badge(self, city, alerts):
        if city not in self.cities:
            return  # removed while the check was in flight
        self._row_badges[city] = city_row_badge(alerts)
        self._refresh_city_row(city)

    def _refresh_city_row(self, city):
        """Repaint a city's row from its weather text plus its alert badge.

        The two arrive from independent fetches, so the row is always composed
        from both rather than appended to in place - otherwise a weather
        refresh silently drops the badge.
        """
        if self._row_text.get(city) is None:
            return
        text = self._row_display(city)
        # By position (the list is in CityStore order), not by text: one name
        # can be the start of another ("X" and "X - Y").
        names = self.cities.names()
        if city in names and names.index(city) < self.city_list.GetCount():
            self.city_list.SetString(names.index(city), text)

    def on_weather_ready(self, city, data):
        """A basic result: today's summary for the city's row."""
        if city not in self.cities:
            return  # removed while the fetch was in flight
        text = city_row_text(city, data, self.fmt)
        if text is None:
            self.on_weather_error(city, "no current conditions")
            return
        self._row_text[city] = text
        self._row_stale.discard(city)
        self._refresh_city_row(city)
        # Best-effort alert badge for US cities (cached 5 min).
        if city in self.cities:
            lat, lon = self.cities.coords(city)
            self._check_alert_badge(city, lat, lon)

    def on_weather_error(self, city, err):
        """A basic fetch failed: say so on the row, instead of Loading for good.

        A row that already has weather keeps it, marked as not refreshed, so
        F5 offline still says something and the old numbers aren't taken as
        current.
        """
        if city not in self.cities:
            return
        if self._row_text.get(city, city_row_error(city)) == city_row_error(city):
            self._row_text[city] = city_row_error(city)
        else:
            self._row_stale.add(city)
        self.statusbar.SetStatusText(f"Couldn't refresh {city}", 0)
        self._refresh_city_row(city)

    def _showing_full(self, city):
        return (self.book.GetSelection() == 1
                and hasattr(self, "current_full_city")
                and self.current_full_city[0] == city)

    def on_full_weather_ready(self, city, data):
        if self._showing_full(city):
            self.current_full_data = data
            self.current_full_error = None
            self._render_full()

    def on_full_weather_error(self, city, err):
        if not self._showing_full(city):
            return
        # Kept in state and rendered, so alerts that arrive (or arrived) are
        # still shown, and a later redraw doesn't drop the error.
        self.current_full_error = err
        self._render_full()

    def on_close(self, event):
        self.fetch.shutdown()
        event.Skip()

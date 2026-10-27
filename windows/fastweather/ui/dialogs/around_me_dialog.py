"""Weather Around Me + Directional Explorer sheet.

Tab 1 shows current weather for 8 compass directions + center at a chosen
radius. Tab 2 (Directional Explorer) lists cached cities along a chosen bearing
with their weather. All results render as accessible lines. Network work runs on
background threads and marshals back with wx.CallAfter.
"""

import threading

import wx

from ...geo import CARDINALS_8
from ...models.weather import condition_summary
from ...services import directional_service, regional_service
from ..accessible_list import AccessibleLinesPanel

_RADII_MI = [50, 100, 150, 200, 250, 300, 350]
_RADII_KM = [80, 160, 240, 320, 400, 480, 560]
_DIR_BEARINGS = dict(CARDINALS_8)


class AroundMeDialog(wx.Dialog):
    def __init__(self, parent, center, settings, fmt, all_cities):
        super().__init__(parent, title=f"Weather Around {center[0]}", size=(760, 620))
        self.center = center
        self.settings = settings
        self.fmt = fmt
        self.all_cities = all_cities
        self._alive = True

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.nb = wx.Notebook(panel)
        self._build_around_tab()
        self._build_explorer_tab()
        vbox.Add(self.nb, 1, wx.EXPAND | wx.ALL, 8)

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

    # -- Around Me tab --------------------------------------------------------
    def _build_around_tab(self):
        p = wx.Panel(self.nb)
        s = wx.BoxSizer(wx.VERTICAL)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(p, label="Radius:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        km = self.settings["units"].get("distance", "mi") == "km"
        self._radii_km = _RADII_KM if km else [round(mi * 1.60934) for mi in _RADII_MI]
        labels = [f"{v} km" for v in _RADII_KM] if km else [f"{mi} mi" for mi in _RADII_MI]
        self.radius_choice = wx.Choice(p, choices=labels)
        cur = self.settings["options"].get("around_me_radius_km", 160)
        self.radius_choice.SetSelection(min(range(len(self._radii_km)),
                                            key=lambda i: abs(self._radii_km[i] - cur)))
        row.Add(self.radius_choice, 0, wx.RIGHT, 8)
        self.around_btn = wx.Button(p, label="Load Weather Around Me")
        row.Add(self.around_btn, 0)
        s.Add(row, 0, wx.ALL, 8)

        self.around_status = wx.StaticText(p, label="Choose a radius and load.")
        s.Add(self.around_status, 0, wx.LEFT | wx.BOTTOM, 8)

        self.around_lines = AccessibleLinesPanel(p, name="Weather around")
        s.Add(self.around_lines, 1, wx.EXPAND | wx.ALL, 8)
        p.SetSizer(s)
        self.nb.AddPage(p, "Around Me")

        self.around_btn.Bind(wx.EVT_BUTTON, self.on_load_around)

    # -- Directional Explorer tab --------------------------------------------
    def _build_explorer_tab(self):
        p = wx.Panel(self.nb)
        s = wx.BoxSizer(wx.VERTICAL)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(p, label="Direction:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.dir_choice = wx.Choice(p, choices=[d for d, _ in CARDINALS_8])
        self.dir_choice.SetSelection(0)
        row.Add(self.dir_choice, 0, wx.RIGHT, 8)

        row.Add(wx.StaticText(p, label="Mode:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.mode_choice = wx.Choice(p, choices=["Arc", "Corridor"])
        self.mode_choice.SetSelection(0 if self.settings["options"].get("around_me_mode", "arc") == "arc" else 1)
        row.Add(self.mode_choice, 0, wx.RIGHT, 8)

        row.Add(wx.StaticText(p, label="Width:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.width_choice = wx.Choice(p, choices=["Narrow", "Standard", "Medium", "Wide"])
        self.width_choice.SetStringSelection(self.settings["options"].get("around_me_width", "Standard"))
        row.Add(self.width_choice, 0, wx.RIGHT, 8)

        self.explore_btn = wx.Button(p, label="Explore")
        row.Add(self.explore_btn, 0)
        s.Add(row, 0, wx.ALL, 8)

        self.explore_status = wx.StaticText(p, label="Pick a direction and explore.")
        s.Add(self.explore_status, 0, wx.LEFT | wx.BOTTOM, 8)

        self.explore_lines = AccessibleLinesPanel(p, name="Cities in that direction")
        s.Add(self.explore_lines, 1, wx.EXPAND | wx.ALL, 8)
        p.SetSizer(s)
        self.nb.AddPage(p, "Directional Explorer")

        self.explore_btn.Bind(wx.EVT_BUTTON, self.on_explore)

    # -- Around Me action -----------------------------------------------------
    def on_load_around(self, event):
        radius_km = self._radii_km[self.radius_choice.GetSelection()]
        self.settings["options"]["around_me_radius_km"] = radius_km
        self.around_btn.Disable()
        self.around_status.SetLabel("Loading (first run reverse-geocodes place names, ~10s)...")
        self.around_lines.set_message("Loading...")
        name, lat, lon = self.center

        def work():
            try:
                result = regional_service.fetch_regional(name, lat, lon, radius_km)
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._around_error, str(e))
                return
            wx.CallAfter(self._around_ready, result)

        threading.Thread(target=work, daemon=True).start()

    def _around_error(self, err):
        if not self._alive:
            return
        self.around_btn.Enable()
        self.around_status.SetLabel(f"Error: {err}")
        self.around_lines.set_message(f"Error: {err}")

    def _around_ready(self, result):
        if not self._alive:
            return
        self.around_btn.Enable()
        fmt = self.fmt
        lines = []
        c = result["center"]
        lines.append(f"Center: {c.name} - {self._tile_wx(c)}")
        lines.append("")
        for t in result["tiles"]:
            lines.append(f"{t.direction} ({fmt.distance(t.distance_km * 1000)}): "
                         f"{t.name} - {self._tile_wx(t)}")
        self.around_status.SetLabel(
            f"Weather within {fmt.distance(result['radius_km'] * 1000)} of {c.name}.")
        self.around_lines.set_lines(lines)
        self.around_lines.set_focus()

    def _tile_wx(self, tile):
        if tile.error:
            return f"unavailable ({tile.error})"
        if tile.temp_c is None:
            return "unavailable"
        cond = condition_summary(tile.weather_code, tile.cloud_cover)
        return f"{self.fmt.temperature_short(tile.temp_c)}, {cond}"

    # -- Explorer action ------------------------------------------------------
    def on_explore(self, event):
        direction = self.dir_choice.GetStringSelection()
        bearing = _DIR_BEARINGS[direction]
        mode = "corridor" if self.mode_choice.GetStringSelection() == "Corridor" else "arc"
        width = self.width_choice.GetStringSelection()
        self.settings["options"]["around_me_mode"] = mode
        self.settings["options"]["around_me_width"] = width
        radius_km = self.settings["options"].get("around_me_radius_km", 160)
        max_km = max(560, radius_km * 3)

        self.explore_btn.Disable()
        self.explore_status.SetLabel(f"Finding cities {direction} of {self.center[0]}...")
        self.explore_lines.set_message("Loading...")
        name, lat, lon = self.center

        def work():
            try:
                cities = directional_service.find_cities(
                    lat, lon, bearing, self.all_cities, mode=mode,
                    width=width, max_distance_km=max_km)
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._explore_error, str(e))
                return
            wx.CallAfter(self._explore_ready, direction, cities)

        threading.Thread(target=work, daemon=True).start()

    def _explore_error(self, err):
        if not self._alive:
            return
        self.explore_btn.Enable()
        self.explore_status.SetLabel(f"Error: {err}")
        self.explore_lines.set_message(f"Error: {err}")

    def _explore_ready(self, direction, cities):
        if not self._alive:
            return
        self.explore_btn.Enable()
        if not cities:
            self.explore_status.SetLabel(f"No cities found {direction} within range.")
            self.explore_lines.set_message("No cities found in that direction/width.")
            return
        lines = []
        for i, c in enumerate(cities, 1):
            dist = self.fmt.distance(c["distance_km"] * 1000)
            if c.get("temp_c") is None:
                wx = "unavailable"
            else:
                cond = condition_summary(c.get("weather_code"), c.get("cloud_cover"))
                wx = f"{self.fmt.temperature_short(c['temp_c'])}, {cond}"
            lines.append(f"{i}. {c['display']} ({dist}) - {wx}")
        self.explore_status.SetLabel(
            f"{len(cities)} cities {direction} of {self.center[0]}.")
        self.explore_lines.set_lines(lines)
        self.explore_lines.set_focus()

    def _on_close(self, event):
        self._alive = False
        event.Skip()

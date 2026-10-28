"""Configure which weather fields display, plus unit selection.

Operates on a plain config dict (a copy of AppSettings.to_dict()); returns the
edited dict via get_configuration(). Apply previews changes live via the
parent's apply_config_changes(new_config).
"""

import copy

import wx


class WeatherConfigDialog(wx.Dialog):
    def __init__(self, parent, current_config):
        super().__init__(parent, title="Configure Weather Display", size=(640, 680))
        self.config = copy.deepcopy(current_config)

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(
            wx.StaticText(panel, label="Select weather details to display:"), 0, wx.ALL, 10
        )

        nb = wx.Notebook(panel)
        self.checkboxes = {"current": {}, "hourly": {}, "daily": {}}
        self.unit_controls = {}

        def add_tab(name, key, options):
            p = wx.Panel(nb)
            sz = wx.BoxSizer(wx.VERTICAL)
            for opt_key, label in options:
                cb = wx.CheckBox(p, label=label)
                cb.SetValue(self.config[key].get(opt_key, False))
                self.checkboxes[key][opt_key] = cb
                sz.Add(cb, 0, wx.ALL, 5)
            p.SetSizer(sz)
            nb.AddPage(p, name)

        add_tab("Current", "current", [
            ("today_outlook", "Today's Outlook"),
            ("condition", "Condition"), ("temperature", "Temperature"),
            ("feels_like", "Feels Like"), ("humidity", "Humidity"),
            ("dew_point", "Dew Point"), ("wind_speed", "Wind Speed"),
            ("wind_direction", "Wind Direction"), ("wind_gusts", "Wind Gusts"),
            ("pressure", "Pressure"), ("visibility", "Visibility"),
            ("uv_index", "UV Index"), ("precipitation", "Precipitation"),
            ("cloud_cover", "Cloud Cover"), ("snowfall", "Snowfall"),
            ("snow_depth", "Snow Depth"), ("rain", "Rain"), ("showers", "Showers"),
        ])
        add_tab("Hourly", "hourly", [
            ("condition", "Condition"), ("temperature", "Temperature"),
            ("feels_like", "Feels Like"), ("humidity", "Humidity"),
            ("dew_point", "Dew Point"), ("precip_probability", "Precip Chance"),
            ("precipitation", "Precipitation"), ("wind_speed", "Wind Speed"),
            ("wind_direction", "Wind Direction"), ("wind_gusts", "Wind Gusts"),
            ("cloud_cover", "Cloud Cover"), ("snowfall", "Snowfall"),
            ("rain", "Rain"), ("showers", "Showers"),
        ])
        add_tab("Daily", "daily", [
            ("condition", "Condition"), ("temperature_max", "High Temp"),
            ("temperature_min", "Low Temp"), ("apparent_max", "Feels High"),
            ("apparent_min", "Feels Low"), ("sunrise", "Sunrise"),
            ("sunset", "Sunset"), ("daylight_duration", "Daylight Duration"),
            ("sunshine_duration", "Sunshine Duration"), ("uv_max", "UV Index Max"),
            ("precipitation_sum", "Precip Total"),
            ("precip_probability_max", "Precip Chance"),
            ("precipitation_hours", "Precip Hours"),
            ("wind_speed_max", "Max Wind"), ("wind_direction_dominant", "Wind Direction"),
            ("snowfall_sum", "Snowfall Total"), ("rain_sum", "Rain Total"),
            ("showers_sum", "Showers Total"),
        ])

        # Units tab
        units_panel = wx.Panel(nb)
        units_sizer = wx.BoxSizer(wx.VERTICAL)

        temp_box = wx.StaticBox(units_panel, label="Temperature")
        temp_sizer = wx.StaticBoxSizer(temp_box, wx.HORIZONTAL)
        self.unit_controls["temp_f"] = wx.RadioButton(
            units_panel, label="Fahrenheit (°F)", style=wx.RB_GROUP
        )
        self.unit_controls["temp_c"] = wx.RadioButton(units_panel, label="Celsius (°C)")
        self.unit_controls["temp_f"].SetValue(self.config["units"].get("temperature", "F") == "F")
        self.unit_controls["temp_c"].SetValue(self.config["units"].get("temperature", "F") == "C")
        temp_sizer.Add(self.unit_controls["temp_f"], 0, wx.ALL, 5)
        temp_sizer.Add(self.unit_controls["temp_c"], 0, wx.ALL, 5)
        units_sizer.Add(temp_sizer, 0, wx.EXPAND | wx.ALL, 10)

        wind_box = wx.StaticBox(units_panel, label="Wind Speed")
        wind_sizer = wx.StaticBoxSizer(wind_box, wx.HORIZONTAL)
        cur_wind = self.config["units"].get("wind_speed", "mph")
        self.unit_controls["wind_mph"] = wx.RadioButton(
            units_panel, label="Miles per hour (mph)", style=wx.RB_GROUP
        )
        self.unit_controls["wind_kmh"] = wx.RadioButton(
            units_panel, label="Kilometers per hour (km/h)"
        )
        self.unit_controls["wind_ms"] = wx.RadioButton(units_panel, label="Meters per second (m/s)")
        self.unit_controls["wind_mph"].SetValue(cur_wind == "mph")
        self.unit_controls["wind_kmh"].SetValue(cur_wind == "km/h")
        self.unit_controls["wind_ms"].SetValue(cur_wind == "m/s")
        wind_sizer.Add(self.unit_controls["wind_mph"], 0, wx.ALL, 5)
        wind_sizer.Add(self.unit_controls["wind_kmh"], 0, wx.ALL, 5)
        wind_sizer.Add(self.unit_controls["wind_ms"], 0, wx.ALL, 5)
        units_sizer.Add(wind_sizer, 0, wx.EXPAND | wx.ALL, 10)

        dist_box = wx.StaticBox(units_panel, label="Distance")
        dist_sizer = wx.StaticBoxSizer(dist_box, wx.HORIZONTAL)
        cur_dist = self.config["units"].get("distance", "mi")
        self.unit_controls["dist_mi"] = wx.RadioButton(
            units_panel, label="Miles (mi)", style=wx.RB_GROUP
        )
        self.unit_controls["dist_km"] = wx.RadioButton(units_panel, label="Kilometers (km)")
        self.unit_controls["dist_mi"].SetValue(cur_dist == "mi")
        self.unit_controls["dist_km"].SetValue(cur_dist == "km")
        dist_sizer.Add(self.unit_controls["dist_mi"], 0, wx.ALL, 5)
        dist_sizer.Add(self.unit_controls["dist_km"], 0, wx.ALL, 5)
        units_sizer.Add(dist_sizer, 0, wx.EXPAND | wx.ALL, 10)

        pres_box = wx.StaticBox(units_panel, label="Pressure")
        pres_sizer = wx.StaticBoxSizer(pres_box, wx.HORIZONTAL)
        cur_pres = self.config["units"].get("pressure", "inHg")
        self.unit_controls["pres_inhg"] = wx.RadioButton(
            units_panel, label="Inches of mercury (inHg)", style=wx.RB_GROUP
        )
        self.unit_controls["pres_hpa"] = wx.RadioButton(units_panel, label="Hectopascals (hPa)")
        self.unit_controls["pres_mmhg"] = wx.RadioButton(units_panel, label="Millimeters of mercury (mmHg)")
        self.unit_controls["pres_inhg"].SetValue(cur_pres == "inHg")
        self.unit_controls["pres_hpa"].SetValue(cur_pres == "hPa")
        self.unit_controls["pres_mmhg"].SetValue(cur_pres == "mmHg")
        pres_sizer.Add(self.unit_controls["pres_inhg"], 0, wx.ALL, 5)
        pres_sizer.Add(self.unit_controls["pres_hpa"], 0, wx.ALL, 5)
        pres_sizer.Add(self.unit_controls["pres_mmhg"], 0, wx.ALL, 5)
        units_sizer.Add(pres_sizer, 0, wx.EXPAND | wx.ALL, 10)

        precip_box = wx.StaticBox(units_panel, label="Precipitation")
        precip_sizer = wx.StaticBoxSizer(precip_box, wx.HORIZONTAL)
        self.unit_controls["precip_in"] = wx.RadioButton(
            units_panel, label="Inches (in)", style=wx.RB_GROUP
        )
        self.unit_controls["precip_mm"] = wx.RadioButton(units_panel, label="Millimeters (mm)")
        self.unit_controls["precip_in"].SetValue(self.config["units"].get("precipitation", "in") == "in")
        self.unit_controls["precip_mm"].SetValue(self.config["units"].get("precipitation", "in") == "mm")
        precip_sizer.Add(self.unit_controls["precip_in"], 0, wx.ALL, 5)
        precip_sizer.Add(self.unit_controls["precip_mm"], 0, wx.ALL, 5)
        units_sizer.Add(precip_sizer, 0, wx.EXPAND | wx.ALL, 10)

        units_panel.SetSizer(units_sizer)
        nb.AddPage(units_panel, "Units")

        vbox.Add(nb, 1, wx.EXPAND | wx.ALL, 10)

        btns = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK)
        apply_btn = wx.Button(panel, wx.ID_APPLY, "Apply")
        cancel_btn = wx.Button(panel, wx.ID_CANCEL)
        # OK is the default, so Enter on a checkbox or radio button means OK.
        # Without one, Enter did nothing, or pressed Apply if Tab had passed it.
        ok_btn.SetDefault()
        btns.AddButton(ok_btn)
        btns.AddButton(apply_btn)
        btns.AddButton(cancel_btn)
        btns.Realize()
        vbox.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        panel.SetSizer(vbox)
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.on_apply, id=wx.ID_APPLY)

    def _harvest(self):
        for section in self.checkboxes:
            for key, cb in self.checkboxes[section].items():
                self.config[section][key] = cb.GetValue()
        self.config["units"]["temperature"] = "F" if self.unit_controls["temp_f"].GetValue() else "C"
        if self.unit_controls["wind_kmh"].GetValue():
            self.config["units"]["wind_speed"] = "km/h"
        elif self.unit_controls["wind_ms"].GetValue():
            self.config["units"]["wind_speed"] = "m/s"
        else:
            self.config["units"]["wind_speed"] = "mph"
        self.config["units"]["precipitation"] = "in" if self.unit_controls["precip_in"].GetValue() else "mm"
        self.config["units"]["distance"] = "mi" if self.unit_controls["dist_mi"].GetValue() else "km"
        if self.unit_controls["pres_hpa"].GetValue():
            self.config["units"]["pressure"] = "hPa"
        elif self.unit_controls["pres_mmhg"].GetValue():
            self.config["units"]["pressure"] = "mmHg"
        else:
            self.config["units"]["pressure"] = "inHg"

    def on_ok(self, event):
        self._harvest()
        self.EndModal(wx.ID_OK)

    def on_apply(self, event):
        self._harvest()
        parent = self.GetParent()
        if parent and hasattr(parent, "apply_config_changes"):
            parent.apply_config_changes(self.config)

    def get_configuration(self):
        return self.config

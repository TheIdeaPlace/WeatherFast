<!-- Generated 2026-11-26 from a read-only code inventory of each app (branch historical-year-jump). Not verified line by line; items marked (verify) need checking. Historical Weather rows reflect this branch. -->

# Feature Parity: iOS, Web, Windows

I had inventories for all three platforms. This report uses only those inventories and has not been checked against the code. Anything marked "(verify)" means an inventory was silent or unclear on that point.

## 1. Parity Matrix

### City list

| Feature | iOS | Web | Windows |
|---|---|---|---|
| Saved city list with current weather | Yes | Yes | Yes |
| Empty state | Yes | Yes | Partial: a starter list is added on first run; no empty state is described (verify) |
| Starter cities on first launch | No | No | Yes |
| View modes (List / Flat / Table) | Partial: Table is Flag (off) | Yes | No: single list only |
| Condensed vs. detailed rows | Yes | Partial: List view only | No |
| Choose and reorder list fields | Yes (about 24 fields) | Yes (12 fields) | No: fixed row of name, temp, condition, precip marker, high/low |
| Alert badge on rows | Yes (NWS plus WeatherKit international) | Partial: U.S. only | Partial: U.S. only |
| Reorder cities | Yes (also to top and to bottom) | Yes (up/down) | Yes (up/down, Alt+U/Alt+D) |
| Remove city with confirmation | Partial: confirms only from the Actions menu | Partial: no confirmation described (verify) | Yes |
| Day navigation (±7 days) | Yes (whole list) | No | Partial: one city at a time, inside Full Weather |
| Automatic GPS "My Location" entry | Yes | No | No |
| Open at Launch | Yes | No | No |
| Glance Ahead (next 1 to 8 hours) | Yes | No | No |

### City management

| Feature | iOS | Web | Windows |
|---|---|---|---|
| Search by city name or ZIP | Yes | Yes | Yes |
| Search by street address or place name | Yes | No: city or ZIP only | Yes |
| Specific place names (airports, etc.) | Yes (flag on) | No | Yes (Settings menu option) |
| Country filter for search | No | Yes | No |
| Choose among multiple matches | Yes | Yes | Yes (always confirms, up to 8 results) |
| Add current location | Yes (GPS) | Yes (browser location) | Yes (device location, with an IP lookup fallback) |

### Refresh and offline

| Feature | iOS | Web | Windows |
|---|---|---|---|
| Automatic refresh | Yes (on launch and on return to foreground) | Partial: loads when opened, no timer (verify) | Partial: on launch only |
| Refresh all cities | Yes (pull to refresh) | Yes (Ctrl+R) | Partial: refreshes only the selected city (verify) |
| Cached or offline weather | Yes (24-hour disk cache plus a "cached data" banner) | Partial: app shell works offline, weather does not | Partial: keeps old values marked "(couldn't refresh)" |
| Load-failure message with retry | Yes | No (verify) | Partial: error shown on the row |
| Installable / works offline as an app | n/a | Yes (PWA) | n/a |

### Browse

| Feature | iOS | Web | Windows |
|---|---|---|---|
| Browse U.S. states and countries with live weather | Yes | Yes | Yes |
| Add from browse | Yes | Yes | Yes (checklist, add several at once) |
| Remove from browse | Yes | Yes | No |
| Sort browsed cities | Yes | Partial: by name only | Yes |
| Search inside browse lists | Yes | No (verify) | No (verify) |
| Browse favorites | Yes | No | Yes (states and countries) |
| Places of the World | Yes (flag on) | No | No |
| Browse radar stations | Flag (off) | No | No |

### Alerts

| Feature | iOS | Web | Windows |
|---|---|---|---|
| U.S. NWS alerts for a city | Yes | Yes | Yes |
| International alerts for a city | Yes (WeatherKit) | No | No |
| Alert detail view | Yes | Yes | Yes |
| Alerts section in the detail view | Yes | Partial: badge only (verify) | Yes (today only) |
| A failed check is never shown as "no alerts" | Yes | No (verify) | Yes |
| Browse Alerts by region | Yes (U.S., Canada, Europe) | No | Partial: U.S. and Canada only, no MeteoAlarm |
| Save alert filters as defaults | Yes (syncs across devices) | No | Yes |

### City detail

| Feature | iOS | Web | Windows |
|---|---|---|---|
| Full detail view | Yes | Yes (dialog) | Yes (list view) |
| Current conditions | Yes | Yes | Yes |
| Plain-language today outlook | Yes | Partial: Today block on cards (high, low, sunrise, sunset) | Yes |
| 24-hour forecast | Yes | Yes | Yes |
| 16-day forecast | Yes | Yes | Yes ("multi-day"; length to verify) |
| Choose fields per section | Yes (and reorder) | Yes (no reorder) | Yes (no reorder) |
| Turn sections on/off and reorder them | Yes | Partial: display mode per section only | Partial: sections follow Configure (verify) |
| Display mode per section | Partial: List or Headings | Yes (flat, table or list) | No: always a list |
| Day Detail screen | Yes | No | Partial: day navigation shows a summary plus hourly |
| Share, copy or save the report | Yes (Share sheet) | No | Yes (copy, or save as text) |
| Air quality | Yes (AirNow, U.S. only) | No | Partial: My Data parameters only (modeled) |
| Pollen | No (verify) | No | Partial: My Data only |
| Marine forecast | Yes (includes tides) | No | Partial: no sea level or tides |
| Astronomy | Yes (phase, illumination, moonrise, moonset) | No | Partial: phase, illumination, age, next new and full moon; no moonrise or moonset |
| Location section | Yes | No | No |
| My Data custom report | Yes (flag on) | No | Yes (adds pollen) |

### Expected precipitation and radar

| Feature | iOS | Web | Windows |
|---|---|---|---|
| Expected precipitation (nowcast) | Yes (minute by minute, WeatherKit, chart) | Partial: 2 hours at fixed points | Partial: next hour in 15-minute steps, text |
| Audio graph | Yes | No | No |
| Radar loop | Flag (off) | No | No |

### Historical weather

| Feature | iOS | Web | Windows |
|---|---|---|---|
| Single Day | Yes | Yes | Yes |
| Browse Days | Yes (30 days) | Yes (30 days) | Yes (1 to 31 days, default 7) |
| Same date across years (iOS "History" = Web "Same Day Across Years" = Windows "Multi-Year") | Yes (1 to 85 years, set in Settings) | Partial: fixed at 20 years (verify) | Yes (1 to 85, default 20) |
| Previous/Next stepping | Yes | Yes | Yes |
| Previous Year / Next Year in Browse Days | Yes | Yes | Yes |
| Date picker plus Today button | Yes | Yes | Partial: picker and Load; no Today button listed (verify) |
| Spoken load results and errors | (verify) | Yes | Yes (per commit 956d795; not in the inventory) |
| Clear historical cache | Yes | No | No (cache is permanent) |

### Weather Around Me

| Feature | iOS | Web | Windows |
|---|---|---|---|
| Comparison in 8 directions | Yes | Yes | Yes |
| Directional explorer | Yes | No | Partial: lists cities; no Closer/Farther stepping (verify) |
| Weather movement, pressure trends, alerts | Yes | No | No |

### Settings, help, platform

| Feature | iOS | Web | Windows |
|---|---|---|---|
| Units | Yes | Partial: no mmHg | Yes (adds wind in m/s) |
| Unit defaults from locale | Yes | No (verify) | Yes |
| Reset cities and settings | Yes | Yes | Partial: `--reset` command-line flag for cities only |
| Sync across devices | Yes (iCloud) | No | No |
| Data sources / attribution page | Yes | Partial: footer credit only | Partial: About shows the version only (verify) |
| User guide | Yes (flag on) | Yes | Yes (opens in browser, F1) |
| Screen reader announcements | Yes | Yes (live region) | Partial: status bar messages (verify that screen readers speak them) |
| Keyboard shortcuts | Partial: only Cmd+Shift+N | Yes | Yes (full set, menu access keys) |
| Home and Lock Screen widgets | Yes | No | No |
| Notifications | No | No | No |
| Updates | App Store | Yes (service worker reloads the page) | Yes (GitHub Releases updater) |
| Feature flags / developer settings | Yes | No (has a Debug console) | No |
| Command-line options | n/a | n/a | Yes |
| Manifest "Refresh Weather" shortcut | n/a | Partial: declared but never handled (bug) | n/a |

## 2. Gaps, Ranked

Ranking puts safety and screen-reader value first, then everyday use, then extras. Effort: S = small, M = medium, L = large.

| # | Gap | Platforms | Effort | Note |
|---|---|---|---|---|
| 1 | Detail view has no alerts section, and a failed check may read as "no alerts" | Web | S | Safety issue. iOS and Windows both handle this correctly (verify Web behavior). |
| 2 | No international alerts for a city | Web, Windows | M | Partly inherent: WeatherKit is Apple-only, and its REST API would need a key held on a server (risky for Web). ECCC and MeteoAlarm are already used in Browse Alerts, so per-city lookups could reuse them. |
| 3 | City list rows are fixed; no field choice or condensed mode | Windows | M | High screen-reader value, because the row is what gets spoken while arrowing through the list. |
| 4 | Directional explorer missing (Web) or without Closer/Farther stepping (Windows) | Web, Windows (verify) | M | Memory notes calls the explorer a "crown jewel". Web's radius also stops at 250 mi (S to raise). |
| 5 | Browse Alerts missing (Web), no Europe (Windows) | Web, Windows | M/L | |
| 6 | Day navigation missing (Web), per city only (Windows) | Web, Windows | M | |
| 7 | No plain-language today outlook | Web | S | Logic exists on iOS and Windows to port. |
| 8 | Air quality missing (Web), modeled-only via My Data (Windows) | Web, Windows | M | AirNow needs an API key, so Web would need a proxy (verify). Air quality is U.S.-only by data source. |
| 9 | No street-address or place-name search, no specific place names | Web | S | Nominatim already supports both. |
| 10 | Day Detail missing (Web), partial (Windows) | Web, Windows | M | |
| 11 | Remove has no confirmation (Web, verify); iOS confirms only from the Actions menu | Web, iOS | S | |
| 12 | No refresh-all (verify) and no automatic refresh | Windows | S | |
| 13 | No load-failure message with retry | Web | S | |
| 14 | No automatic My Location entry | Web, Windows | M | Partly inherent: browser location permission and Windows location access behave differently from iOS. |
| 15 | No Glance Ahead | Web, Windows | S | |
| 16 | No Open at Launch | Web, Windows | S | |
| 17 | Coarse nowcast | Web, Windows | S | Minute-by-minute data is WeatherKit, which is inherent. Web (2 hours) and Windows (1 hour) should at least match each other. |
| 18 | Browse: no sort, search or favorites (Web); no remove or search (Windows) | Web, Windows | S | |
| 19 | Same Day Across Years fixed at 20 years | Web (verify) | S | |
| 20 | Weak keyboard support | iOS | S/M | Matters for iPad and hardware-keyboard users. |
| 21 | No Marine, Astronomy or My Data | Web | M each | Windows astronomy has no moonrise or moonset (S); Windows marine has no tides (S). |
| 22 | Places of the World | Web, Windows | S/M | The JSON file is shared; the project notes say iOS-only "for now". |
| 23 | Missing unit options: mmHg (Web), m/s wind (iOS, Web), locale defaults (Web) | iOS, Web | S | |
| 24 | Clear historical cache | Web, Windows | S | |
| 25 | No add-several-at-once in Browse, no copy/save as text, no country filter | iOS | S | Low value; Share covers copy. |
| 26 | Manifest "Refresh Weather" shortcut does nothing | Web | S | A real bug. |
| 27 | Weak attribution page | Web, Windows | S | |
| 28 | Sync across devices | Web, Windows | L | Inherent: iCloud. Would need an account service. |
| 29 | Widgets | Web, Windows | L | Inherent to the platforms. |
| 30 | Radar loop and radar stations | Web, Windows | L | Inherent: NEXRAD/IEM tiles are U.S.-only, plus ECCC for Canada. Also Flag (off) on iOS. |
| 31 | Audio graph, custom actions | Web, Windows | n/a | Inherent: these are VoiceOver and Apple APIs. |

## 3. Where the Platforms Disagree on Behavior

**Historical weather**
- **Names:** iOS uses "Single Day / Browse Days / History". Web uses "Same Day Across Years / Single Day / Browse Days". Windows uses "Single Day / Daily Browse / Multi-Year".
- **Where the archive ends:** all three go to today (iOS warns that today may be incomplete). Windows Multi-Year windows end last year.
- **Default view:** Web opens on Same Day Across Years. iOS and Windows (verify).
- **Browse Days length:** iOS and Web use 30 days. Windows lets you choose 1 to 31 days, default 7, and labels buttons by the count ("Next 7 Days").
- **Years across:** iOS sets 1 to 85 in Settings. Web is fixed at 20 and steps 20 years at a time (verify). Windows uses 1 to 85, default 20, remembered, with the count in the button label.
- **At the archive edges:** Web marks the buttons aria-disabled but keeps focus on them. iOS and Windows disable them.
- **Feb 29:** all three fall back to Feb 28 in non-leap years, for year jumps and for the same day across years.

**Weather Around Me**
- **Radius:** iOS 50 to 350 mi (80 to 560 km). Web 50 to 250 mi, default 150 (80 to 400 km, default 240). Windows about 50 to 350 mi, remembered.

**Alerts**
- **Badge:** iOS shows a severity icon. Web uses a colored badge. Windows appends text, for example "[EXTREME: Tornado Warning, +1 more]", and caches the check for 5 minutes.
- **Sources:** iOS uses NWS plus WeatherKit. Web and Windows use NWS only.

**Adding a city**
- **Search provider:** iOS uses CLGeocoder for ZIP codes and the Apple Maps place search for everything else. Web and Windows use Nominatim.
- **Confirmation:** Windows always shows a confirmation dialog, even for a single result. Web shows a dialog only when there are several matches.

**Current location**
- iOS uses GPS. Web uses browser location plus reverse geocoding. Windows asks first, then uses device location with an ipapi.co fallback.

**Refresh**
- **iOS:** automatic on launch and on return to the foreground, with a 10-minute in-memory cache.
- **Web:** Ctrl+R refreshes every city. This overrides the browser's own reload shortcut.
- **Windows:** loads on launch; F5 or Ctrl+R refreshes the selected city, or the whole report when Full Weather is open.

**Remove and reorder**
- **Confirmation:** iOS confirms only from the Actions menu. Windows always confirms. Web never confirms (verify).
- **Reorder options:** only iOS has Move to Top and Move to Bottom.

**Units**
- **Pressure:** iOS and Windows offer hPa, inHg and mmHg. Web offers inHg and hPa only.
- **Wind:** only Windows offers m/s.
- **Defaults:** iOS follows the device locale; Windows follows the Windows region, including the usual wind unit for that country.

**Expected precipitation**
- iOS is minute by minute (WeatherKit, with Open-Meteo as fallback). Web shows now plus 6 points up to 120 minutes. Windows shows 60 minutes in 15-minute steps.

**Fields**
- **City list:** iOS offers about 24 fields, Web 12, and Windows has a fixed row.
- **Hourly:** Web includes feels like and humidity; neither appears in the iOS hourly list (verify).
- **Daily:** only Web omits feels-like high and low.

**Browse**
- **Adding:** iOS and Web use a per-city add/remove toggle. Windows uses a checklist with Add Selected, and cities already saved are skipped.
- **Sort:** iOS offers alphabetical, geographic and temperature. Web sorts by name only. Windows offers name, north-south, east-west and temperature.

**Keyboard**
- **Add city:** Cmd+Shift+N on iOS; Alt+N moves to the add-city field on Windows.
- **Configure:** Alt+G on Web, Alt+C on Windows.
- **Use my location:** Alt+L on Web only.

**Help**
- iOS has an in-app guide. Web has a separate page with JAWS, NVDA and Narrator tips. Windows opens the guide in the browser with F1.
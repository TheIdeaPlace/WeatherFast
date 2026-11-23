# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

FastWeather is a multi-platform accessibility-first weather app with three independent platform implementations that share city coordinate data:

| Platform | Directory | Language/Stack |
|----------|-----------|---------------|
| iOS | `iOS/` | Swift / SwiftUI (iOS 17+) |
| Web/PWA | `webapp/` | Vanilla HTML/CSS/JS |
| Windows Desktop | `windows/` | Python + wxPython |
| City Data | `CityData/` | Python (geocoding scripts) |

All platforms use [Open-Meteo](https://open-meteo.com/) (no API key required for free tier) for weather data and share pre-geocoded city coordinate files (`us-cities-cached.json`, `international-cities-cached.json`).

---

## iOS (Swift/SwiftUI)

### Build & Run

```bash
# Open project in Xcode
open iOS/FastWeather.xcodeproj

# Build from CLI
xcodebuild -project iOS/FastWeather.xcodeproj \
    -scheme FastWeather \
    -configuration Debug \
    -sdk iphonesimulator \
    -destination 'platform=iOS Simulator,name=iPhone 17,OS=26.2' \
    build
```

### Tests

```bash
# Run all tests via Xcode: Cmd+U
# Or from CLI:
xcodebuild test \
    -project iOS/FastWeather.xcodeproj \
    -scheme FastWeather \
    -destination 'platform=iOS Simulator,name=iPhone 17,OS=26.2'
```

Test files are in `iOS/FastWeatherTests/`. The module name is `WeatherFast` (used in `@testable import WeatherFast`).

### First-Time Setup — Secrets.swift

`iOS/FastWeather/Services/Secrets.swift` is gitignored and must be created locally before building:

```swift
// Secrets.swift
enum Secrets {
    // Set to nil to use free Open-Meteo tier (rate-limited)
    static let openMeteoAPIKey: String? = nil
}
```

When set, the key routes requests to dedicated Open-Meteo servers (`customer-*.open-meteo.com`). Without it, the app falls back to the free tier.

### Architecture

MVVM with a shared service layer. Services are singletons injected as `@EnvironmentObject` at the app root (`WeatherFastApp.swift`).

**Key services:**
- `WeatherService` — fetches weather from Open-Meteo; manages `savedCities` persisted to UserDefaults; holds an in-memory `weatherCache: [UUID: WeatherData]`
- `WeatherCache` — disk-based cache (separate from WeatherService's in-memory cache); used for longer-lived caching across app launches
- `HistoricalWeatherCache` — separate disk cache for historical data
- `SettingsManager` — wraps `AppSettings` (Codable struct) persisted to UserDefaults; also owns `DateParser` and `FormatHelper` utilities
- `FeatureFlags` — singleton (`FeatureFlags.shared`) that gates in-development features; always access via `.shared`, never instantiate directly
- `LocationService` — CoreLocation wrapper; provides current device location for "Weather Around Me" and the geolocation city search
- `CityDataService` — loads the bundled city JSON files at startup
- `BrowseFavoritesService` — manages favorites within the Browse Cities tab (persisted separately from `savedCities`)
- `RadarService` — fetches precipitation nowcast data (used when `radarEnabled` flag is on)
- `RegionalWeatherService` — fetches weather for nearby cities (used when `weatherAroundMeEnabled` flag is on)

**Critical patterns:**
- Open-Meteo timestamps use format `"yyyy-MM-dd'T'HH:mm"` — always parse via `DateParser.parse()`, never `ISO8601DateFormatter`
- Time display always via `FormatHelper.formatTime()` / `FormatHelper.formatTimeCompact()`
- NWS weather alerts are U.S.-only (`api.weather.gov`); international alerts use WeatherKit when `weatherKitAlertsEnabled` is on
- Historical weather API endpoint: `archive-api.open-meteo.com/v1/archive` (1940–yesterday)
- Logging: use `AppLogger.service`, `.network`, `.persistence`, or `.location` (backed by `os.Logger`) — never bare `print()`

**Tab structure:**
```
ContentView (TabView)
├── MyCitiesView → delegates to ListView / TableView / FlatView
├── BrowseCitiesView → StateCitiesView (state/country drill-down)
└── SettingsView → DeveloperSettingsView (feature flag toggles)
```

Feature-flagged views (`RadarView`, `WeatherAroundMeView`, `HistoricalWeatherView`) are presented as sheets from `CityDetailView`, not as tabs.

**Accessibility (non-negotiable):**
- Use `.accessibilityElement(children: .ignore)` (not `.combine`) with explicit `.accessibilityLabel()`
- All buttons need `.accessibilityHint()`
- All decorative images need `.accessibilityHidden(true)`
- Test with VoiceOver before marking UI work complete

### Feature Flags

All flags are toggled in `DeveloperSettingsView` (Settings → Developer Settings). Each persists to `UserDefaults`.

| Flag | Default | Description |
|------|---------|-------------|
| `radarEnabled` | `true` | Expected Precipitation sheet in CityDetail |
| `weatherAroundMeEnabled` | `true` | Weather Around Me regional comparison |
| `userGuideEnabled` | `true` | User guide link in Settings |
| `weatherKitAlertsEnabled` | `true` | WeatherKit alerts for non-US cities |
| `myDataEnabled` | `true` | Custom "My Data" section in CityDetail |
| `tableViewEnabled` | `false` | Table view mode (experimental, has text-clipping issues) |
| `weatherKitSnowEnabled` | `true` | Use WeatherKit daily snow totals instead of Open-Meteo |
| `weatherKitNowcastEnabled` | `true` | Use WeatherKit minute-by-minute nowcast for precipitation |
| `weatherKitConditionsEnabled` | `true` | Use WeatherKit's observation-informed current condition instead of Open-Meteo's model `weather_code` for "now" (today only; unmappable conditions fall back to Open-Meteo) |
| `specificPlaceNamesEnabled` | `true` | Show specific place names (airports, universities, streets) instead of city-only labels; when off, searches fall back to locality-only |
| `myLocationEnabled` | `true` | Show the My Location section on the city list; when off, the whole My Location feature is hidden |
| `placesOfTheWorldEnabled` | `true` | Places of the World entry in Browse (curated bridges, beaches, extreme-weather places from `places-of-the-world.json`) |

**Adding a feature-flagged feature:**
1. Add `@Published var featureEnabled: Bool` to `FeatureFlags.swift`
2. Add toggle in `DeveloperSettingsView.swift`
3. Gate in views with `if featureFlags.featureEnabled { ... }`

### Releasing (TestFlight & App Store)

**Full guide: [`iOS/RELEASING.md`](iOS/RELEASING.md) — read it before any release step.**

⛔ **Golden rule:** this dev Mac runs a **beta macOS**, so any App Store binary built
locally is rejected as `INVALID_BINARY` (regardless of Xcode). **App Store builds must
come from the GitHub Actions workflow** `.github/workflows/ios-release.yml` (released-macOS
runner): `gh workflow run ios-release.yml -f build_number=<N>`, then attach the build to the
App Store version and submit via `iOS/scripts/asc.py` (the App Store Connect client;
`python3 iOS/scripts/asc.py check` signs in and finds the app, read-only). **TestFlight** builds may be local:
`iOS/scripts/release-testflight.sh`. The App Store Connect key comes from the signing kit,
`~/.signing-kit/asc-api-key.p8` (key `38ANZ53D9L`; restore the folder with
`python3 <projects repo>/signing/sync-secrets.py pull-kit`). The CI signing secrets are
TheIdeaPlace organization secrets set by `sync-secrets.py`; never set them on this repo by
hand. `~/.fastweather-keys/` is retired: its `asc.py` is now in the repo, and the WeatherKit
key the data tools use is in the kit too. See `signing/README.md` in
kellylford/The-Idea-Place-Projects. Key gotchas: binary `CFBundleShortVersionString` ≤ 3 integers (the 4-part
`X.Y.Z.build` label goes on the store version record only); build numbers are single-use.

---

## Web/PWA

### Run Locally

```bash
cd webapp
npm run serve        # starts python http.server on port 8000
```

### Tests

```bash
cd webapp
npm test                 # all tests (jest + jsdom)
npm run test:unit        # unit tests only (*.unit.test.js)
npm run test:integration # integration tests only (*.integration.test.js)
npm run test:a11y        # accessibility tests only (jest-axe, *.a11y.test.js)
npm run test:coverage
```

### Architecture

Single-page vanilla JS app — no framework. Core files: `app.js` (all logic), `index.html`, `styles.css`, `service-worker.js` (offline PWA). City data loaded from `us-cities-cached.json` and `international-cities-cached.json` at runtime.

Deployed to `weatherfast.online`. See `webapp/DEPLOYMENT.md` for the upload checklist. Never upload `debug.html`, `build-city-cache.py`, or `table-test.html` to production.

---

## Windows Desktop

### Run from Source

```bash
cd windows
pip install -r requirements.txt
python fastweather.py
```

### Build Executable

```bash
cd windows
python build.py      # produces dist/ executable via PyInstaller
```

---

## Diagnostic Tools (`tools/`)

Out-of-app testing/diagnostic tools follow a fixed pattern — keep it for any new tool:

- **Tools live in `tools/` on `main`** (single source of truth; every new branch inherits them). Develop new tools on main or merge them there promptly.
- **They are run from OneDrive** (`~/Library/CloudStorage/OneDrive-Personal/RadarData/`) via Finder `.command` wrappers. Each wrapper resolves `tools/` via `fastweather-tools-sync.sh` (in that folder): normally the checked-out repo's `tools/` (every branch carries it), with a `git archive` fallback to main's copy for old branches that predate `tools/`.
- **Results always log to the RadarData folder** (per-run subfolders), never into the repo.
- New tools: `tools/<area>/`, Python-stdlib-only where possible, accept an output-root flag, plus a `.command` wrapper in RadarData.

Current tools: `tools/datatesting/` (nowcast data validation) and `tools/quickradar/` (radar image lab). See `tools/README.md`.

---

## City Data (Shared Across Platforms)

Pre-geocoded city files live in `CityData/` and are copied to each platform. Rebuild only when adding cities/countries.

```bash
cd CityData
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python build-city-cache.py            # US cities (~2-3 hours)
python build-international-cache.py   # International (~40-50 min)

# After rebuilding, distribute to all platforms:
./distribute-caches.sh               # macOS/Linux
# distribute-caches.bat               # Windows
```

**Places of the World** (`CityData/places-of-the-world.json`) is hand-curated, not geocoded: an array of categories, each with up to 200 places (`name`, `description`, optional `city`/`state`, `country`, `lat`, `lon`). Open-Meteo uses the elevation at the exact coordinates, so summits and weather stations must be pinned on the spot itself. Run `python3 verify-places.py` after editing (structure checks plus a Nominatim country check, cached), then `./distribute-caches.sh`. iOS only for now.

Current coverage: 93 countries (~20 cities each) + 50 US states (50 cities each) = ~4,360 pre-geocoded locations. Scripts respect Nominatim's 1 req/sec rate limit and are resumable.

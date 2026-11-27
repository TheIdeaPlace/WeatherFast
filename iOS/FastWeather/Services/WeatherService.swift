//
//  WeatherService.swift
//  Fast Weather
//
//  Service for fetching weather data from Open-Meteo API
//

import Foundation
import Combine
import CoreLocation
#if canImport(WeatherKit)
import WeatherKit
#endif

// MARK: - WeatherCacheKey
/// Cache key for date-aware weather data
/// Allows caching weather for the same city on different days
struct WeatherCacheKey: Hashable {
    let cityId: UUID
    let dateOffset: Int  // 0 = today, +1 = tomorrow, -1 = yesterday
    
    init(cityId: UUID, dateOffset: Int = 0) {
        self.cityId = cityId
        self.dateOffset = dateOffset
    }
}

@MainActor
class WeatherService: ObservableObject {
    @Published var savedCities: [City] = []
    @Published var weatherCache: [WeatherCacheKey: WeatherData] = [:]
    @Published var marineCache:     [WeatherCacheKey: MarineData] = [:]
    @Published var browseWeatherCache: [String: WeatherData] = [:] // Cache for browse cities (basic)
    @Published var browseWeatherFullCache: [String: WeatherData] = [:] // Cache for browse cities (full)
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    /// Incremented every time refreshAllWeather() runs, triggering alert re-fetch in views
    @Published var alertsRefreshID: Int = 0
    /// Cache keys whose last fetch attempt failed (network error, timeout, bad response).
    /// Views use this to show an error state instead of an infinite spinner.
    @Published var failedCacheKeys: Set<WeatherCacheKey> = []
    
    // DISABLED: Persistent cache is too slow (8.9s to load from UserDefaults)
    // Only using in-memory cache for now
    // private let persistentCache = WeatherCache.shared
    
    private var baseURL: String {
        Secrets.openMeteoAPIKey != nil
            ? "https://customer-api.open-meteo.com/v1/forecast"
            : "https://api.open-meteo.com/v1/forecast"
    }
    // Historical API is NOT included in the Standard paid plan — always use free tier.
    private let historicalURL = "https://archive-api.open-meteo.com/v1/archive"
    private var marineURL: String {
        Secrets.openMeteoAPIKey != nil
            ? "https://customer-marine-api.open-meteo.com/v1/marine"
            : "https://marine-api.open-meteo.com/v1/marine"
    }
    private var airQualityURL: String {
        Secrets.openMeteoAPIKey != nil
            ? "https://customer-air-quality-api.open-meteo.com/v1/air-quality"
            : "https://air-quality-api.open-meteo.com/v1/air-quality"
    }
    private let userDefaultsKey = "SavedCities"
    private var sharedDefaults: UserDefaults {
        UserDefaults(suiteName: AppGroup.suiteName) ?? .standard
    }
    
    /// Wraps a URL in a URLRequest with the required User-Agent header.
    /// Appends the Open-Meteo API key when configured and applies a 15-second timeout
    /// (suitable for current/forecast data; historical overrides this to 30s).
    private func apiRequest(for url: URL, timeout: TimeInterval = 15) -> URLRequest {
        var finalURL = url
        if let key = Secrets.openMeteoAPIKey, !key.isEmpty {
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
            var items = components?.queryItems ?? []
            items.append(URLQueryItem(name: "apikey", value: key))
            components?.queryItems = items
            finalURL = components?.url ?? url
        }
        var request = URLRequest(url: finalURL, timeoutInterval: timeout)
        request.setValue("FastWeather/1.5 (weatherfast.online)", forHTTPHeaderField: "User-Agent")
        return request
    }

    /// Executes an Open-Meteo API request and returns the raw response data.
    /// Retries transient failures — request timeouts, dropped connections, and
    /// HTTP 429/5xx rate-limit or server errors — up to `maxRetries` times with
    /// exponential backoff before giving up. Without this, a single network blip or
    /// rate-limit spike drops the caller back to stale/partial (light) cached data,
    /// which is what produced the "only a few days" / "missing hourly" reports.
    /// A non-transient non-200 status decodes the Open-Meteo error body
    /// ({"error":true,"reason":"..."}) and throws a descriptive NSError rather than
    /// letting the caller receive a generic DecodingError on the response body.
    private func apiData(for url: URL, timeout: TimeInterval = 15, maxRetries: Int = 2) async throws -> Data {
        var attempt = 0
        while true {
            do {
                let request = apiRequest(for: url, timeout: timeout)
                let (data, response) = try await URLSession.shared.data(for: request)
                if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode != 200 {
                    // Retry rate-limit (429) and server (5xx) errors; surface everything else.
                    if Self.isRetryableStatus(httpResponse.statusCode), attempt < maxRetries {
                        attempt += 1
                        try await Task.sleep(nanoseconds: Self.backoffNanoseconds(forAttempt: attempt))
                        continue
                    }
                    if let errorBody = try? JSONDecoder().decode(OpenMeteoErrorResponse.self, from: data),
                       errorBody.error {
                        throw NSError(domain: "OpenMeteo", code: httpResponse.statusCode,
                                      userInfo: [NSLocalizedDescriptionKey: errorBody.reason ?? "Unknown API error"])
                    }
                    throw URLError(.badServerResponse)
                }
                return data
            } catch {
                // Retry transient network errors (timeout, connection lost, DNS blip).
                if Self.isTransientNetworkError(error), attempt < maxRetries {
                    attempt += 1
                    try? await Task.sleep(nanoseconds: Self.backoffNanoseconds(forAttempt: attempt))
                    continue
                }
                throw error
            }
        }
    }

    /// HTTP statuses worth retrying: rate limiting and transient server-side faults.
    private static func isRetryableStatus(_ status: Int) -> Bool {
        status == 429 || (500...599).contains(status)
    }

    /// Transient client-side network failures that a brief retry can clear. Deliberately
    /// excludes `.notConnectedToInternet` (no point retrying a device that's offline) and
    /// `.badServerResponse` (already decided not to retry that status above).
    private static func isTransientNetworkError(_ error: Error) -> Bool {
        guard let urlError = error as? URLError else { return false }
        switch urlError.code {
        case .timedOut, .networkConnectionLost, .cannotConnectToHost,
             .cannotFindHost, .dnsLookupFailed:
            return true
        default:
            return false
        }
    }

    /// Exponential backoff: ~0.5s before the first retry, ~1.5s before the second —
    /// long enough to clear a blip, short enough not to strand the UI.
    private static func backoffNanoseconds(forAttempt attempt: Int) -> UInt64 {
        let seconds = 0.5 * pow(3.0, Double(attempt - 1))
        return UInt64(seconds * 1_000_000_000)
    }
    
    // Cache durations
    // Current weather changes every ~10 min; future days change at most once per hour.
    private let currentWeatherCacheDuration: TimeInterval = 10 * 60       // 10 minutes
    private let forecastWeatherCacheDuration: TimeInterval = 60 * 60      // 1 hour
    private let browseCacheDuration: TimeInterval = 10 * 60               // 10 minutes
    // Maximum number of in-memory weather and marine cache entries (oldest evicted first).
    private let maxWeatherCacheEntries = 50
    private let maxBrowseCacheEntries  = 100
    // Paid tier (dedicated servers) has no concurrent limit; free tier is 1-in-flight + 5 queued.
    private let maxConcurrentRequests = Secrets.openMeteoAPIKey != nil ? 5 : 1
    
    // Cache timestamp tracking
    private var cacheTimestamps: [WeatherCacheKey: Date] = [:]
    private var marineCacheTimestamps: [WeatherCacheKey: Date] = [:]
    private var browseCacheTimestamps: [String: Date] = [:]
    private var browseFullCacheTimestamps: [String: Date] = [:]
    
    init() {
        loadSavedCities()
        migrateCountryNamesIfNeeded()
        observeCloudCityChanges()
    }
    
    // MARK: - My Data Dynamic Parameters
    
    /// Loads the persisted AppSettings without coupling to SettingsManager.
    /// Reads from the App Group suite (where SettingsManager writes after migration),
    /// falling back to standard defaults for pre-migration / edge cases. Reading from
    /// `.standard` alone silently dropped My Data parameters on fresh installs — see CR-2.
    private static func loadPersistedSettings() -> AppSettings? {
        let suite = UserDefaults(suiteName: AppGroup.suiteName)
        if let data = suite?.data(forKey: "AppSettings"),
           let settings = try? JSONDecoder().decode(AppSettings.self, from: data) {
            return settings
        }
        if let data = UserDefaults.standard.data(forKey: "AppSettings"),
           let settings = try? JSONDecoder().decode(AppSettings.self, from: data) {
            return settings
        }
        return nil
    }

    /// Appends user-selected My Data API parameters to the base current params string.
    /// Reads directly from UserDefaults to avoid coupling to SettingsManager.
    static func appendMyDataParameters(to baseParams: String) -> String {
        guard let settings = loadPersistedSettings() else {
            return baseParams
        }
        
        let enabledParams = settings.myDataFields.filter { $0.isEnabled }
        guard !enabledParams.isEmpty else { return baseParams }
        
        let existingKeys = Set(baseParams.split(separator: ",").map { String($0) })
        let newKeys = enabledParams
            .map { $0.parameter.apiKey }
            .filter { !existingKeys.contains($0) }
        
        if newKeys.isEmpty { return baseParams }
        return baseParams + "," + newKeys.joined(separator: ",")
    }
    
    /// Fetches marine current values for selected My Data parameters.
    /// Returns a dictionary of API key -> value for marine parameters only.
    private func fetchMyDataMarineValues(for city: City) async -> [String: Double]? {
        guard let settings = Self.loadPersistedSettings() else {
            return nil
        }
        
        // Get enabled marine parameters
        let marineParams = settings.myDataFields
            .filter { $0.isEnabled && $0.parameter.apiEndpoint == .marine }
            .map { $0.parameter.apiKey }
        
        guard !marineParams.isEmpty else { return nil }
        
        // Build marine API request with current parameters
        let params = [
            "latitude": String(city.latitude),
            "longitude": String(city.longitude),
            "current": marineParams.joined(separator: ","),
            "cell_selection": "sea"
        ]
        
        var components = URLComponents(string: marineURL)!
        components.queryItems = params.map { URLQueryItem(name: $0.key, value: $0.value) }
        
        guard let url = components.url else { return nil }
        
        do {
            let data = try await apiData(for: url)
            let decoder = JSONDecoder()
            let response = try decoder.decode(MarineResponse.self, from: data)
            return response.current?.myDataValues
        } catch {
            debugLog("❌ Failed to fetch marine My Data: \(error.localizedDescription)")
            return nil
        }
    }
    
    /// Fetches air quality current values for selected My Data parameters.
    /// Returns a dictionary of API key -> value for air quality parameters only.
    private func fetchMyDataAirQualityValues(for city: City) async -> [String: Double]? {
        guard let settings = Self.loadPersistedSettings() else {
            return nil
        }
        
        // Get enabled air quality parameters
        let airQualityParams = settings.myDataFields
            .filter { $0.isEnabled && $0.parameter.apiEndpoint == .airQuality }
            .map { $0.parameter.apiKey }
        
        guard !airQualityParams.isEmpty else { return nil }
        
        // Build air quality API request with current parameters
        let params = [
            "latitude": String(city.latitude),
            "longitude": String(city.longitude),
            "current": airQualityParams.joined(separator: ",")
        ]
        
        var components = URLComponents(string: airQualityURL)!
        components.queryItems = params.map { URLQueryItem(name: $0.key, value: $0.value) }
        
        guard let url = components.url else { return nil }
        
        do {
            let data = try await apiData(for: url)
            let decoder = JSONDecoder()
            let response = try decoder.decode(AirQualityResponse.self, from: data)
            return response.current?.myDataValues
        } catch {
            debugLog("❌ Failed to fetch air quality My Data: \(error.localizedDescription)")
            return nil
        }
    }
    
    // MARK: - City Management
    
    func addCity(_ city: City) {
        let alreadySaved = savedCities.contains {
            $0.id == city.id ||
            $0.displayName.lowercased() == city.displayName.lowercased()
        }
        guard !alreadySaved else { return }
        savedCities.append(city)
        saveCities()
        Task {
            await fetchWeather(for: city)
        }
    }
    
    func removeCity(_ city: City) {
        savedCities.removeAll { $0.id == city.id }
        // Remove all cached weather data for this city (all date offsets)
        weatherCache = weatherCache.filter { $0.key.cityId != city.id }
        cacheTimestamps = cacheTimestamps.filter { $0.key.cityId != city.id }
        // Also drop marine cache entries for this city so they don't linger (L4)
        marineCache = marineCache.filter { $0.key.cityId != city.id }
        marineCacheTimestamps = marineCacheTimestamps.filter { $0.key.cityId != city.id }
        alertsCache.removeValue(forKey: city.id)
        saveCities()
    }
    
    func moveCity(from source: IndexSet, to destination: Int) {
        savedCities.move(fromOffsets: source, toOffset: destination)
        saveCities()
    }
    
    /// Flush all in-memory weather cache entries so the next fetch is a live network call.
    func clearWeatherCache() {
        weatherCache = [:]
        cacheTimestamps = [:]
        marineCache = [:]
        marineCacheTimestamps = [:]
        alertsCache = [:]
    }
    
    // MARK: - Weather Fetching
    
    // Check if cached data is still valid
    private func isCacheValid(timestamp: Date?) -> Bool {
        guard let timestamp = timestamp else { return false }
        return Date().timeIntervalSince(timestamp) < currentWeatherCacheDuration
    }
    
    /// Returns true when a cache entry is fresh enough to skip a new fetch, using the
    /// offset-aware policy: current (offset=0) is cached for 10 minutes, future offsets
    /// for 1 hour. Takes the timestamp explicitly so it works for both the weather and
    /// marine timestamp dictionaries — see CR review HI-6.
    private func isCacheValid(timestamp: Date?, dateOffset: Int) -> Bool {
        guard let timestamp = timestamp else { return false }
        let duration = dateOffset == 0 ? currentWeatherCacheDuration : forecastWeatherCacheDuration
        return Date().timeIntervalSince(timestamp) < duration
    }
    
    // MARK: - LRU Cache Eviction
    
    /// Evicts the oldest entries from weatherCache and marineCache when they exceed
    /// maxWeatherCacheEntries, keeping the most recently fetched data in memory.
    private func trimWeatherCacheIfNeeded() {
        guard weatherCache.count > maxWeatherCacheEntries else { return }
        let evict = cacheTimestamps
            .sorted { $0.value < $1.value }
            .prefix(weatherCache.count - maxWeatherCacheEntries)
            .map { $0.key }
        for key in evict {
            weatherCache.removeValue(forKey: key)
            marineCache.removeValue(forKey: key)
            cacheTimestamps.removeValue(forKey: key)
            marineCacheTimestamps.removeValue(forKey: key)
        }
    }

    /// Evicts the oldest marine entries independently of weatherCache. Marine data is
    /// fetched on its own (sailing/coastal cities) and would otherwise grow unbounded
    /// because trimWeatherCacheIfNeeded only fires on weatherCache growth — H2.
    private func trimMarineCacheIfNeeded() {
        guard marineCache.count > maxWeatherCacheEntries else { return }
        let evict = marineCacheTimestamps
            .sorted { $0.value < $1.value }
            .prefix(marineCache.count - maxWeatherCacheEntries)
            .map { $0.key }
        for key in evict {
            marineCache.removeValue(forKey: key)
            marineCacheTimestamps.removeValue(forKey: key)
        }
    }

    private func trimBrowseCacheIfNeeded() {
        guard browseWeatherCache.count > maxBrowseCacheEntries else { return }
        let evict = browseCacheTimestamps
            .sorted { $0.value < $1.value }
            .prefix(browseWeatherCache.count - maxBrowseCacheEntries)
            .map { $0.key }
        for key in evict {
            browseWeatherCache.removeValue(forKey: key)
            browseCacheTimestamps.removeValue(forKey: key)
        }
    }

    private func trimBrowseFullCacheIfNeeded() {
        guard browseWeatherFullCache.count > maxBrowseCacheEntries else { return }
        let evict = browseFullCacheTimestamps
            .sorted { $0.value < $1.value }
            .prefix(browseWeatherFullCache.count - maxBrowseCacheEntries)
            .map { $0.key }
        for key in evict {
            browseWeatherFullCache.removeValue(forKey: key)
            browseFullCacheTimestamps.removeValue(forKey: key)
        }
    }
    
    // Fetch light weather data (no hourly, 3 days) for list views
    func fetchWeather(for city: City) async {
        // Light fetch for list display — detail view will request full data on open
        await fetchWeatherForDate(for: city, dateOffset: 0, includeHourly: false)
    }

    /// Clears any prior failure marker for this city/date and re-attempts a full fetch.
    /// Once a full fetch fails, `failedCacheKeys` guards the list-row `.task` from
    /// re-fetching (so it doesn't loop on a persistent error), which leaves a city stuck
    /// showing truncated light data. The detail view's "Try Again" button calls this to
    /// escape that state.
    func retryFetch(for city: City, dateOffset: Int) async {
        let cacheKey = WeatherCacheKey(cityId: city.id, dateOffset: dateOffset)
        await MainActor.run { self.failedCacheKeys.remove(cacheKey) }
        await fetchWeatherForDate(for: city, dateOffset: dateOffset, includeHourly: true)
    }

    /// Change in daylight duration (in seconds) for the given day versus the day before it —
    /// positive means more daylight than the previous day, negative means less. Powers the
    /// "N minutes more/less than yesterday" note under the daylight total.
    ///
    /// First reuses per-day data already cached by day navigation ("look ahead") — each
    /// visited day is fetched with `daylight_duration`, so once the previous day has been
    /// viewed this costs nothing. Only when the previous day isn't cached (e.g. a cold
    /// today-view, which never pre-fetches yesterday) does it fall back to a tiny dedicated
    /// request — daily=daylight_duration only, no hourly — that doesn't bloat the main
    /// payload. Returns nil on any error.
    func fetchDaylightChangeVsPreviousDay(for city: City, dateOffset: Int) async -> Double? {
        // Fast path: both days are already in the weather cache from day navigation.
        let currentKey = WeatherCacheKey(cityId: city.id, dateOffset: dateOffset)
        let previousKey = WeatherCacheKey(cityId: city.id, dateOffset: dateOffset - 1)
        if let current = weatherCache[currentKey]?.daily?.daylightDuration?.value(at: 0),
           let previous = weatherCache[previousKey]?.daily?.daylightDuration?.value(at: 0) {
            return current - previous
        }

        // With past_days=P and forecast_days=F, the daily array covers dateOffsets -P…(F-1),
        // so a given dateOffset lives at index (dateOffset + P). Size the window to include
        // both the target day and the day before it.
        let previousOffset = dateOffset - 1
        let pastDays = max(0, -previousOffset)
        let forecastDays = max(1, dateOffset + 1)

        var components = URLComponents(string: baseURL)!
        components.queryItems = [
            URLQueryItem(name: "latitude", value: String(city.latitude)),
            URLQueryItem(name: "longitude", value: String(city.longitude)),
            URLQueryItem(name: "daily", value: "daylight_duration"),
            URLQueryItem(name: "past_days", value: String(pastDays)),
            URLQueryItem(name: "forecast_days", value: String(forecastDays)),
            URLQueryItem(name: "timezone", value: "auto")
        ]
        guard let url = components.url else { return nil }

        do {
            let data = try await apiData(for: url)
            // Decode into a minimal struct, NOT the full WeatherResponse: DailyWeather has
            // required fields (e.g. temperature_2m_max) that this daylight-only request omits,
            // which would make a full decode throw keyNotFound and silently drop the note.
            let response = try JSONDecoder().decode(DaylightChangeResponse.self, from: data)
            guard let durations = response.daily?.daylightDuration else { return nil }
            let targetIndex = dateOffset + pastDays
            guard let target = durations.value(at: targetIndex),
                  let previous = durations.value(at: targetIndex - 1) else { return nil }
            return target - previous
        } catch {
            debugLog("❌ Failed to fetch daylight change: \(error.localizedDescription)")
            return nil
        }
    }

    /// Minimal decodable for the daylight-only request in `fetchDaylightChangeVsPreviousDay`,
    /// so it doesn't require the many non-optional fields of the full `WeatherResponse.DailyWeather`.
    private struct DaylightChangeResponse: Decodable {
        struct Daily: Decodable {
            let daylightDuration: [Double?]?
            enum CodingKeys: String, CodingKey { case daylightDuration = "daylight_duration" }
        }
        let daily: Daily?
    }
    
    // Fetch weather data for a specific date offset.
    // includeHourly: false → skip hourly, forecast_days=3 (fast; used by list/background refresh)
    // includeHourly: true  → full hourly + 16-day forecast on paid key, 7-day on free tier
    func fetchWeatherForDate(for city: City, dateOffset: Int, includeHourly: Bool = true) async {
        let cacheKey = WeatherCacheKey(cityId: city.id, dateOffset: dateOffset)
        
        // Check in-memory cache
        if isCacheValid(timestamp: cacheTimestamps[cacheKey], dateOffset: dateOffset) {
            if !includeHourly {
                // Light fetch: any valid cache entry is acceptable
                return
            }
            // Full fetch: only reuse cache if it already has hourly data
            if let cached = weatherCache[cacheKey], cached.hourly != nil {
                return
            }
            // Cached data has no hourly — fall through to re-fetch with full params
        }
        
        // Calculate the target date
        let calendar = Calendar.current
        guard let targetDate = calendar.date(byAdding: .day, value: dateOffset, to: Date()) else {
            await MainActor.run {
                self.errorMessage = "Invalid date calculation"
            }
            return
        }
        
        // For recent past dates (-92 to -1): use the forecast API with past_days — no data lag,
        // full hourly data available. For older dates (< -92): fall back to the archive API.
        if dateOffset < 0 {
            if dateOffset >= -92 {
                await fetchPastWeatherForCity(city: city, dateOffset: dateOffset, cacheKey: cacheKey)
            } else {
                await fetchHistoricalWeatherForCity(city: city, targetDate: targetDate, cacheKey: cacheKey)
            }
            return
        }
        
        // For today and future dates, use forecast API
        // Build current parameters including any My Data selections
        let baseCurrentParams = "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,visibility,wind_gusts_10m,uv_index,dew_point_2m"
        let currentParams = Self.appendMyDataParameters(to: baseCurrentParams)
        
        // Light fetch (list/background): minimal params to stay well within free-tier limits.
        // Full fetch (detail view): includes hourly for charts and 7-day forecast.
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "latitude", value: String(city.latitude)),
            URLQueryItem(name: "longitude", value: String(city.longitude)),
            URLQueryItem(name: "current", value: currentParams),
            URLQueryItem(name: "daily", value: includeHourly
                ? "temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,sunrise,sunset,weather_code,precipitation_sum,rain_sum,snowfall_sum,precipitation_probability_max,uv_index_max,daylight_duration,sunshine_duration,wind_speed_10m_max,wind_direction_10m_dominant"
                : "temperature_2m_max,temperature_2m_min,sunrise,sunset,weather_code,precipitation_sum"),
            URLQueryItem(name: "forecast_days", value: includeHourly ? "16" : "3"),
            URLQueryItem(name: "timezone", value: "auto")
        ]
        if includeHourly {
            queryItems.append(URLQueryItem(name: "hourly", value: "temperature_2m,weather_code,precipitation,precipitation_probability,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,uv_index,dew_point_2m,snowfall,cloud_cover"))
        }
        
        var components = URLComponents(string: baseURL)!
        components.queryItems = queryItems
        
        guard let url = components.url else {
            await MainActor.run {
                self.errorMessage = "Invalid URL"
            }
            return
        }
        
        do {
            // The full fetch (hourly + 16 daily variables) is a large payload; give it
            // 30s on slow cellular so it doesn't time out and fall back to light data.
            // The light fetch (3 days, no hourly) is small — keep the tighter 15s.
            let data = try await apiData(for: url, timeout: includeHourly ? 30 : 15)

            let decoder = JSONDecoder()
            let response = try decoder.decode(WeatherResponse.self, from: data)

            // For dateOffset = 0 (today), use the current weather directly
            // For dateOffset > 0 (future), extract that day's data from daily/hourly arrays
            let weatherData: WeatherData
            if dateOffset == 0 {
                weatherData = WeatherData(current: response.current, daily: response.daily, hourly: response.hourly, utcOffsetSeconds: response.utcOffsetSeconds)
            } else {
                // Extract the specific day's data from the arrays
                guard let daily = response.daily,
                      dateOffset < daily.temperature2mMax.count else {
                    await MainActor.run {
                        self.errorMessage = "Future date out of range"
                    }
                    return
                }
                
                // Build synthetic "current" weather from that day's max/min temps and weather code.
                // All array access is bounds-safe (.value(at:)) so a partial API response can't trap — CR-3.
                let avgTemp = ((daily.temperature2mMax.value(at: dateOffset) ?? 0) + (daily.temperature2mMin.value(at: dateOffset) ?? 0)) / 2
                let avgApparentTemp: Double? = {
                    guard let maxVal = daily.apparentTemperatureMax?.value(at: dateOffset),
                          let minVal = daily.apparentTemperatureMin?.value(at: dateOffset) else { return nil }
                    return (maxVal + minVal) / 2
                }()
                let current = WeatherData.CurrentWeather(
                    temperature2m: avgTemp,
                    relativeHumidity2m: nil,
                    apparentTemperature: avgApparentTemp,
                    isDay: 1,
                    precipitation: daily.precipitationSum?.value(at: dateOffset) ?? 0,
                    rain: daily.rainSum?.value(at: dateOffset) ?? 0,
                    showers: nil,
                    snowfall: daily.snowfallSum?.value(at: dateOffset) ?? 0,
                    weatherCode: daily.weatherCode?.value(at: dateOffset) ?? 0,
                    cloudCover: 0,
                    pressureMsl: nil,
                    windSpeed10m: daily.windSpeed10mMax?.value(at: dateOffset) ?? 0,
                    windDirection10m: nil,
                    visibility: nil,
                    windGusts10m: nil,
                    uvIndex: daily.uvIndexMax?.value(at: dateOffset) ?? nil,
                    dewpoint2m: nil
                )

                // Extract just this day's data from daily arrays (single-element arrays)
                let singleDayDaily = WeatherData.DailyWeather(
                    temperature2mMax: [daily.temperature2mMax.value(at: dateOffset)].compactMap { $0 },
                    temperature2mMin: [daily.temperature2mMin.value(at: dateOffset)].compactMap { $0 },
                    sunrise: daily.sunrise.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    sunset: daily.sunset.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    weatherCode: daily.weatherCode.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    precipitationSum: daily.precipitationSum.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    rainSum: daily.rainSum.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    snowfallSum: daily.snowfallSum.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    precipitationProbabilityMax: daily.precipitationProbabilityMax.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    uvIndexMax: daily.uvIndexMax.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    daylightDuration: daily.daylightDuration.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    sunshineDuration: daily.sunshineDuration.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    windSpeed10mMax: daily.windSpeed10mMax.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    windDirectionDominant: daily.windDirectionDominant.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    apparentTemperatureMax: daily.apparentTemperatureMax.map { [$0.value(at: dateOffset)].compactMap { $0 } },
                    apparentTemperatureMin: daily.apparentTemperatureMin.map { [$0.value(at: dateOffset)].compactMap { $0 } }
                )
                
                // Extract hourly data for that specific day (24 hours starting at midnight of target date)
                // Each day has 24 hourly entries, so day N starts at index N*24
                var hourlyForDay: WeatherData.HourlyWeather? = nil
                if let hourly = response.hourly,
                   let hourlyTemp = hourly.temperature2m,
                   let hourlyTime = hourly.time {
                    let hourlyStartIdx = dateOffset * 24
                    let hourlyEndIdx = min(hourlyStartIdx + 24, hourlyTemp.count)
                    if hourlyStartIdx < hourlyTemp.count {
                        hourlyForDay = WeatherData.HourlyWeather(
                            time: Array(hourlyTime[hourlyStartIdx..<hourlyEndIdx]),
                            temperature2m: Array(hourlyTemp[hourlyStartIdx..<hourlyEndIdx]),
                            weatherCode: hourly.weatherCode.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                            precipitation: hourly.precipitation.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                            relativeHumidity2m: hourly.relativeHumidity2m.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                            windSpeed10m: hourly.windSpeed10m.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                            cloudCover: hourly.cloudCover.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                            precipitationProbability: hourly.precipitationProbability.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                            uvIndex: hourly.uvIndex.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                            windGusts10m: hourly.windGusts10m.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                            dewPoint2m: hourly.dewPoint2m.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                            snowfall: hourly.snowfall.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) }
                        )
                    }
                }
                
                weatherData = WeatherData(current: current, daily: singleDayDaily, hourly: hourlyForDay, utcOffsetSeconds: response.utcOffsetSeconds)
            }
            
            // MARK: - Merge Marine & Air Quality My Data values (dateOffset = 0 only)
            // For current conditions (today), fetch marine and air quality parameters if selected
            var finalWeatherData = weatherData
            if dateOffset == 0 {
                var mergedMyDataValues = weatherData.current.myDataValues ?? [:]
                
                // Fetch marine My Data values if any marine parameters are selected
                if let marineValues = await fetchMyDataMarineValues(for: city) {
                    mergedMyDataValues.merge(marineValues) { (_, new) in new }
                }
                
                // Fetch air quality My Data values if any air quality parameters are selected
                if let airQualityValues = await fetchMyDataAirQualityValues(for: city) {
                    mergedMyDataValues.merge(airQualityValues) { (_, new) in new }
                }
                
                // Update weatherData with merged My Data values if any were added
                if !mergedMyDataValues.isEmpty {
                    let updatedCurrent = WeatherData.CurrentWeather(
                        temperature2m: weatherData.current.temperature2m,
                        relativeHumidity2m: weatherData.current.relativeHumidity2m,
                        apparentTemperature: weatherData.current.apparentTemperature,
                        isDay: weatherData.current.isDay,
                        precipitation: weatherData.current.precipitation,
                        rain: weatherData.current.rain,
                        showers: weatherData.current.showers,
                        snowfall: weatherData.current.snowfall,
                        weatherCode: weatherData.current.weatherCode,
                        cloudCover: weatherData.current.cloudCover,
                        pressureMsl: weatherData.current.pressureMsl,
                        windSpeed10m: weatherData.current.windSpeed10m,
                        windDirection10m: weatherData.current.windDirection10m,
                        visibility: weatherData.current.visibility,
                        windGusts10m: weatherData.current.windGusts10m,
                        uvIndex: weatherData.current.uvIndex,
                        dewpoint2m: weatherData.current.dewpoint2m,
                        myDataValues: mergedMyDataValues
                    )
                    finalWeatherData = WeatherData(
                        current: updatedCurrent,
                        daily: weatherData.daily,
                        hourly: weatherData.hourly,
                        utcOffsetSeconds: weatherData.utcOffsetSeconds
                    )
                }
            }
            
            // Optionally overlay WeatherKit data (current condition and/or snow totals) over
            // the Open-Meteo values. One WeatherKit call serves both, so enabling the condition
            // overlay adds no extra request when snow is already on. Each overlay is gated by its
            // own feature flag inside the function; it returns the data unchanged on any error.
            #if canImport(WeatherKit)
            if #available(iOS 16.0, *) {
                finalWeatherData = await applyWeatherKitOverlay(for: city, dateOffset: dateOffset, into: finalWeatherData)
            }
            #endif
            
            await MainActor.run {
                self.weatherCache[cacheKey] = finalWeatherData
                self.cacheTimestamps[cacheKey] = Date()
                // failedCacheKeys tracks FULL-fetch state only (it drives the detail view's
                // "couldn't load the full forecast" banner). A light fetch has no hourly/16-day
                // data, so it must neither set nor clear the marker — otherwise a light success
                // would hide a real full-fetch failure, and a light failure would show the
                // banner over perfectly good cached full data.
                if includeHourly { self.failedCacheKeys.remove(cacheKey) }
                self.trimWeatherCacheIfNeeded()
            }
        } catch {
            debugLog("❌ fetchWeatherForDate failed (dateOffset=\(dateOffset), includeHourly=\(includeHourly)): \(error.localizedDescription)")
            await MainActor.run {
                self.errorMessage = "Failed to fetch weather: \(error.localizedDescription)"
                if includeHourly { self.failedCacheKeys.insert(cacheKey) }
            }
        }
    }
    
    // Helper: Fetch a past day (dateOffset in -92..-1) using the forecast API with past_days.
    // Returns full hourly data with no data lag, unlike the archive API.
    private func fetchPastWeatherForCity(city: City, dateOffset: Int, cacheKey: WeatherCacheKey) async {
        let pastDays = abs(dateOffset)

        let baseCurrentParams = "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,visibility,wind_gusts_10m,uv_index,dew_point_2m"
        let currentParams = Self.appendMyDataParameters(to: baseCurrentParams)

        var components = URLComponents(string: baseURL)!
        components.queryItems = [
            URLQueryItem(name: "latitude", value: String(city.latitude)),
            URLQueryItem(name: "longitude", value: String(city.longitude)),
            URLQueryItem(name: "current", value: currentParams),
            URLQueryItem(name: "daily", value: "temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,sunrise,sunset,weather_code,precipitation_sum,rain_sum,snowfall_sum,precipitation_probability_max,uv_index_max,daylight_duration,sunshine_duration,wind_speed_10m_max,wind_direction_10m_dominant"),
            URLQueryItem(name: "hourly", value: "temperature_2m,weather_code,precipitation,precipitation_probability,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,uv_index,dew_point_2m,snowfall,cloud_cover"),
            URLQueryItem(name: "past_days", value: String(pastDays)),
            URLQueryItem(name: "forecast_days", value: "1"),
            URLQueryItem(name: "timezone", value: "auto")
        ]

        guard let url = components.url else {
            await MainActor.run { self.errorMessage = "Invalid URL" }
            return
        }

        do {
            let data = try await apiData(for: url)
            let decoder = JSONDecoder()
            let response = try decoder.decode(WeatherResponse.self, from: data)

            guard let daily = response.daily,
                  !daily.temperature2mMax.isEmpty else {
                await MainActor.run { self.errorMessage = "No data available for requested date" }
                return
            }

            // With past_days=N and forecast_days=1, the response contains N+1 days.
            // The target past day is always at index 0 (the oldest entry).
            let targetIndex = 0

            // Bounds-safe access (.value(at:)) so a partial API response can't trap — CR-3.
            let avgTemp = ((daily.temperature2mMax.value(at: targetIndex) ?? 0) + (daily.temperature2mMin.value(at: targetIndex) ?? 0)) / 2
            let avgApparentTemp: Double? = {
                guard let maxVal = daily.apparentTemperatureMax?.value(at: targetIndex),
                      let minVal = daily.apparentTemperatureMin?.value(at: targetIndex) else { return nil }
                return (maxVal + minVal) / 2
            }()
            let current = WeatherData.CurrentWeather(
                temperature2m: avgTemp,
                relativeHumidity2m: nil,
                apparentTemperature: avgApparentTemp,
                isDay: 1,
                precipitation: daily.precipitationSum?.value(at: targetIndex) ?? 0,
                rain: daily.rainSum?.value(at: targetIndex) ?? 0,
                showers: nil,
                snowfall: daily.snowfallSum?.value(at: targetIndex) ?? 0,
                weatherCode: daily.weatherCode?.value(at: targetIndex) ?? 0,
                cloudCover: 0,
                pressureMsl: nil,
                windSpeed10m: daily.windSpeed10mMax?.value(at: targetIndex) ?? 0,
                windDirection10m: nil,
                visibility: nil,
                windGusts10m: nil,
                uvIndex: daily.uvIndexMax?.value(at: targetIndex) ?? nil,
                dewpoint2m: nil
            )

            let singleDayDaily = WeatherData.DailyWeather(
                temperature2mMax: [daily.temperature2mMax.value(at: targetIndex)].compactMap { $0 },
                temperature2mMin: [daily.temperature2mMin.value(at: targetIndex)].compactMap { $0 },
                sunrise: daily.sunrise.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                sunset: daily.sunset.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                weatherCode: daily.weatherCode.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                precipitationSum: daily.precipitationSum.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                rainSum: daily.rainSum.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                snowfallSum: daily.snowfallSum.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                precipitationProbabilityMax: daily.precipitationProbabilityMax.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                uvIndexMax: daily.uvIndexMax.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                daylightDuration: daily.daylightDuration.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                sunshineDuration: daily.sunshineDuration.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                windSpeed10mMax: daily.windSpeed10mMax.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                windDirectionDominant: daily.windDirectionDominant.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                apparentTemperatureMax: daily.apparentTemperatureMax.map { [$0.value(at: targetIndex)].compactMap { $0 } },
                apparentTemperatureMin: daily.apparentTemperatureMin.map { [$0.value(at: targetIndex)].compactMap { $0 } }
            )

            // The target past day's hourly data is always the first 24 entries in the response.
            var hourlyForDay: WeatherData.HourlyWeather? = nil
            if let hourly = response.hourly,
               let hourlyTemp = hourly.temperature2m,
               let hourlyTime = hourly.time,
               !hourlyTemp.isEmpty {
                let endIdx = min(24, hourlyTemp.count)
                hourlyForDay = WeatherData.HourlyWeather(
                    time: Array(hourlyTime[0..<endIdx]),
                    temperature2m: Array(hourlyTemp[0..<endIdx]),
                    weatherCode: hourly.weatherCode.map { Array($0[0..<min(endIdx, $0.count)]) },
                    precipitation: hourly.precipitation.map { Array($0[0..<min(endIdx, $0.count)]) },
                    relativeHumidity2m: hourly.relativeHumidity2m.map { Array($0[0..<min(endIdx, $0.count)]) },
                    windSpeed10m: hourly.windSpeed10m.map { Array($0[0..<min(endIdx, $0.count)]) },
                    cloudCover: hourly.cloudCover.map { Array($0[0..<min(endIdx, $0.count)]) },
                    precipitationProbability: hourly.precipitationProbability.map { Array($0[0..<min(endIdx, $0.count)]) },
                    uvIndex: hourly.uvIndex.map { Array($0[0..<min(endIdx, $0.count)]) },
                    windGusts10m: hourly.windGusts10m.map { Array($0[0..<min(endIdx, $0.count)]) },
                    dewPoint2m: hourly.dewPoint2m.map { Array($0[0..<min(endIdx, $0.count)]) },
                    snowfall: hourly.snowfall.map { Array($0[0..<min(endIdx, $0.count)]) }
                )
            }

            let weatherData = WeatherData(
                current: current,
                daily: singleDayDaily,
                hourly: hourlyForDay,
                utcOffsetSeconds: response.utcOffsetSeconds
            )

            await MainActor.run {
                self.weatherCache[cacheKey] = weatherData
                self.cacheTimestamps[cacheKey] = Date()
                self.failedCacheKeys.remove(cacheKey)
                self.trimWeatherCacheIfNeeded()
            }
        } catch {
            debugLog("❌ fetchPastWeatherForCity failed (dateOffset=\(dateOffset)): \(error.localizedDescription)")
            // Fall back to archive API
            guard let targetDate = Calendar.current.date(byAdding: .day, value: dateOffset, to: Date()) else { return }
            await fetchHistoricalWeatherForCity(city: city, targetDate: targetDate, cacheKey: cacheKey)
        }
    }

    // Helper: Fetch historical weather for a city on a specific past date
    private func fetchHistoricalWeatherForCity(city: City, targetDate: Date, cacheKey: WeatherCacheKey) async {
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let dateString = dateFormatter.string(from: targetDate)
        
        do {
            // Fetch single day from archive API
            let response = try await fetchHistoricalWeather(for: city, startDate: dateString, endDate: dateString)
            
            // Convert historical data to WeatherData format
            let daily = response.daily
            guard !daily.time.isEmpty,
                  let firstIndex = daily.time.indices.first else {
                await MainActor.run {
                    self.errorMessage = "No historical data available for \(dateString)"
                }
                return
            }
            
            // Create minimal current weather from daily data
            let avgTemp = ((daily.temperature2mMax[firstIndex] ?? 0) + (daily.temperature2mMin[firstIndex] ?? 0)) / 2
            let avgApparentTemp = ((daily.apparentTemperatureMax?[firstIndex] ?? 0) + (daily.apparentTemperatureMin?[firstIndex] ?? 0)) / 2
            
            let current = WeatherData.CurrentWeather(
                temperature2m: avgTemp,
                relativeHumidity2m: nil,
                apparentTemperature: avgApparentTemp,
                isDay: 1,
                precipitation: daily.precipitationSum[firstIndex] ?? 0,
                rain: daily.rainSum?[firstIndex] ?? 0,
                showers: nil,
                snowfall: daily.snowfallSum?[firstIndex] ?? 0,
                weatherCode: daily.weatherCode[firstIndex] ?? 0,
                cloudCover: 0,
                pressureMsl: nil,
                windSpeed10m: daily.windSpeed10mMax?[firstIndex] ?? 0,
                windDirection10m: nil,
                visibility: nil,
                windGusts10m: nil,
                uvIndex: nil,
                dewpoint2m: nil
            )
            
            // Create daily weather data
            let dailyWeather = WeatherData.DailyWeather(
                temperature2mMax: daily.temperature2mMax,
                temperature2mMin: daily.temperature2mMin,
                sunrise: daily.sunrise,
                sunset: daily.sunset,
                weatherCode: daily.weatherCode,
                precipitationSum: daily.precipitationSum,
                rainSum: daily.rainSum,
                snowfallSum: daily.snowfallSum,
                precipitationProbabilityMax: nil,
                uvIndexMax: nil,
                daylightDuration: nil,
                sunshineDuration: nil,
                windSpeed10mMax: daily.windSpeed10mMax,
                windDirectionDominant: nil,
                apparentTemperatureMax: nil,
                apparentTemperatureMin: nil
            )
            
            let weatherData = WeatherData(current: current, daily: dailyWeather, hourly: nil, utcOffsetSeconds: nil)
            
            await MainActor.run {
                self.weatherCache[cacheKey] = weatherData
                self.cacheTimestamps[cacheKey] = Date()
                self.trimWeatherCacheIfNeeded()
            }
        } catch {
            await MainActor.run {
                self.errorMessage = "Failed to fetch historical weather: \(error.localizedDescription)"
            }
        }
    }
    
    // Fetch basic weather data (1 day, minimal fields) for list displays - OPTIMIZED
    func fetchWeatherBasic(latitude: Double, longitude: Double) async throws -> WeatherData {
        let cacheKey = "\(latitude),\(longitude)"
        
        // Check cache first
        if let cached = browseWeatherCache[cacheKey],
           isCacheValid(timestamp: browseCacheTimestamps[cacheKey]) {
            return cached
        }
        
        // Minimal params matching Windows "basic" mode, plus wind/pressure for Weather Around Me.
        // No hourly block — browse/around-me views show only current conditions; the 24-value
        // cloud_cover hourly array that was previously requested is never displayed.
        let params = [
            "latitude": String(latitude),
            "longitude": String(longitude),
            "current": "temperature_2m,weather_code,cloud_cover,is_day,uv_index,wind_speed_10m,wind_direction_10m,pressure_msl",
            "daily": "temperature_2m_max,temperature_2m_min",
            "forecast_days": "1",
            "timezone": "auto"
        ]
        
        var components = URLComponents(string: baseURL)!
        components.queryItems = params.map { URLQueryItem(name: $0.key, value: $0.value) }
        
        guard let url = components.url else {
            throw URLError(.badURL)
        }
        
        let data = try await apiData(for: url)
        let response = try JSONDecoder().decode(WeatherResponse.self, from: data)
        var weatherData = WeatherData(current: response.current, daily: response.daily, hourly: response.hourly, utcOffsetSeconds: response.utcOffsetSeconds)

        // Overlay WeatherKit's observation-informed current condition (browse/around-me rows).
        #if canImport(WeatherKit)
        if #available(iOS 16.0, *) {
            if let wmo = await weatherKitCurrentWMOCode(latitude: latitude, longitude: longitude) {
                weatherData = weatherData.withCurrentWeatherCode(wmo)
            }
        }
        #endif

        // Cache the result
        let cachedData = weatherData
        await MainActor.run {
            browseWeatherCache[cacheKey] = cachedData
            browseCacheTimestamps[cacheKey] = Date()
            trimBrowseCacheIfNeeded()
        }

        return weatherData
    }

    // Fetch full weather data (16 days) for detail views
    func fetchWeatherFull(latitude: Double, longitude: Double) async throws -> WeatherData {
        let cacheKey = "\(latitude),\(longitude)"

        if let cached = browseWeatherFullCache[cacheKey],
           isCacheValid(timestamp: browseFullCacheTimestamps[cacheKey]) {
            return cached
        }

        let params = [
            "latitude": String(latitude),
            "longitude": String(longitude),
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,visibility,wind_gusts_10m,uv_index,dew_point_2m",
            "hourly": "temperature_2m,weather_code,precipitation,precipitation_probability,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,uv_index,dew_point_2m,snowfall,cloud_cover",
            "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset,weather_code,precipitation_sum,rain_sum,snowfall_sum,precipitation_probability_max,uv_index_max,daylight_duration,sunshine_duration,wind_speed_10m_max,wind_direction_10m_dominant",
            "forecast_days": "16",
            "timezone": "auto"
        ]

        var components = URLComponents(string: baseURL)!
        components.queryItems = params.map { URLQueryItem(name: $0.key, value: $0.value) }

        guard let url = components.url else {
            throw URLError(.badURL)
        }

        let data = try await apiData(for: url)
        let response = try JSONDecoder().decode(WeatherResponse.self, from: data)
        let weatherData = WeatherData(current: response.current, daily: response.daily, hourly: response.hourly, utcOffsetSeconds: response.utcOffsetSeconds)

        await MainActor.run {
            browseWeatherFullCache[cacheKey] = weatherData
            browseFullCacheTimestamps[cacheKey] = Date()
            trimBrowseFullCacheIfNeeded()
        }

        return weatherData
    }
    
    // Batch load weather for multiple locations (parallel with concurrency limit)
    func batchFetchWeatherBasic(for locations: [(latitude: Double, longitude: Double)]) async -> [String: WeatherData] {
        var results: [String: WeatherData] = [:]
        
        await withTaskGroup(of: (String, WeatherData?).self) { group in
            var activeTaskCount = 0
            var locationIndex = 0
            
            // Process locations with concurrency limit
            while locationIndex < locations.count || activeTaskCount > 0 {
                // Add tasks up to the limit
                while activeTaskCount < maxConcurrentRequests && locationIndex < locations.count {
                    let location = locations[locationIndex]
                    let key = "\(location.latitude),\(location.longitude)"
                    locationIndex += 1
                    activeTaskCount += 1
                    
                    group.addTask {
                        do {
                            let weather = try await self.fetchWeatherBasic(
                                latitude: location.latitude,
                                longitude: location.longitude
                            )
                            return (key, weather)
                        } catch {
                            debugLog("❌ Batch fetch error for \(key): \(error)")
                            return (key, nil)
                        }
                    }
                }
                
                // Wait for one task to complete
                if let result = await group.next() {
                    if let weatherData = result.1 {
                        results[result.0] = weatherData
                    }
                    activeTaskCount -= 1
                }
            }
        }
        
        return results
    }
    
    func refreshAllWeather() async {
        await MainActor.run {
            isLoading = true
            alertsRefreshID += 1
        }
        
        // Fetch cities concurrently, capped by maxConcurrentRequests.
        // On the paid tier (dedicated servers) this is 5; on free tier it stays 1.
        await withTaskGroup(of: Void.self) { group in
            var inFlight = 0
            var iterator = savedCities.makeIterator()
            
            while inFlight < maxConcurrentRequests, let city = iterator.next() {
                let c = city
                group.addTask { await self.fetchWeatherForDate(for: c, dateOffset: 0, includeHourly: false) }
                inFlight += 1
            }
            
            while await group.next() != nil {
                inFlight -= 1
                if let city = iterator.next() {
                    let c = city
                    group.addTask { await self.fetchWeatherForDate(for: c, dateOffset: 0, includeHourly: false) }
                    inFlight += 1
                }
            }
        }
        
        await MainActor.run {
            isLoading = false
        }
    }
    
    // MARK: - Marine Weather
    
    // Fetch marine forecast data for a specific city and date offset
    func fetchMarineData(for city: City, dateOffset: Int = 0) async {
        let cacheKey = WeatherCacheKey(cityId: city.id, dateOffset: dateOffset)
        
        // Check in-memory cache
        if isCacheValid(timestamp: marineCacheTimestamps[cacheKey], dateOffset: dateOffset) {
            return
        }
        
        // Marine API params - request all available marine variables
        let params = [
            "latitude": String(city.latitude),
            "longitude": String(city.longitude),
            "hourly": "wave_height,wave_direction,wave_period,wave_peak_period,wind_wave_height,wind_wave_direction,wind_wave_period,swell_wave_height,swell_wave_direction,swell_wave_period,ocean_current_velocity,ocean_current_direction,sea_surface_temperature,sea_level_height_msl",
            "forecast_days": "7",
            "timezone": "auto",
            "cell_selection": "sea"  // Prefer sea grid cells for accurate marine data
        ]
        
        var components = URLComponents(string: marineURL)!
        components.queryItems = params.map { URLQueryItem(name: $0.key, value: $0.value) }
        
        guard let url = components.url else {
            await MainActor.run {
                self.errorMessage = "Invalid marine API URL"
            }
            return
        }
        
        do {
            let data = try await apiData(for: url)
            let decoder = JSONDecoder()
            let response = try decoder.decode(MarineResponse.self, from: data)
            
            // Extract marine data for the specific date offset
            var marineData: MarineData
            
            if dateOffset == 0 {
                // For today, use all data as-is
                marineData = MarineData(current: nil, hourly: response.hourly)
            } else if dateOffset > 0 {
                // For future dates, extract that day's hourly data (24 hours)
                guard let hourly = response.hourly,
                      let hourlyTime = hourly.time else {
                    await MainActor.run {
                        self.errorMessage = "No marine data available"
                    }
                    return
                }
                
                let hourlyStartIdx = dateOffset * 24
                let hourlyEndIdx = min(hourlyStartIdx + 24, hourlyTime.count)
                
                if hourlyStartIdx < hourlyTime.count {
                    let extractedHourly = MarineData.MarineHourly(
                        time: Array(hourlyTime[hourlyStartIdx..<hourlyEndIdx]),
                        waveHeight: hourly.waveHeight.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        waveDirection: hourly.waveDirection.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        wavePeriod: hourly.wavePeriod.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        wavePeakPeriod: hourly.wavePeakPeriod.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        windWaveHeight: hourly.windWaveHeight.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        windWaveDirection: hourly.windWaveDirection.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        windWavePeriod: hourly.windWavePeriod.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        swellWaveHeight: hourly.swellWaveHeight.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        swellWaveDirection: hourly.swellWaveDirection.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        swellWavePeriod: hourly.swellWavePeriod.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        oceanCurrentVelocity: hourly.oceanCurrentVelocity.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        oceanCurrentDirection: hourly.oceanCurrentDirection.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        seaSurfaceTemperature: hourly.seaSurfaceTemperature.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) },
                        seaLevelHeight: hourly.seaLevelHeight.map { Array($0[hourlyStartIdx..<hourlyEndIdx]) }
                    )
                    marineData = MarineData(current: nil, hourly: extractedHourly)
                } else {
                    await MainActor.run {
                        self.errorMessage = "Marine data not available for this date"
                    }
                    return
                }
            } else {
                // dateOffset < 0 - past dates not supported by marine API (no historical marine data)
                await MainActor.run {
                    self.errorMessage = "Historical marine data not available"
                }
                return
            }
            
            await MainActor.run {
                self.marineCache[cacheKey] = marineData
                self.marineCacheTimestamps[cacheKey] = Date()
                self.trimMarineCacheIfNeeded()
            }
        } catch {
            await MainActor.run {
                self.errorMessage = "Failed to fetch marine data: \(error.localizedDescription)"
            }
        }
    }
    
    // MARK: - Historical Weather
    
    // Fetch historical weather for a specific date range
    func fetchHistoricalWeather(for city: City, startDate: String, endDate: String,
                                fields: String = "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,sunrise,sunset,precipitation_sum,rain_sum,snowfall_sum,precipitation_hours,wind_speed_10m_max") async throws -> HistoricalWeatherResponse {
        let params = [
            "latitude": String(city.latitude),
            "longitude": String(city.longitude),
            "start_date": startDate,
            "end_date": endDate,
            "daily": fields,
            "timezone": "auto"
        ]
        
        var components = URLComponents(string: historicalURL)!
        components.queryItems = params.map { URLQueryItem(name: $0.key, value: $0.value) }
        
        guard let url = components.url else {
            throw URLError(.badURL)
        }
        
        debugLog("📊 Fetching historical weather from \(startDate) to \(endDate) for \(city.name)")
        
        // Historical archive API is always free tier — never send paid API key.
        var request = URLRequest(url: url, timeoutInterval: 30)
        request.setValue("FastWeather/1.5 (weatherfast.online)", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await URLSession.shared.data(for: request)
        
        // Surface HTTP-level errors (4xx/5xx) before attempting JSON decode.
        if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode != 200 {
            // Try to decode an Open-Meteo error body {"error":true,"reason":"..."}
            if let errorBody = try? JSONDecoder().decode(OpenMeteoErrorResponse.self, from: data),
               errorBody.error {
                throw NSError(domain: "OpenMeteoArchive", code: httpResponse.statusCode,
                              userInfo: [NSLocalizedDescriptionKey: errorBody.reason ?? "Unknown API error"])
            }
            throw URLError(.badServerResponse)
        }
        
        do {
            let weatherResponse = try JSONDecoder().decode(HistoricalWeatherResponse.self, from: data)
            return weatherResponse
        } catch {
            // Log raw response snippet to help diagnose field-name changes in the API.
            let preview = String(data: data.prefix(200), encoding: .utf8) ?? "<unreadable>"
            debugLog("❌ Failed to decode historical response for \(startDate): \(error)\nResponse preview: \(preview)")
            throw error
        }
    }
    
    // Fetch same day across multiple years (e.g., all January 19ths from 1940 to now)
    func fetchSameDayHistory(for city: City, monthDay: String, yearsBack: Int = 85, endYear: Int? = nil) async throws -> [HistoricalDay] {
        let calendar = Calendar.current
        let actualEndYear = endYear ?? calendar.component(.year, from: Date())
        let cacheKey = "\(monthDay)-\(actualEndYear)"
        
        // Check cache first - but only use it if it has enough years
        if let cached = HistoricalWeatherCache.shared.getCached(for: city, monthDay: cacheKey) {
            if cached.count >= yearsBack {
                debugLog("📊 Cache hit: \(cached.count) years for \(cacheKey)")
                // Return only the requested number of years (most recent ones)
                return Array(cached.prefix(yearsBack))
            } else {
                debugLog("⚠️ Cache has only \(cached.count) years but \(yearsBack) requested — fetching fresh data")
            }
        }
        
        // Parse month and day from monthDay string (format: "MM-DD")
        let parts = monthDay.split(separator: "-")
        guard parts.count == 2,
              let month = Int(parts[0]),
              let day = Int(parts[1]) else {
            throw URLError(.badURL)
        }
        
        // startYear to actualEndYear gives yearsBack+1 candidates.
        // actualEndYear itself may not yet be in the archive (~5-day lag), so if it
        // fails we still collect exactly yearsBack results from the older years.
        let startYear = actualEndYear - yearsBack
        
        // DateFormatter created once (not inside the loop) with explicit locale/timezone
        // to avoid mis-parsing on non-English devices or around DST transitions.
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        dateFormatter.locale = Locale(identifier: "en_US_POSIX")
        // No UTC override: parse in local timezone so stored dates display correctly
        // (midnight UTC would appear as prev-day evening in US timezones)
        
        var historicalDays: [HistoricalDay] = []
        var failCount = 0
        
        // Fetch one year at a time: each request retrieves only a single day of data
        // (~tiny JSON response). The old 10-year-range approach fetched ~3,650 rows per
        // chunk and regularly hit the 15-second timeout on slower cellular connections,
        // causing complete or partial data loss. Per-year requests are far more reliable;
        // a failure for one year skips only that year, not 10.
        // We run 5 years concurrently to keep total fetch time reasonable (max ~85 yrs).
        let years = Array(startYear...actualEndYear)
        let batchSize = 5
        
        for batchStart in stride(from: 0, to: years.count, by: batchSize) {
            let batchEnd = min(batchStart + batchSize, years.count)
            let batch = Array(years[batchStart..<batchEnd])
            
            let batchResults: [HistoricalDay] = await withTaskGroup(of: HistoricalDay?.self) { group in
                for year in batch {
                    group.addTask { [self] in
                        // Feb 29 falls back to Feb 28 in non-leap years, as the year jumps do
                        let isLeap = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0
                        let dayInYear = (month == 2 && day == 29 && !isLeap) ? 28 : day
                        let dateString = String(format: "%04d-%02d-%02d", year, month, dayInYear)
                        do {
                            let response = try await self.fetchHistoricalWeather(
                                for: city, startDate: dateString, endDate: dateString,
                                fields: "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum")
                            
                            guard !response.daily.time.isEmpty,
                                  let timeString = response.daily.time[0],
                                  let date = dateFormatter.date(from: timeString),
                                  let weatherCode = response.daily.weatherCode[0],
                                  let tempMax = response.daily.temperature2mMax[0],
                                  let tempMin = response.daily.temperature2mMin[0],
                                  let precipitationSum = response.daily.precipitationSum[0] else {
                                debugLog("⚠️ [\(year)] No data or nil field for \(dateString)")
                                return nil
                            }
                            
                            let resolvedYear = calendar.component(.year, from: date)
                            return HistoricalDay(
                                date: date,
                                year: resolvedYear,
                                weatherCode: weatherCode,
                                tempMax: tempMax,
                                tempMin: tempMin,
                                precipitationSum: precipitationSum
                            )
                        } catch {
                            debugLog("⚠️ [\(year)] Failed to fetch \(dateString): \(error.localizedDescription)")
                            return nil
                        }
                    }
                }
                
                var results: [HistoricalDay] = []
                for await result in group {
                    if let day = result {
                        results.append(day)
                    } else {
                        failCount += 1
                    }
                }
                return results
            }
            
            historicalDays.append(contentsOf: batchResults)
        }
        
        if failCount > 0 {
            debugLog("⚠️ \(failCount) year(s) failed to load for \(monthDay). Got \(historicalDays.count) of \(yearsBack) requested.")
        }
        
        // Sort by year descending (most recent first)
        historicalDays.sort { $0.year > $1.year }
        
        // Only cache if we received at least one year; avoids persisting transient network
        // failures as empty cache entries that suppress future retries.
        if !historicalDays.isEmpty {
            HistoricalWeatherCache.shared.cache(historicalDays, for: city, monthDay: cacheKey)
        }
        
        return historicalDays
    }
    
    // MARK: - WeatherKit Overlay (current condition + snow totals)

    /// Overlays WeatherKit data onto an Open-Meteo `WeatherData`:
    ///  - **Current condition** (today only, flag `weatherKitConditionsEnabled`): replaces the
    ///    Open-Meteo model `weather_code` with WeatherKit's observation/nowcast-informed
    ///    condition, translated to WMO. Unmappable conditions keep the Open-Meteo code.
    ///  - **Forecast conditions** (flag `weatherKitForecastConditionsEnabled`): the same WMO
    ///    translation applied per hour/day across WeatherKit's ~10-day horizon, fixing the
    ///    phantom-thunderstorm code in the 24-hour and 16-day views. Beyond the horizon and for
    ///    unmappable conditions, the Open-Meteo code is kept.
    ///  - **Snow totals** (flag `weatherKitSnowEnabled`, ≤10 days): replaces `snowfall_sum`.
    ///
    /// Both come from a **single** WeatherKit request, so enabling conditions adds no extra
    /// call when snow is already on. On any WeatherKit error the original data is returned
    /// unchanged — the app never regresses below the Open-Meteo behavior.
    #if canImport(WeatherKit)
    @available(iOS 16.0, *)
    private func applyWeatherKitOverlay(for city: City, dateOffset: Int, into weatherData: WeatherData) async -> WeatherData {
        let conditionsWanted = FeatureFlags.shared.weatherKitConditionsEnabled && dateOffset == 0
        // Forecast overlay only applies to the today-anchored full fetch, which is the only path
        // carrying the multi-day hourly/daily arrays the 24-hour and 16-day views render.
        let forecastWanted = FeatureFlags.shared.weatherKitForecastConditionsEnabled && dateOffset == 0
        let snowWanted = FeatureFlags.shared.weatherKitSnowEnabled && dateOffset < 10 && weatherData.daily != nil
        guard conditionsWanted || forecastWanted || snowWanted else { return weatherData }

        let location = CLLocation(latitude: city.latitude, longitude: city.longitude)
        do {
            // One call provides both current condition and the daily forecast.
            let weather = try await WeatherKit.WeatherService.shared.weather(for: location)
            var result = weatherData

            // --- Current condition overlay (today only) ---
            if conditionsWanted {
                let condition = weather.currentWeather.condition
                if let wmo = WeatherCode(weatherKitCondition: condition) {
                    result = result.withCurrentWeatherCode(wmo.rawValue)
                    debugLog("🌤 WK condition overlay for \(city.name): \(condition) → \(wmo.description)")
                } else {
                    debugLog("🌤 WK condition \(condition) has no WMO mapping; keeping Open-Meteo for \(city.name)")
                }
            }

            // --- Forecast condition overlay (hourly + daily, WeatherKit horizon ~10 days) ---
            // Same idea as the current-condition overlay, extended across the forecast horizon:
            // translate each WeatherKit hourly/daily condition to a WMO code and replace the
            // Open-Meteo model code. Hours/days WeatherKit doesn't cover (beyond ~10 days),
            // and conditions with no WMO equivalent, keep the Open-Meteo code — never worse
            // than today. Runs before the snow overlay so the two compose on `result.daily`.
            if forecastWanted {
                let tz = result.timeZone

                // Hourly: match WeatherKit's absolute dates to Open-Meteo's city-local hour
                // strings ("yyyy-MM-dd'T'HH") by formatting the WeatherKit date in the city zone.
                let hourFmt = DateFormatter()
                hourFmt.locale = Locale(identifier: "en_US_POSIX")
                hourFmt.timeZone = tz
                hourFmt.dateFormat = "yyyy-MM-dd'T'HH"
                var wkHourly: [String: Int] = [:]
                for h in weather.hourlyForecast.forecast {
                    if let wmo = WeatherCode(weatherKitCondition: h.condition) {
                        wkHourly[hourFmt.string(from: h.date)] = wmo.rawValue
                    }
                }
                if let hourly = result.hourly, let times = hourly.time, var codes = hourly.weatherCode {
                    var changed = 0
                    for i in 0..<min(times.count, codes.count) {
                        guard let t = times[i], let wmo = wkHourly[String(t.prefix(13))] else { continue }
                        if codes[i] != wmo { codes[i] = wmo; changed += 1 }
                    }
                    if changed > 0 {
                        result = result.withHourly(hourly.withWeatherCodes(codes))
                        debugLog("🌤 WK hourly overlay for \(city.name): \(changed) hours updated")
                    }
                }

                // Daily: match by city-local day ("yyyy-MM-dd"). Daily rows carry no date of their
                // own, so anchor them to the ordered unique days present in the hourly time array.
                let dayFmt = DateFormatter()
                dayFmt.locale = Locale(identifier: "en_US_POSIX")
                dayFmt.timeZone = tz
                dayFmt.dateFormat = "yyyy-MM-dd"
                var wkDaily: [String: Int] = [:]
                for d in weather.dailyForecast.forecast {
                    if let wmo = WeatherCode(weatherKitCondition: d.condition) {
                        wkDaily[dayFmt.string(from: d.date)] = wmo.rawValue
                    }
                }
                if let daily = result.daily, var dcodes = daily.weatherCode {
                    var orderedDays: [String] = []
                    var seen = Set<String>()
                    for case let t? in (result.hourly?.time ?? []) {
                        let day = String(t.prefix(10))
                        if seen.insert(day).inserted { orderedDays.append(day) }
                    }
                    var changed = 0
                    for i in 0..<dcodes.count {
                        guard i < orderedDays.count, let wmo = wkDaily[orderedDays[i]] else { continue }
                        if dcodes[i] != wmo { dcodes[i] = wmo; changed += 1 }
                    }
                    if changed > 0 {
                        result = result.withDaily(daily.withWeatherCodes(dcodes))
                        debugLog("🌤 WK daily overlay for \(city.name): \(changed) days updated")
                    }
                }
            }

            // --- Snow totals overlay ---
            if snowWanted, let daily = result.daily {
                let forecasts = weather.dailyForecast.forecast
                let newSnowfallSum: [Double?]
                if dateOffset == 0 {
                    var snow: [Double?] = daily.snowfallSum ?? Array(repeating: nil, count: daily.temperature2mMax.count)
                    for i in 0..<min(forecasts.count, snow.count) {
                        snow[i] = forecasts[i].snowfallAmount.converted(to: .centimeters).value
                    }
                    newSnowfallSum = snow
                } else if dateOffset < forecasts.count {
                    newSnowfallSum = [forecasts[dateOffset].snowfallAmount.converted(to: .centimeters).value]
                } else {
                    newSnowfallSum = daily.snowfallSum ?? []
                }

                let newDaily = WeatherData.DailyWeather(
                    temperature2mMax: daily.temperature2mMax,
                    temperature2mMin: daily.temperature2mMin,
                    sunrise: daily.sunrise,
                    sunset: daily.sunset,
                    weatherCode: daily.weatherCode,
                    precipitationSum: daily.precipitationSum,
                    rainSum: daily.rainSum,
                    snowfallSum: newSnowfallSum,
                    precipitationProbabilityMax: daily.precipitationProbabilityMax,
                    uvIndexMax: daily.uvIndexMax,
                    daylightDuration: daily.daylightDuration,
                    sunshineDuration: daily.sunshineDuration,
                    windSpeed10mMax: daily.windSpeed10mMax,
                    windDirectionDominant: daily.windDirectionDominant,
                    apparentTemperatureMax: daily.apparentTemperatureMax,
                    apparentTemperatureMin: daily.apparentTemperatureMin
                )
                result = WeatherData(current: result.current, daily: newDaily, hourly: result.hourly, utcOffsetSeconds: result.utcOffsetSeconds)
                debugLog("❄️ WK snow overlay applied for \(city.name) offset=\(dateOffset) days=\(forecasts.count)")
            }

            return result
        } catch {
            debugLog("⚠️ WK overlay failed for \(city.name): \(error.localizedDescription)")
            return weatherData
        }
    }

    /// Fetches WeatherKit's current condition for a coordinate and returns it as a WMO code,
    /// or nil if conditions are disabled, the call fails, or the condition has no WMO mapping.
    /// Used by the lightweight browse/regional paths that don't go through `applyWeatherKitOverlay`.
    @available(iOS 16.0, *)
    private func weatherKitCurrentWMOCode(latitude: Double, longitude: Double) async -> Int? {
        guard FeatureFlags.shared.weatherKitConditionsEnabled else { return nil }
        // Coordinate-keyed TTL cache (main-actor isolated): avoids re-billing WeatherKit on every
        // browse-row reappearance — HI-1. The overlay is preserved; only redundant calls are cut.
        let key = String(format: "%.2f,%.2f", latitude, longitude)
        if let wmo = wkConditionCache.value(for: key) {
            return wmo
        }
        do {
            let current = try await WeatherKit.WeatherService.shared.weather(
                for: CLLocation(latitude: latitude, longitude: longitude), including: .current)
            guard let wmo = WeatherCode(weatherKitCondition: current.condition)?.rawValue else { return nil }
            wkConditionCache.set(wmo, for: key)
            return wmo
        } catch {
            debugLog("⚠️ WK condition (browse) failed for \(latitude),\(longitude): \(error.localizedDescription)")
            return nil
        }
    }
    #endif
    
    // MARK: - Weather Alerts (NWS & WeatherKit)
    
    private var alertsCache: [UUID: (alerts: [WeatherAlert], timestamp: Date)] = [:]
    // alertsCache is @MainActor-isolated (WeatherService is @MainActor); no lock needed.

    // Coordinate-keyed cache of WeatherKit current WMO codes for the lightweight browse/regional
    // paths, with a short TTL. Avoids redundant WeatherKit billing — HI-1. Shared TTLCache type.
    private let wkConditionCache = TTLCache<String, Int>(ttl: 10 * 60)
    private let alertsCacheMinutes: TimeInterval = 5
    
    /// Countries where WeatherKit alerts are known to work
    /// Source: Apple WeatherKit documentation and real-world testing
    private let weatherKitSupportedCountries = Set([
        "United States",
        "Canada",
        "United Kingdom",
        "Germany",
        "France",
        "Spain",
        "Italy",
        "Netherlands",
        "Belgium",
        "Austria",
        "Switzerland",
        "Denmark",
        "Sweden",
        "Norway",
        "Finland",
        "Ireland",
        "Portugal",
        "Japan",
        "Australia",
        "New Zealand"
    ])
    
    /// Checks if WeatherKit alerts are likely supported for this country
    private func isWeatherKitSupported(for city: City) -> Bool {
        return weatherKitSupportedCountries.contains(city.country)
    }
    
    /// Fetches severe weather alerts using appropriate source based on location
    /// - US cities: National Weather Service (detailed alerts with full text)
    /// - International: Apple WeatherKit (when feature flag enabled AND country supported)
    /// - Returns: Array of active weather alerts (empty if no alerts or service unavailable)
    /// Signals that the alert state could not be determined (vs. a genuine "no alerts").
    enum AlertFetchError: Error { case badStatus(Int) }

    /// URLSession used for NWS alert fetches. Injectable so the failure / empty-200 paths can be
    /// tested deterministically without the network (defaults to `.shared`).
    var alertsURLSession: URLSession = .shared

    func fetchNWSAlerts(for city: City) async throws -> [WeatherAlert] {
        // Check cache first, filtering out expired alerts
        if let cached = alertsCache[city.id] {
            let age = Date().timeIntervalSince(cached.timestamp)
            if age < alertsCacheMinutes * 60 {
                let activeAlerts = cached.alerts.filter { !$0.isExpired }
                return activeAlerts
            }
        }
        
        // US cities: Use NWS for detailed alerts
        if city.country == "United States" {
            return try await fetchNWSAlertsDirectly(for: city)
        }
        
        // International cities: Use WeatherKit if enabled AND country supported
        if FeatureFlags.shared.weatherKitAlertsEnabled {
            if isWeatherKitSupported(for: city) {
                return try await fetchWeatherKitAlerts(for: city)
            } else {
                return []
            }
        } else {
            return []
        }
    }
    
    /// Fetches alerts directly from National Weather Service API (US only)
    private func fetchNWSAlertsDirectly(for city: City) async throws -> [WeatherAlert] {
        
        let urlString = "https://api.weather.gov/alerts/active?point=\(city.latitude),\(city.longitude)"
        guard let url = URL(string: urlString) else {
            return []
        }
        
        var request = URLRequest(url: url)
        request.setValue("WeatherFast/1.0 iOS", forHTTPHeaderField: "User-Agent")

        do {
            let (data, response) = try await alertsURLSession.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                // A non-200 means we could NOT determine the alert state. Throw so the UI can show a
                // distinct "couldn't check alerts" state — a fetch failure must never render as
                // "No active alerts" for a safety feature (HI-3 / product review #1).
                let status = (response as? HTTPURLResponse)?.statusCode ?? -1
                AppLogger.network.error("NWS alerts non-200 (\(status, privacy: .public)) for \(city.name, privacy: .public)")
                throw AlertFetchError.badStatus(status)
            }
            
            // Don't use .iso8601 date decoding strategy - it interferes with FlexibleStringOrArray
            // and causes crashes when NWS API puts ISO date strings in text fields
            let decoder = JSONDecoder()
            
            let nwsResponse = try decoder.decode(NWSAlertsResponse.self, from: data)
            
            // Convert NWS features to WeatherAlert objects
            // NWS dates are real ISO8601 with timezone — one formatter created once, outside the closure
            // to avoid ICU internal-cache memory corruption when allocating per-iteration on a background thread
            let nwsDateFormatter = ISO8601DateFormatter()
            let alerts = nwsResponse.features.compactMap { feature -> WeatherAlert? in
                let props = feature.properties
                
                // Parse severity
                let severity: AlertSeverity
                switch props.severity?.lowercased() {
                case "extreme": severity = .extreme
                case "severe": severity = .severe
                case "moderate": severity = .moderate
                case "minor": severity = .minor
                default: severity = .unknown
                }
                
                // Parse onset and expires dates.
                // Prefer `ends` (when hazardous conditions end) over `expires` (when the NWS alert
                // product expires, which can pre-date onset for refreshed advisories — causing the
                // "From: Jun 30, Until: Jun 20" reversal customers reported).
                let onset = props.onset.flatMap { nwsDateFormatter.date(from: $0) } ?? Date()
                let endsDate = props.ends.flatMap { nwsDateFormatter.date(from: $0) }
                let expiresDate = props.expires.flatMap { nwsDateFormatter.date(from: $0) } ?? Date().addingTimeInterval(86400)
                let expires = max(endsDate ?? expiresDate, onset)
                
                return WeatherAlert(
                    id: props.id,
                    event: props.event,
                    severity: severity,
                    headline: props.headline,
                    description: props.description,
                    instruction: props.instruction,
                    onset: onset,
                    expires: expires,
                    areaDesc: props.areaDesc,
                    source: .nws,
                    detailsURL: nil  // NWS alerts use weather.gov link in UI
                )
            }
            
            // Filter out expired alerts
            let activeAlerts = alerts.filter { !$0.isExpired }
            
            // Cache the results
            alertsCache[city.id] = (activeAlerts, Date())
            
            return activeAlerts

        } catch {
            // Network/decoding failure — we could NOT determine the alert state. Rethrow so the UI
            // shows "couldn't check alerts" rather than a misleading "No active alerts" (HI-3 /
            // product review #1). Not cached, so the next attempt (or a retry) tries again.
            AppLogger.network.error("NWS alerts fetch failed for \(city.name, privacy: .public): \(error.localizedDescription, privacy: .public)")
            throw error
        }
    }

    /// Fetches weather alerts from Apple WeatherKit (international cities)
    private func fetchWeatherKitAlerts(for city: City) async throws -> [WeatherAlert] {
        #if canImport(WeatherKit)
        let location = CLLocation(latitude: city.latitude, longitude: city.longitude)
        let appleWeatherService = WeatherKit.WeatherService.shared
        
        do {
            let weatherAlerts = try await appleWeatherService.weather(
                for: location,
                including: .alerts
            )
            
            // Convert WeatherKit alerts to our WeatherAlert model
            let alerts = weatherAlerts?.compactMap { wkAlert -> WeatherAlert? in
                // Map WeatherKit severity to our AlertSeverity
                let severity: AlertSeverity
                switch wkAlert.severity {
                case .extreme: severity = .extreme
                case .severe: severity = .severe
                case .moderate: severity = .moderate
                case .minor: severity = .minor
                case .unknown: severity = .unknown
                @unknown default: severity = .unknown
                }
                
                // WeatherKit provides limited info - just summary and region
                // Build a user-friendly description
                let regionText = wkAlert.region ?? "your area"
                let description = "Government weather alert issued for \(regionText). Tap 'View Alert Details' below for complete information from local authorities."
                
                return WeatherAlert(
                    id: UUID().uuidString,
                    event: wkAlert.summary,
                    severity: severity,
                    headline: wkAlert.summary,
                    description: description,
                    instruction: nil, // WeatherKit doesn't provide safety instructions
                    onset: Date(), // WeatherKit doesn't expose onset directly
                    expires: Date().addingTimeInterval(86400), // Default to 24 hours
                    areaDesc: wkAlert.region,
                    source: .weatherKit,
                    detailsURL: wkAlert.detailsURL.absoluteString
                )
            } ?? []
            
            // Filter expired alerts
            let activeAlerts = alerts.filter { !$0.isExpired }
            
            // Cache results
            alertsCache[city.id] = (activeAlerts, Date())
            

            return activeAlerts
            
        } catch {
            let nsError = error as NSError
            let errorDescription = nsError.localizedDescription

            // HTTP 400 = this region simply has no WeatherKit alert coverage. That's a genuine
            // "no alerts here," not a failure to check — cache empty and return normally.
            if errorDescription.contains("400") || errorDescription.contains("responseFailed: 400") {
                debugLog("⚠️ WeatherKit alerts not available for \(city.name) (region unsupported)")
                alertsCache[city.id] = ([], Date())
                return []
            }

            // Any other error (auth, daemon, network) means we could NOT determine the alert
            // state. Rethrow so the UI shows "couldn't check alerts" instead of a false
            // "No active alerts" (product review #1). Not cached, so a retry re-attempts.
            AppLogger.network.error("WeatherKit alerts fetch failed for \(city.name, privacy: .public): \(errorDescription, privacy: .public)")
            throw error
        }
        #else
        debugLog("⚠️ WeatherKit not available on this platform")
        return []
        #endif
    }
    
    // MARK: - Cache Management
    
    /// Get cache metadata for a city (for displaying "Using cached data from...")
    func getCacheMetadata(for cacheKey: WeatherCacheKey) async -> CachedWeather? {
        guard let timestamp = cacheTimestamps[cacheKey],
              let weather = weatherCache[cacheKey] else {
            return nil
        }
        
        return CachedWeather(weather: weather, timestamp: timestamp, cityId: cacheKey.cityId)
    }
    
    /// Clear all persistent cached weather data
    func clearPersistentCache() {
        // DISABLED: Persistent cache too slow
        debugLog("ℹ️ Persistent cache disabled for performance")
    }
    
    // MARK: - Persistence
    
    private static let citiesModifiedKey = "SavedCitiesLastModified"

    private func saveCities() {
        do {
            let encoded = try JSONEncoder().encode(savedCities)
            sharedDefaults.set(encoded, forKey: userDefaultsKey)
            // Record the local edit time so iCloud sync can apply last-writer-wins (HI-4).
            let now = Date()
            sharedDefaults.set(now.timeIntervalSince1970, forKey: Self.citiesModifiedKey)
            iCloudSyncService.shared.pushCities(savedCities, modified: now)
        } catch {
            AppLogger.service.error("Failed to save cities: \(error)")
        }
    }

    // MARK: - iCloud Sync

    private func observeCloudCityChanges() {
        NotificationCenter.default.addObserver(
            forName: .iCloudCitiesDidChangeExternally,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.applyRemoteCities()
        }
    }

    /// Apply the cities list currently in iCloud.
    /// - Parameter force: when true (an explicit user choice like "Use iCloud List"), skip the
    ///   last-writer-wins comparison and always adopt the remote list.
    func applyRemoteCities(force: Bool = false) {
        guard let remoteCities = iCloudSyncService.shared.pullCities() else { return }

        // Last-writer-wins by edit time (HI-4), but only when the remote actually carries a
        // timestamp. A legacy blob pushed by an app version before timestamps existed has none —
        // that's real user data, not garbage, so we must NOT reject it as "older than local"
        // (which would stomp it with our local list during the upgrade window). We also skip the
        // check entirely when the user explicitly asked for the iCloud list (force).
        if !force, let remoteTS = iCloudSyncService.shared.pullCitiesTimestamp() {
            let localTS = Date(timeIntervalSince1970: sharedDefaults.double(forKey: Self.citiesModifiedKey))
            if remoteTS < localTS {
                // Our local copy is newer — re-push it (keeping our timestamp) so the other device
                // converges onto it, then keep local unchanged. No loop: accepting never re-pushes.
                AppLogger.service.debug("iCloud: ignoring older remote cities; re-pushing newer local")
                iCloudSyncService.shared.pushCities(savedCities, modified: localTS)
                return
            }
        }

        guard remoteCities != savedCities else { return }
        savedCities = remoteCities
        // Stamp local bookkeeping with the remote's timestamp (or now, if the remote was a legacy
        // un-timestamped blob) so future comparisons stay consistent.
        let appliedTS = iCloudSyncService.shared.pullCitiesTimestamp() ?? Date()
        sharedDefaults.set(appliedTS.timeIntervalSince1970, forKey: Self.citiesModifiedKey)
        do {
            let encoded = try JSONEncoder().encode(remoteCities)
            sharedDefaults.set(encoded, forKey: userDefaultsKey)
            AppLogger.service.debug("iCloud: applied \(remoteCities.count) cities")
        } catch {
            AppLogger.service.error("Failed to save remote cities locally: \(error)")
        }
    }

    /// Push the local city list to iCloud and record the local edit time together, so the LWW
    /// bookkeeping read by applyRemoteCities() can never drift from what was pushed (review
    /// finding 1). Use this instead of calling iCloudSyncService.pushCities() directly.
    func pushCitiesToCloud() {
        let now = Date()
        sharedDefaults.set(now.timeIntervalSince1970, forKey: Self.citiesModifiedKey)
        iCloudSyncService.shared.pushCities(savedCities, modified: now)
    }
    
    // MARK: - Data Migration
    
    /// Migrate country names from native language to English (one-time)
    private func migrateCountryNamesIfNeeded() {
        let migrationKey = "countryNamesMigrated_v1"
        
        // Check if migration already completed
        guard !UserDefaults.standard.bool(forKey: migrationKey) else {
            return
        }
        
        var migratedCount = 0
        
        // Create backup before migration
        if let encoded = try? JSONEncoder().encode(savedCities) {
            UserDefaults.standard.set(encoded, forKey: "cities_backup_preMigration")
        }
        
        // Migrate each city's country name
        var updatedCities: [City] = []
        for city in savedCities {
            let oldCountry = city.country
            let normalizedCountry = CountryNames.normalize(oldCountry)
            let newCountry = normalizedCountry ?? oldCountry // Use original if normalization returns nil
            
            if oldCountry != newCountry {
                // Create new City with updated country
                let updatedCity = City(
                    id: city.id,
                    name: city.name,
                    state: city.state,
                    country: newCountry,
                    latitude: city.latitude,
                    longitude: city.longitude
                )
                updatedCities.append(updatedCity)
                migratedCount += 1
            } else {
                updatedCities.append(city)
            }
        }
        
        // Update savedCities with migrated data
        savedCities = updatedCities
        
        // Save migrated cities if any changes made
        if migratedCount > 0 {
            saveCities()
        }
        
        // Mark migration as complete (even if no changes)
        UserDefaults.standard.set(true, forKey: migrationKey)
    }
    
    // MARK: - Persistence
    
    private func migrateToAppGroupIfNeeded() {
        let migrationKey = "appGroupMigration_v1"
        guard !UserDefaults.standard.bool(forKey: migrationKey) else { return }
        if let data = UserDefaults.standard.data(forKey: userDefaultsKey),
           sharedDefaults.data(forKey: userDefaultsKey) == nil {
            sharedDefaults.set(data, forKey: userDefaultsKey)
        }
        UserDefaults.standard.set(true, forKey: migrationKey)
    }

    private func loadSavedCities() {
        migrateToAppGroupIfNeeded()
        guard let data = sharedDefaults.data(forKey: userDefaultsKey) else {
            // First launch — seed default cities
            savedCities = [
                City(name: "Madison", state: "Wisconsin", country: "United States", latitude: 43.074761, longitude: -89.3837613),
                City(name: "San Diego", state: "California", country: "United States", latitude: 32.7174202, longitude: -117.162772)
            ]
            saveCities()
            return
        }
        
        do {
            savedCities = try JSONDecoder().decode([City].self, from: data)
            // DON'T fetch weather during init - let the view trigger it after appearing
        } catch {
            AppLogger.service.error("Failed to decode saved cities — resetting to defaults: \(error)")
            savedCities = [
                City(name: "Madison", state: "Wisconsin", country: "United States", latitude: 43.074761, longitude: -89.3837613),
                City(name: "San Diego", state: "California", country: "United States", latitude: 32.7174202, longitude: -117.162772)
            ]
            saveCities()
        }
    }
}

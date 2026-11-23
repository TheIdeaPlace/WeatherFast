//
//  StateCitiesView.swift
//  Fast Weather
//
//  View for displaying cities in a specific US state
//

import SwiftUI

// Primary geography sort; use secondary axis only when primary values are exactly equal
func geographySort<T>(
    _ a: T, _ b: T,
    primary: KeyPath<T, Double>,
    primaryDescending: Bool,
    secondary: KeyPath<T, Double>,
    secondaryDescending: Bool
) -> Bool {
    let aP = a[keyPath: primary]
    let bP = b[keyPath: primary]
    if aP != bP {
        return primaryDescending ? aP > bP : aP < bP
    }
    let aS = a[keyPath: secondary]
    let bS = b[keyPath: secondary]
    return secondaryDescending ? aS > bS : aS < bS
}

struct StateCitiesView: View {
    let state: String
    @ObservedObject var cityDataService: CityDataService
    let favoritesService: BrowseFavoritesService
    let overrideSortOrder: BrowseSortOrder?
    @EnvironmentObject var weatherService: WeatherService
    @AppStorage("defaultBrowseSortOrder") private var defaultSortRaw: String = BrowseSortOrder.nameAZ.rawValue
    @State private var searchText = ""
    @State private var weatherData: [String: WeatherData] = [:]
    @State private var isLoadingWeather = false
    @State private var hasCompletedInitialLoad = false
    @State private var sortOrder: BrowseSortOrder

    init(state: String, cityDataService: CityDataService, favoritesService: BrowseFavoritesService, overrideSortOrder: BrowseSortOrder?) {
        self.state = state
        self.cityDataService = cityDataService
        self.favoritesService = favoritesService
        self.overrideSortOrder = overrideSortOrder
        self._sortOrder = State(initialValue: overrideSortOrder ?? .nameAZ)
    }

    private var cities: [CityLocation] {
        cityDataService.cities(forState: state)
    }

    private var filteredCities: [CityLocation] {
        let base: [CityLocation]
        if searchText.isEmpty {
            base = cities
        } else {
            base = cities.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
        }
        switch sortOrder {
        case .tempHighLow:
            return base.sorted { a, b in
                let ta = weatherData[a.cacheKey]?.current.temperature2m ?? -.infinity
                let tb = weatherData[b.cacheKey]?.current.temperature2m ?? -.infinity
                return ta > tb
            }
        case .tempLowHigh:
            return base.sorted { a, b in
                let ta = weatherData[a.cacheKey]?.current.temperature2m ?? .infinity
                let tb = weatherData[b.cacheKey]?.current.temperature2m ?? .infinity
                return ta < tb
            }
        default:
            return base.sorted(by: sortComparator)
        }
    }

    private func sortComparator(_ a: CityLocation, _ b: CityLocation) -> Bool {
        switch sortOrder {
        case .nameAZ:    return a.name.localizedCompare(b.name) == .orderedAscending
        case .nameZA:    return a.name.localizedCompare(b.name) == .orderedDescending
        case .northSouth: return geographySort(a, b, primary: \.latitude,  primaryDescending: true,  secondary: \.longitude, secondaryDescending: false)
        case .southNorth: return geographySort(a, b, primary: \.latitude,  primaryDescending: false, secondary: \.longitude, secondaryDescending: false)
        case .eastWest:   return geographySort(a, b, primary: \.longitude, primaryDescending: true,  secondary: \.latitude,  secondaryDescending: true)
        case .westEast:   return geographySort(a, b, primary: \.longitude, primaryDescending: false, secondary: \.latitude,  secondaryDescending: true)
        case .tempHighLow, .tempLowHigh: return a.name.localizedCompare(b.name) == .orderedAscending
        }
    }

    var body: some View {
        List {
            ForEach(filteredCities, id: \.self) { cityLocation in
                NavigationLink(destination: BrowseCityDetailDestination(cityLocation: cityLocation)) {
                    CityLocationRowOptimized(
                        cityLocation: cityLocation,
                        weatherData: weatherData[cityLocation.cacheKey],
                        isLoading: !hasCompletedInitialLoad
                    )
                }
            }
        }
        .navigationTitle(state)
        .searchable(text: $searchText, prompt: "Search cities in \(state)")
        .accessibilityElement(children: .contain)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                sortMenu
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                favoriteButton
            }
        }
        .onAppear {
            if overrideSortOrder == nil {
                sortOrder = BrowseSortOrder(rawValue: defaultSortRaw) ?? .nameAZ
            }
        }
        .task {
            await loadAllWeather()
        }
    }

    private var favoriteButton: some View {
        let isFav = favoritesService.isFavorite(name: state, regionType: .us)
        return Button {
            if isFav {
                favoritesService.remove(name: state, regionType: .us)
            } else {
                favoritesService.add(name: state, regionType: .us, sortOrder: sortOrder)
            }
        } label: {
            Image(systemName: isFav ? "star.fill" : "star")
                .foregroundColor(isFav ? .yellow : nil)
        }
        .accessibilityLabel(isFav ? "\(state), Remove from Favorites" : "\(state), Add to Favorites")
    }

    private var sortMenu: some View {
        Menu {
            Section("Alphabetical") {
                ForEach([BrowseSortOrder.nameAZ, .nameZA]) { option in
                    Button {
                        sortOrder = option
                    } label: {
                        Label(option.rawValue, systemImage: sortOrder == option ? "checkmark" : option.systemImage)
                    }
                    // Announce the active sort to VoiceOver (was conveyed by checkmark icon only) — VO-4
                    .accessibilityAddTraits(sortOrder == option ? .isSelected : [])
                }
            }
            Section("Geographic") {
                ForEach([BrowseSortOrder.northSouth, .southNorth, .eastWest, .westEast]) { option in
                    Button {
                        sortOrder = option
                    } label: {
                        Label(option.rawValue, systemImage: sortOrder == option ? "checkmark" : option.systemImage)
                    }
                    // Announce the active sort to VoiceOver (was conveyed by checkmark icon only) — VO-4
                    .accessibilityAddTraits(sortOrder == option ? .isSelected : [])
                }
            }
            Section("Temperature") {
                ForEach([BrowseSortOrder.tempHighLow, .tempLowHigh]) { option in
                    Button {
                        sortOrder = option
                    } label: {
                        Label(option.rawValue, systemImage: sortOrder == option ? "checkmark" : option.systemImage)
                    }
                    // Announce the active sort to VoiceOver (was conveyed by checkmark icon only) — VO-4
                    .accessibilityAddTraits(sortOrder == option ? .isSelected : [])
                }
            }
        } label: {
            Label("Sort", systemImage: "arrow.up.arrow.down")
        }
        .accessibilityLabel("Sort cities. Current sort: \(sortOrder.rawValue)")
    }

    private func loadAllWeather() async {
        guard weatherData.isEmpty && !isLoadingWeather else { return }
        isLoadingWeather = true

        let locations = cities.map { (latitude: $0.latitude, longitude: $0.longitude) }
        let results = await weatherService.batchFetchWeatherBasic(for: locations)

        await MainActor.run {
            weatherData = results
            isLoadingWeather = false
            hasCompletedInitialLoad = true
        }
    }
}

struct CountryCitiesView: View {
    let country: String
    @ObservedObject var cityDataService: CityDataService
    let favoritesService: BrowseFavoritesService
    let overrideSortOrder: BrowseSortOrder?
    @EnvironmentObject var weatherService: WeatherService
    @AppStorage("defaultBrowseSortOrder") private var defaultSortRaw: String = BrowseSortOrder.nameAZ.rawValue
    @State private var searchText = ""
    @State private var weatherData: [String: WeatherData] = [:]
    @State private var isLoadingWeather = false
    @State private var hasCompletedInitialLoad = false
    @State private var sortOrder: BrowseSortOrder

    init(country: String, cityDataService: CityDataService, favoritesService: BrowseFavoritesService, overrideSortOrder: BrowseSortOrder?) {
        self.country = country
        self.cityDataService = cityDataService
        self.favoritesService = favoritesService
        self.overrideSortOrder = overrideSortOrder
        self._sortOrder = State(initialValue: overrideSortOrder ?? .nameAZ)
    }

    private var cities: [CityLocation] {
        cityDataService.cities(forCountry: country)
    }

    private var filteredCities: [CityLocation] {
        let base: [CityLocation]
        if searchText.isEmpty {
            base = cities
        } else {
            base = cities.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
        }
        switch sortOrder {
        case .tempHighLow:
            return base.sorted { a, b in
                let ta = weatherData[a.cacheKey]?.current.temperature2m ?? -.infinity
                let tb = weatherData[b.cacheKey]?.current.temperature2m ?? -.infinity
                return ta > tb
            }
        case .tempLowHigh:
            return base.sorted { a, b in
                let ta = weatherData[a.cacheKey]?.current.temperature2m ?? .infinity
                let tb = weatherData[b.cacheKey]?.current.temperature2m ?? .infinity
                return ta < tb
            }
        default:
            return base.sorted(by: sortComparator)
        }
    }

    private func sortComparator(_ a: CityLocation, _ b: CityLocation) -> Bool {
        switch sortOrder {
        case .nameAZ:     return a.name.localizedCompare(b.name) == .orderedAscending
        case .nameZA:     return a.name.localizedCompare(b.name) == .orderedDescending
        case .northSouth: return geographySort(a, b, primary: \.latitude,  primaryDescending: true,  secondary: \.longitude, secondaryDescending: false)
        case .southNorth: return geographySort(a, b, primary: \.latitude,  primaryDescending: false, secondary: \.longitude, secondaryDescending: false)
        case .eastWest:   return geographySort(a, b, primary: \.longitude, primaryDescending: true,  secondary: \.latitude,  secondaryDescending: true)
        case .westEast:   return geographySort(a, b, primary: \.longitude, primaryDescending: false, secondary: \.latitude,  secondaryDescending: true)
        case .tempHighLow, .tempLowHigh: return a.name.localizedCompare(b.name) == .orderedAscending
        }
    }

    var body: some View {
        List {
            ForEach(filteredCities, id: \.self) { cityLocation in
                NavigationLink(destination: BrowseCityDetailDestination(cityLocation: cityLocation)) {
                    CityLocationRowOptimized(
                        cityLocation: cityLocation,
                        weatherData: weatherData[cityLocation.cacheKey],
                        isLoading: !hasCompletedInitialLoad
                    )
                }
            }
        }
        .navigationTitle(country)
        .searchable(text: $searchText, prompt: "Search cities in \(country)")
        .accessibilityElement(children: .contain)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                sortMenu
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                favoriteButton
            }
        }
        .onAppear {
            if overrideSortOrder == nil {
                sortOrder = BrowseSortOrder(rawValue: defaultSortRaw) ?? .nameAZ
            }
        }
        .task {
            await loadAllWeather()
        }
    }

    private var favoriteButton: some View {
        let isFav = favoritesService.isFavorite(name: country, regionType: .international)
        return Button {
            if isFav {
                favoritesService.remove(name: country, regionType: .international)
            } else {
                favoritesService.add(name: country, regionType: .international, sortOrder: sortOrder)
            }
        } label: {
            Image(systemName: isFav ? "star.fill" : "star")
                .foregroundColor(isFav ? .yellow : nil)
        }
        .accessibilityLabel(isFav ? "\(country), Remove from Favorites" : "\(country), Add to Favorites")
    }

    private var sortMenu: some View {
        Menu {
            Section("Alphabetical") {
                ForEach([BrowseSortOrder.nameAZ, .nameZA]) { option in
                    Button {
                        sortOrder = option
                    } label: {
                        Label(option.rawValue, systemImage: sortOrder == option ? "checkmark" : option.systemImage)
                    }
                    // Announce the active sort to VoiceOver (was conveyed by checkmark icon only) — VO-4
                    .accessibilityAddTraits(sortOrder == option ? .isSelected : [])
                }
            }
            Section("Geographic") {
                ForEach([BrowseSortOrder.northSouth, .southNorth, .eastWest, .westEast]) { option in
                    Button {
                        sortOrder = option
                    } label: {
                        Label(option.rawValue, systemImage: sortOrder == option ? "checkmark" : option.systemImage)
                    }
                    // Announce the active sort to VoiceOver (was conveyed by checkmark icon only) — VO-4
                    .accessibilityAddTraits(sortOrder == option ? .isSelected : [])
                }
            }
            Section("Temperature") {
                ForEach([BrowseSortOrder.tempHighLow, .tempLowHigh]) { option in
                    Button {
                        sortOrder = option
                    } label: {
                        Label(option.rawValue, systemImage: sortOrder == option ? "checkmark" : option.systemImage)
                    }
                    // Announce the active sort to VoiceOver (was conveyed by checkmark icon only) — VO-4
                    .accessibilityAddTraits(sortOrder == option ? .isSelected : [])
                }
            }
        } label: {
            Label("Sort", systemImage: "arrow.up.arrow.down")
        }
        .accessibilityLabel("Sort cities. Current sort: \(sortOrder.rawValue)")
    }

    private func loadAllWeather() async {
        guard weatherData.isEmpty && !isLoadingWeather else { return }
        isLoadingWeather = true

        let locations = cities.map { (latitude: $0.latitude, longitude: $0.longitude) }
        let results = await weatherService.batchFetchWeatherBasic(for: locations)

        await MainActor.run {
            weatherData = results
            isLoadingWeather = false
            hasCompletedInitialLoad = true
        }
    }
}

// Optimized row that uses pre-loaded weather data
struct CityLocationRowOptimized: View {
    let cityLocation: CityLocation
    let weatherData: WeatherData?
    let isLoading: Bool
    @EnvironmentObject var weatherService: WeatherService
    @EnvironmentObject var settingsManager: SettingsManager
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(cityLocation.displayName)
                    .font(.body)
                
                if let weatherData = weatherData {
                    HStack(spacing: 8) {
                        if let weatherCode = weatherData.current.weatherCodeEnum {
                            Image(systemName: weatherCode.systemImageName(isDay: (weatherData.current.isDay ?? 1) == 1))
                                .foregroundColor(.blue)
                        }
                        Text(formatTemperature(weatherData.current.temperature2m))
                            .font(.headline)
                            .foregroundColor(.primary)
                        if let weatherCode = weatherData.current.weatherCodeEnum {
                            Text(weatherCode.description)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                                .truncationMode(.tail)
                        }
                    }
                } else if isLoading {
                    HStack(spacing: 4) {
                        ProgressView()
                            .scaleEffect(0.7)
                        Text("Loading...")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                } else {
                    HStack(spacing: 4) {
                        Image(systemName: "exclamationmark.triangle")
                            .foregroundColor(.orange)
                            .font(.caption)
                        Text("Unable to load")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            
            Spacer()
            
            Image(systemName: "chevron.right")
                .foregroundColor(.secondary)
                .font(.caption)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(weatherAccessibilityLabel)
        .accessibilityAction(named: "Add to My Cities") {
            addCity()
        }
    }
    
    private var weatherAccessibilityLabel: String {
        if let weatherData = weatherData {
            let temp = formatTemperature(weatherData.current.temperature2m)
            let desc = weatherData.current.weatherCodeEnum?.description ?? "unknown conditions"
            return "\(cityLocation.displayName), \(temp), \(desc)"
        } else if isLoading {
            return "\(cityLocation.displayName), loading weather"
        } else {
            return "\(cityLocation.displayName), unable to load weather"
        }
    }
    
    private func addCity() {
        let city = cityLocation.toCity()
        weatherService.addCity(city)
        
        // Announce to VoiceOver
        UIAccessibility.post(notification: .announcement, argument: "\(cityLocation.displayName) added to My Cities")
    }
    
    private func formatTemperature(_ celsius: Double) -> String {
        let temp = settingsManager.settings.temperatureUnit.convert(celsius)
        let unit = settingsManager.settings.temperatureUnit == .fahrenheit ? "F" : "C"
        return String(format: "%.0f°%@", temp, unit)
    }
}

// Legacy row with on-demand loading (kept for backward compatibility)
struct CityLocationRow: View {
    let cityLocation: CityLocation
    @EnvironmentObject var weatherService: WeatherService
    @EnvironmentObject var settingsManager: SettingsManager
    @State private var weatherData: WeatherData?
    @State private var isLoadingWeather = false
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(cityLocation.displayName)
                    .font(.body)
                
                if isLoadingWeather {
                    HStack(spacing: 4) {
                        ProgressView()
                            .scaleEffect(0.7)
                        Text("Loading weather...")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                } else if let weatherData = weatherData {
                    HStack(spacing: 8) {
                        if let weatherCode = weatherData.current.weatherCodeEnum {
                            Image(systemName: weatherCode.systemImageName(isDay: (weatherData.current.isDay ?? 1) == 1))
                                .foregroundColor(.blue)
                        }
                        Text(formatTemperature(weatherData.current.temperature2m))
                            .font(.headline)
                            .foregroundColor(.primary)
                        if let weatherCode = weatherData.current.weatherCodeEnum {
                            Text(weatherCode.description)
                                .lineLimit(1)
                                .truncationMode(.tail)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                } else {
                    Text("Tap to view details")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            Spacer()
            
            Image(systemName: "chevron.right")
                .foregroundColor(.secondary)
                .font(.caption)
        }
        .onAppear {
            if weatherData == nil {
                loadWeather()
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(weatherAccessibilityLabel)
        .accessibilityAction(named: "Add to My Cities") {
            addCity()
        }
    }
    
    private var weatherAccessibilityLabel: String {
        if let weatherData = weatherData {
            let temp = formatTemperature(weatherData.current.temperature2m)
            let desc = weatherData.current.weatherCodeEnum?.description ?? "unknown conditions"
            return "\(cityLocation.displayName), \(temp), \(desc)"
        } else if isLoadingWeather {
            return "\(cityLocation.displayName), loading weather"
        }
        return cityLocation.displayName
    }
    
    private func loadWeather() {
        guard !isLoadingWeather else { return }
        isLoadingWeather = true
        
        Task {
            do {
                let fetchedWeather = try await weatherService.fetchWeatherBasic(
                    latitude: cityLocation.latitude,
                    longitude: cityLocation.longitude
                )
                await MainActor.run {
                    weatherData = fetchedWeather
                    isLoadingWeather = false
                }
            } catch {
                await MainActor.run {
                    isLoadingWeather = false
                }
            }
        }
    }
    
    private func addCity() {
        let city = cityLocation.toCity()
        weatherService.addCity(city)
        
        // Announce to VoiceOver
        UIAccessibility.post(notification: .announcement, argument: "\(cityLocation.displayName) added to My Cities")
    }
    
    private func formatTemperature(_ celsius: Double) -> String {
        let temp = settingsManager.settings.temperatureUnit.convert(celsius)
        let unit = settingsManager.settings.temperatureUnit == .fahrenheit ? "F" : "C"
        return String(format: "%.0f°%@", temp, unit)
    }
}

// Detail view for a city from browsing (not yet added)
struct CityLocationDetailView: View {
    let cityLocation: CityLocation
    @EnvironmentObject var weatherService: WeatherService
    @EnvironmentObject var settingsManager: SettingsManager
    @State private var weatherData: WeatherData?
    @State private var isLoadingWeather = true
    
    private var isAlreadyAdded: Bool {
        weatherService.savedCities.contains { city in
            city.latitude == cityLocation.latitude &&
            city.longitude == cityLocation.longitude
        }
    }
    
    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                if isLoadingWeather {
                    ProgressView("Loading weather data...")
                        .padding()
                } else if let weather = weatherData {
                    // Main weather display
                    VStack(spacing: 16) {
                        // Temperature and condition
                        if let weatherCode = weather.current.weatherCodeEnum {
                            Image(systemName: weatherCode.systemImageName(isDay: (weather.current.isDay ?? 1) == 1))
                                .font(.system(size: 80))
                                .foregroundColor(.blue)
                                .accessibilityHidden(true)
                            
                            Text(weatherCode.description)
                                .font(.title2)
                                .accessibilityLabel("Conditions: \(weatherCode.description)")
                        }
                        
                        Text(formatTemperature(weather.current.temperature2m))
                            .font(.system(size: 72, weight: .bold))
                            .accessibilityLabel("Temperature \(formatTemperature(weather.current.temperature2m))")
                        
                        if let apparentTemp = weather.current.apparentTemperature {
                            Text("Feels like \(formatTemperature(apparentTemp))")
                                .font(.title3)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding()
                    
                    // Add/Remove button
                    Button(action: toggleCity) {
                        Label(isAlreadyAdded ? "Remove from My Cities" : "Add to My Cities",
                              systemImage: isAlreadyAdded ? "minus.circle.fill" : "plus.circle.fill")
                            .font(.headline)
                            .foregroundColor(.white)
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(isAlreadyAdded ? Color.red : Color.blue)
                            .cornerRadius(10)
                    }
                    .padding(.horizontal)
                    .accessibilityLabel(isAlreadyAdded ? "Remove from My Cities" : "Add to My Cities")
                    
                    // Current conditions
                    GroupBox(label: Label("Current Conditions", systemImage: "thermometer")) {
                        VStack(spacing: 12) {
                            if let humidity = weather.current.relativeHumidity2m {
                                DetailRow(label: "Humidity", value: "\(humidity)%")
                                Divider()
                            }
                            if let windSpeed = weather.current.windSpeed10m {
                                DetailRow(label: "Wind Speed", value: formatWindSpeed(windSpeed))
                                Divider()
                            }
                            if let windDir = weather.current.windDirection10m {
                                DetailRow(label: "Wind Direction", value: formatWindDirection(windDir))
                                Divider()
                            }
                            if let pressure = weather.current.pressureMsl {
                                DetailRow(label: "Pressure", value: String(format: "%.1f hPa", pressure))
                                Divider()
                            }
                            if let visibility = weather.current.visibility {
                                DetailRow(label: "Visibility", value: formatVisibility(visibility))
                                Divider()
                            }
                            DetailRow(label: "Cloud Cover", value: "\(weather.current.cloudCover)%")
                        }
                        .padding(.vertical, 8)
                    }
                    .padding(.horizontal)
                    .accessibilityElement(children: .contain)
                    
                    // Precipitation
                    GroupBox(label: Label("Precipitation", systemImage: "cloud.rain")) {
                        VStack(spacing: 12) {
                            if let precip = weather.current.precipitation {
                                DetailRow(label: "Total", value: formatPrecipitation(precip))
                                Divider()
                            }
                            if let rain = weather.current.rain {
                                DetailRow(label: "Rain", value: formatPrecipitation(rain))
                                Divider()
                            }
                            if let showers = weather.current.showers {
                                DetailRow(label: "Showers", value: formatPrecipitation(showers))
                                Divider()
                            }
                            if let snow = weather.current.snowfall {
                                DetailRow(label: "Snowfall", value: formatPrecipitation(snow))
                            }
                        }
                        .padding(.vertical, 8)
                    }
                    .padding(.horizontal)
                    .accessibilityElement(children: .contain)
                    
                    // Daily info
                    if let daily = weather.daily {
                        GroupBox(label: Label("Today", systemImage: "calendar")) {
                            VStack(spacing: 12) {
                                if let maxTemp = daily.temperature2mMax[0] {
                                    DetailRow(label: "High", value: formatTemperature(maxTemp))
                                }
                                Divider()
                                if let minTemp = daily.temperature2mMin[0] {
                                    DetailRow(label: "Low", value: formatTemperature(minTemp))
                                }
                                Divider()
                                if let sunriseArray = daily.sunrise, let sunrise = sunriseArray[0] {
                                    DetailRow(label: "Sunrise", value: formatTime(sunrise))
                                }
                                Divider()
                                if let sunsetArray = daily.sunset, let sunset = sunsetArray[0] {
                                    DetailRow(label: "Sunset", value: formatTime(sunset))
                                }
                            }
                            .padding(.vertical, 8)
                        }
                        .padding(.horizontal)
                        .accessibilityElement(children: .contain)
                    }
                } else {
                    Text("Unable to load weather data")
                        .foregroundColor(.secondary)
                        .padding()
                }
            }
            .padding(.vertical)
        }
        .navigationTitle(cityLocation.displayName)
        .navigationBarTitleDisplayMode(.large)
        .onAppear {
            loadWeather()
        }
    }
    
    private func loadWeather() {
        isLoadingWeather = true
        Task {
            do {
                let fetchedWeather = try await weatherService.fetchWeatherFull(
                    latitude: cityLocation.latitude,
                    longitude: cityLocation.longitude
                )
                await MainActor.run {
                    weatherData = fetchedWeather
                    isLoadingWeather = false
                }
            } catch {
                await MainActor.run {
                    isLoadingWeather = false
                }
            }
        }
    }
    
    private func toggleCity() {
        if isAlreadyAdded {
            // Find and remove the city
            if let existingCity = weatherService.savedCities.first(where: { city in
                city.latitude == cityLocation.latitude && city.longitude == cityLocation.longitude
            }) {
                withAnimation {
                    weatherService.removeCity(existingCity)
                }
                UIAccessibility.post(notification: .announcement, argument: "\(cityLocation.displayName) removed from My Cities")
            }
        } else {
            let city = cityLocation.toCity()
            weatherService.addCity(city)
            UIAccessibility.post(notification: .announcement, argument: "\(cityLocation.displayName) added to My Cities")
        }
    }
    
    // Formatting helpers
    private func formatTemperature(_ celsius: Double) -> String {
        let temp = settingsManager.settings.temperatureUnit.convert(celsius)
        let unit = settingsManager.settings.temperatureUnit == .fahrenheit ? "F" : "C"
        return String(format: "%.0f°%@", temp, unit)
    }
    
    private func formatWindSpeed(_ kmh: Double) -> String {
        let speed = settingsManager.settings.windSpeedUnit.convert(kmh)
        return String(format: "%.1f %@", speed, settingsManager.settings.windSpeedUnit.rawValue)
    }
    
    private func formatWindDirection(_ degrees: Int) -> String {
        let directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        let index = Int((Double(degrees) / 45.0).rounded()) % 8
        return "\(directions[index]) (\(degrees)°)"
    }
    
    private func formatPrecipitation(_ mm: Double) -> String {
        let precip = settingsManager.settings.precipitationUnit.convert(mm)
        return String(format: "%.2f %@", precip, settingsManager.settings.precipitationUnit.rawValue)
    }
    
    private func formatVisibility(_ meters: Double) -> String {
        let km = meters / 1000.0
        let distance = settingsManager.settings.distanceUnit.convert(km)
        return settingsManager.settings.distanceUnit.format(distance, decimals: 1)
    }
    
    private func formatTime(_ isoString: String) -> String {
        guard let date = DateParser.parse(isoString) else { return isoString }
        
        let timeFormatter = DateFormatter()
        timeFormatter.timeStyle = .short
        return timeFormatter.string(from: date)
    }
}

// MARK: - Browse City Detail Destination

/// Wraps CityDetailView for browse mode, ensuring a stable City UUID for caching
/// and triggering a weather fetch when the browse city hasn't been loaded yet.
struct BrowseCityDetailDestination: View {
    @EnvironmentObject var weatherService: WeatherService
    @State private var browseCity: City

    init(cityLocation: CityLocation) {
        _browseCity = State(initialValue: cityLocation.toCity())
    }

    init(city: City) {
        _browseCity = State(initialValue: city)
    }
    
    var body: some View {
        CityDetailView(city: browseCity)
            .task {
                await weatherService.fetchWeatherForDate(for: browseCity, dateOffset: 0)
            }
    }
}

#Preview {
    let favoritesService = BrowseFavoritesService()
    StateCitiesView(state: "California", cityDataService: CityDataService(), favoritesService: favoritesService, overrideSortOrder: nil)
        .environmentObject(WeatherService())
}

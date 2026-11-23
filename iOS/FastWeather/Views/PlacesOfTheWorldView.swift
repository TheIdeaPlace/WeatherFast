//
//  PlacesOfTheWorldView.swift
//  Fast Weather
//
//  Places of the World: browse curated categories of famous places
//  (bridges, beaches, extreme-weather spots) the same way as states and countries
//

import SwiftUI

struct PlaceCategoriesListView: View {
    @ObservedObject var cityDataService: CityDataService
    @Binding var navPath: [BrowseDestination]

    var body: some View {
        List {
            if cityDataService.placeCategories.isEmpty {
                Text("Loading places...")
                    .foregroundColor(.secondary)
            } else {
                ForEach(cityDataService.placeCategories) { category in
                    Button {
                        navPath.append(.placeCategory(name: category.name, sortOrder: nil))
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(category.name)
                                .foregroundColor(.primary)
                            Text(category.description)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(category.name), \(category.places.count) places. \(category.description)")
                    .accessibilityHint("Double tap to browse \(category.name)")
                    .accessibilityAddTraits(.isButton)
                }
            }
        }
        .navigationTitle("Places of the World")
    }
}

struct PlaceCategoryView: View {
    let category: String
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

    init(category: String, cityDataService: CityDataService, favoritesService: BrowseFavoritesService, overrideSortOrder: BrowseSortOrder?) {
        self.category = category
        self.cityDataService = cityDataService
        self.favoritesService = favoritesService
        self.overrideSortOrder = overrideSortOrder
        self._sortOrder = State(initialValue: overrideSortOrder ?? .nameAZ)
    }

    private var places: [WorldPlace] {
        cityDataService.places(forCategory: category)
    }

    private var filteredPlaces: [WorldPlace] {
        let base: [WorldPlace]
        if searchText.isEmpty {
            base = places
        } else {
            // Match the name or where it is, so "Japan" or "Hawaii" finds places there
            base = places.filter {
                $0.name.localizedCaseInsensitiveContains(searchText) ||
                $0.locationLine.localizedCaseInsensitiveContains(searchText)
            }
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

    private func sortComparator(_ a: WorldPlace, _ b: WorldPlace) -> Bool {
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
            ForEach(filteredPlaces, id: \.self) { place in
                NavigationLink(destination: BrowseCityDetailDestination(city: place.toCity())) {
                    WorldPlaceRow(
                        place: place,
                        weatherData: weatherData[place.cacheKey],
                        isLoading: !hasCompletedInitialLoad
                    )
                }
            }
        }
        .navigationTitle(category)
        .searchable(text: $searchText, prompt: "Search \(category)")
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
        let isFav = favoritesService.isFavorite(name: category, regionType: .places)
        return Button {
            if isFav {
                favoritesService.remove(name: category, regionType: .places)
            } else {
                favoritesService.add(name: category, regionType: .places, sortOrder: sortOrder)
            }
        } label: {
            Image(systemName: isFav ? "star.fill" : "star")
                .foregroundColor(isFav ? .yellow : nil)
        }
        .accessibilityLabel(isFav ? "\(category), Remove from Favorites" : "\(category), Add to Favorites")
        .accessibilityHint(isFav ? "Double tap to remove this list from Browse favorites" : "Double tap to add this list to Browse favorites")
    }

    private var sortMenu: some View {
        Menu {
            Section("Alphabetical") {
                ForEach([BrowseSortOrder.nameAZ, .nameZA]) { option in
                    sortButton(option)
                }
            }
            Section("Geographic") {
                ForEach([BrowseSortOrder.northSouth, .southNorth, .eastWest, .westEast]) { option in
                    sortButton(option)
                }
            }
            Section("Temperature") {
                ForEach([BrowseSortOrder.tempHighLow, .tempLowHigh]) { option in
                    sortButton(option)
                }
            }
        } label: {
            Label("Sort", systemImage: "arrow.up.arrow.down")
        }
        .accessibilityLabel("Sort places. Current sort: \(sortOrder.rawValue)")
        .accessibilityHint("Double tap to choose how places are ordered")
    }

    private func sortButton(_ option: BrowseSortOrder) -> some View {
        Button {
            sortOrder = option
        } label: {
            Label(option.rawValue, systemImage: sortOrder == option ? "checkmark" : option.systemImage)
        }
        .accessibilityAddTraits(sortOrder == option ? .isSelected : [])
    }

    private func loadAllWeather() async {
        guard weatherData.isEmpty && !isLoadingWeather else { return }
        isLoadingWeather = true

        let locations = places.map { (latitude: $0.latitude, longitude: $0.longitude) }
        let results = await weatherService.batchFetchWeatherBasic(for: locations)

        await MainActor.run {
            weatherData = results
            isLoadingWeather = false
            hasCompletedInitialLoad = true
        }
    }
}

struct WorldPlaceRow: View {
    let place: WorldPlace
    let weatherData: WeatherData?
    let isLoading: Bool
    @EnvironmentObject var weatherService: WeatherService
    @EnvironmentObject var settingsManager: SettingsManager

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(place.name)
                .font(.body)
            Text(place.locationLine)
                .font(.caption)
                .foregroundColor(.secondary)

            if let weatherData {
                HStack(spacing: 8) {
                    if let weatherCode = weatherData.current.weatherCodeEnum {
                        Image(systemName: weatherCode.systemImageName(isDay: (weatherData.current.isDay ?? 1) == 1))
                            .foregroundColor(.blue)
                            .accessibilityHidden(true)
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
                        .accessibilityHidden(true)
                    Text("Unable to load")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            Text(place.description)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityText)
        .accessibilityHint("Double tap for the full forecast")
        .accessibilityAction(named: "Add to My Cities") {
            addPlace()
        }
    }

    // Name and weather first so a list can be scanned quickly; location and description follow
    private var accessibilityText: String {
        let weather: String
        if let weatherData {
            let temp = formatTemperature(weatherData.current.temperature2m)
            let desc = weatherData.current.weatherCodeEnum?.description ?? "unknown conditions"
            weather = "\(temp), \(desc)"
        } else if isLoading {
            weather = "loading weather"
        } else {
            weather = "unable to load weather"
        }
        return "\(place.name), \(weather), \(place.locationLine). \(place.description)"
    }

    private func addPlace() {
        let city = place.toCity()
        weatherService.addCity(city)
        UIAccessibility.post(notification: .announcement, argument: "\(place.name) added to My Cities")
    }

    private func formatTemperature(_ celsius: Double) -> String {
        let temp = settingsManager.settings.temperatureUnit.convert(celsius)
        let unit = settingsManager.settings.temperatureUnit == .fahrenheit ? "F" : "C"
        return String(format: "%.0f°%@", temp, unit)
    }
}

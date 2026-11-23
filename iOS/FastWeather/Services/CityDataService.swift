//
//  CityDataService.swift
//  Fast Weather
//
//  Service for browsing cities by state and country
//

import Foundation
import SwiftUI

class CityDataService: ObservableObject {
    @Published var usCitiesByState: [String: [CityLocation]] = [:]
    @Published var internationalCitiesByCountry: [String: [CityLocation]] = [:]
    @Published var placeCategories: [WorldPlaceCategory] = []
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    
    init() {
        loadCityData()
    }
    
    private func loadCityData() {
        // Load US cities
        if let url = Bundle.main.url(forResource: "us-cities-cached", withExtension: "json") {
            do {
                let data = try Data(contentsOf: url)
                let decoded = try JSONDecoder().decode([String: [CityLocation]].self, from: data)
                usCitiesByState = decoded

            } catch {
                debugLog("❌ Error loading US cities: \(error)")
                errorMessage = "Failed to load US cities: \(error.localizedDescription)"
            }
        } else {
            debugLog("❌ Could not find us-cities-cached.json in bundle")
            errorMessage = "Could not find US cities data file"
        }
        
        // Load international cities
        if let url = Bundle.main.url(forResource: "international-cities-cached", withExtension: "json") {
            do {
                let data = try Data(contentsOf: url)
                let decoded = try JSONDecoder().decode([String: [CityLocation]].self, from: data)
                internationalCitiesByCountry = decoded

            } catch {
                debugLog("❌ Error loading international cities: \(error)")
                errorMessage = "Failed to load international cities: \(error.localizedDescription)"
            }
        } else {
            debugLog("❌ Could not find international-cities-cached.json in bundle")
            errorMessage = "Could not find international cities data file"
        }

        // Load Places of the World
        if let url = Bundle.main.url(forResource: "places-of-the-world", withExtension: "json") {
            do {
                let data = try Data(contentsOf: url)
                placeCategories = try JSONDecoder().decode(WorldPlacesFile.self, from: data).categories
            } catch {
                debugLog("❌ Error loading places of the world: \(error)")
            }
        } else {
            debugLog("❌ Could not find places-of-the-world.json in bundle")
        }
    }
    
    var usStates: [String] {
        usCitiesByState.keys.sorted()
    }
    
    var countries: [String] {
        internationalCitiesByCountry.keys.sorted()
    }
    
    func cities(forState state: String) -> [CityLocation] {
        usCitiesByState[state] ?? []
    }
    
    func cities(forCountry country: String) -> [CityLocation] {
        internationalCitiesByCountry[country] ?? []
    }

    func places(forCategory category: String) -> [WorldPlace] {
        placeCategories.first { $0.name == category }?.places ?? []
    }
    
    /// Get all cities from all states and countries combined
    func allCities() -> [CityLocation] {
        var all: [CityLocation] = []
        for cities in usCitiesByState.values {
            all.append(contentsOf: cities)
        }
        for cities in internationalCitiesByCountry.values {
            all.append(contentsOf: cities)
        }
        return all
    }
}

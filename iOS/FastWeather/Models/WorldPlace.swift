//
//  WorldPlace.swift
//  Fast Weather
//
//  Models for Places of the World: curated categories of famous places
//  (bridges, beaches, extreme-weather spots) loaded from places-of-the-world.json
//

import Foundation

struct WorldPlacesFile: Codable {
    let categories: [WorldPlaceCategory]
}

struct WorldPlaceCategory: Codable, Hashable, Identifiable {
    let name: String
    let description: String
    let places: [WorldPlace]

    var id: String { name }
}

struct WorldPlace: Codable, Hashable {
    let name: String
    let description: String
    let city: String?
    let state: String?
    let country: String
    let latitude: Double
    let longitude: Double

    enum CodingKeys: String, CodingKey {
        case name
        case description
        case city
        case state
        case country
        case latitude = "lat"
        case longitude = "lon"
    }

    /// Where the place is, e.g. "San Francisco, California, United States" or "Antarctica"
    var locationLine: String {
        [city, state, country].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: ", ")
    }

    var cacheKey: String {
        "\(latitude),\(longitude)"
    }

    /// Saved name follows the specific-place-name convention used by search:
    /// "Golden Gate Bridge, San Francisco", or just the name when there's no nearby town.
    func toCity() -> City {
        let savedName: String
        if let city, !city.isEmpty, city != name {
            savedName = "\(name), \(city)"
        } else {
            savedName = name
        }
        return City(name: savedName, state: state, country: country, latitude: latitude, longitude: longitude)
    }
}

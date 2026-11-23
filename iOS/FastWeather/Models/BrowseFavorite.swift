//
//  BrowseFavorite.swift
//  Fast Weather
//
//  Model for a favorited browse destination (US state or international country)
//

import Foundation

enum BrowseRegionType: String, CaseIterable, Codable, Hashable {
    case us = "United States"
    case international = "International"
    case places = "Places of the World"
}

struct BrowseFavorite: Identifiable, Codable, Hashable {
    var id: UUID = UUID()
    let regionType: BrowseRegionType
    let name: String
    let sortOrder: BrowseSortOrder

    static func == (lhs: BrowseFavorite, rhs: BrowseFavorite) -> Bool {
        lhs.id == rhs.id
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
}

//
//  WorldPlaceTests.swift
//  FastWeatherTests
//
//  Places of the World: the bundled data decodes, stays within the per-category
//  limit, and places save to My Cities under the specific-place-name convention.
//

import XCTest
@testable import WeatherFast

final class WorldPlaceTests: XCTestCase {

    func testBundledPlacesDecodeAndStayWithinLimit() throws {
        let service = CityDataService()
        XCTAssertFalse(service.placeCategories.isEmpty, "places-of-the-world.json should load from the app bundle")
        for category in service.placeCategories {
            XCTAssertFalse(category.places.isEmpty, "\(category.name) has no places")
            XCTAssertLessThanOrEqual(category.places.count, 200, "\(category.name) has more than 200 places")
            for place in category.places {
                XCTAssertTrue((-90...90).contains(place.latitude), "\(place.name) latitude out of range")
                XCTAssertTrue((-180...180).contains(place.longitude), "\(place.name) longitude out of range")
            }
        }
    }

    func testPlaceDecodesOptionalCityAndState() throws {
        let json = """
        {"name": "Vostok Station", "description": "Coldest recorded temperature on Earth",
         "country": "Antarctica", "lat": -78.4645, "lon": 106.8339}
        """
        let place = try JSONDecoder().decode(WorldPlace.self, from: Data(json.utf8))
        XCTAssertNil(place.city)
        XCTAssertNil(place.state)
        XCTAssertEqual(place.locationLine, "Antarctica")
    }

    func testSavedNameIncludesNearbyCity() {
        let bridge = WorldPlace(name: "Golden Gate Bridge", description: "Suspension bridge",
                                city: "San Francisco", state: "California", country: "United States",
                                latitude: 37.8199, longitude: -122.4783)
        let city = bridge.toCity()
        XCTAssertEqual(city.name, "Golden Gate Bridge, San Francisco")
        XCTAssertEqual(city.displayName, "Golden Gate Bridge, San Francisco, California")
        XCTAssertEqual(bridge.locationLine, "San Francisco, California, United States")
    }

    func testSavedNameWithoutCityUsesPlaceName() {
        let station = WorldPlace(name: "Vostok Station", description: "Coldest recorded temperature",
                                 city: nil, state: nil, country: "Antarctica",
                                 latitude: -78.4645, longitude: 106.8339)
        XCTAssertEqual(station.toCity().name, "Vostok Station")
        XCTAssertEqual(station.toCity().displayName, "Vostok Station, Antarctica")
    }
}

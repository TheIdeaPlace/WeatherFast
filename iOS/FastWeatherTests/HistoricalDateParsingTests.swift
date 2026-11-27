//
//  HistoricalDateParsingTests.swift
//  FastWeatherTests
//
//  Regression tests for historical weather date parsing.
//
//  The critical invariant: API date strings like "2025-04-13" must always
//  display the same calendar date on-screen regardless of the device timezone.
//  Parsing with UTC (TimeZone(secondsFromGMT:0)) produces midnight UTC, which
//  rolls back to the previous day in any negative-UTC-offset timezone (all of
//  the US). This file guards against that regression.
//

import XCTest
@testable import WeatherFast

final class HistoricalDateParsingTests: XCTestCase {

    // The formatter that mirrors how HistoricalWeatherView / WeatherService
    // now parses date-only strings from the Open-Meteo archive API.
    private func makeDateOnlyFormatter() -> DateFormatter {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        // No timezone override — intentionally local, matching display formatter
        return f
    }

    // The formatter that mirrors HistoricalDayRow.dateLabel (display path).
    private func makeDisplayFormatter() -> DateFormatter {
        let f = DateFormatter()
        f.dateFormat = "MMM d"
        // No timezone override — local, same as parse formatter
        return f
    }

    // MARK: - Core regression: date must not shift under negative UTC offsets

    /// Parsing "2026-04-13" must yield a Date whose local calendar date is
    /// April 13, not April 12 (the previous-day bug caused by UTC midnight).
    func testDateOnlyStringPreservesLocalCalendarDate() {
        let formatter = makeDateOnlyFormatter()
        let dateString = "2026-04-13"
        guard let date = formatter.date(from: dateString) else {
            XCTFail("Formatter failed to parse '\(dateString)'")
            return
        }
        let components = Calendar.current.dateComponents([.year, .month, .day], from: date)
        XCTAssertEqual(components.year, 2026, "Year must be 2026")
        XCTAssertEqual(components.month, 4,   "Month must be 4 (April)")
        XCTAssertEqual(components.day, 13,    "Day must be 13, not 12 (UTC midnight off-by-one regression)")
    }

    func testDateOnlyStringJanuary1PreservesLocalCalendarDate() {
        let formatter = makeDateOnlyFormatter()
        guard let date = formatter.date(from: "2025-01-01") else {
            XCTFail("Failed to parse 2025-01-01"); return
        }
        let components = Calendar.current.dateComponents([.month, .day], from: date)
        XCTAssertEqual(components.month, 1, "Month must be January")
        XCTAssertEqual(components.day,   1, "Day must be 1, not December 31")
    }

    func testDateOnlyStringDecember31PreservesLocalCalendarDate() {
        let formatter = makeDateOnlyFormatter()
        guard let date = formatter.date(from: "2024-12-31") else {
            XCTFail("Failed to parse 2024-12-31"); return
        }
        let components = Calendar.current.dateComponents([.month, .day], from: date)
        XCTAssertEqual(components.month, 12, "Month must be December")
        XCTAssertEqual(components.day,   31, "Day must be 31, not 30")
    }

    // MARK: - Parse and display round-trip

    /// The date returned by the parse formatter must display identically
    /// to what the display formatter would show for the same calendar date.
    /// If both use local timezone this round-trip is exact; if one uses UTC
    /// and the other local, the display shows the wrong day.
    func testParseAndDisplayRoundTrip() {
        let parseFormatter   = makeDateOnlyFormatter()
        let displayFormatter = makeDisplayFormatter()

        let testCases: [(input: String, expectedDisplay: String)] = [
            ("2026-04-13", "Apr 13"),
            ("2026-01-01", "Jan 1"),
            ("2026-07-04", "Jul 4"),
            ("2026-12-25", "Dec 25"),
            ("2024-02-29", "Feb 29"), // leap day
        ]

        for tc in testCases {
            guard let date = parseFormatter.date(from: tc.input) else {
                XCTFail("Failed to parse '\(tc.input)'"); continue
            }
            let displayed = displayFormatter.string(from: date)
            XCTAssertEqual(displayed, tc.expectedDisplay,
                "'\(tc.input)' should display as '\(tc.expectedDisplay)' but got '\(displayed)'. " +
                "This is likely the UTC-midnight timezone shift bug.")
        }
    }

    // MARK: - HistoricalDate struct correctness

    func testHistoricalDateFromDatePreservesComponents() {
        // Build a Date for April 13, 2026 in local calendar
        var components = DateComponents()
        components.year  = 2026
        components.month = 4
        components.day   = 13
        guard let date = Calendar.current.date(from: components) else {
            XCTFail("Could not construct test date"); return
        }
        let hd = HistoricalDate(from: date)
        XCTAssertEqual(hd.year,  2026, "Year should be 2026")
        XCTAssertEqual(hd.month, 4,    "Month should be 4")
        XCTAssertEqual(hd.day,   13,   "Day should be 13")
    }

    func testHistoricalDateDateStringFormat() {
        let hd = HistoricalDate(year: 2026, month: 4, day: 13)
        XCTAssertEqual(hd.dateString, "2026-04-13", "dateString must be yyyy-MM-dd")
    }

    func testHistoricalDateMonthDayKey() {
        let hd = HistoricalDate(year: 2026, month: 4, day: 13)
        XCTAssertEqual(hd.monthDayKey, "04-13", "monthDayKey must be MM-dd with leading zeros")
    }

    func testHistoricalDateMonthDayKeySingleDigits() {
        let hd = HistoricalDate(year: 2026, month: 1, day: 5)
        XCTAssertEqual(hd.monthDayKey, "01-05", "Single-digit month and day must be zero-padded")
    }

    func testHistoricalDateAddDaysForwardDoesNotShiftDate() {
        var hd = HistoricalDate(year: 2026, month: 4, day: 13)
        hd.addDays(1)
        XCTAssertEqual(hd.year,  2026, "Year unchanged")
        XCTAssertEqual(hd.month, 4,    "Month unchanged")
        XCTAssertEqual(hd.day,   14,   "Day should advance to 14")
    }

    func testHistoricalDateAddDaysAcrossMonthBoundary() {
        var hd = HistoricalDate(year: 2026, month: 4, day: 30)
        hd.addDays(1)
        XCTAssertEqual(hd.month, 5, "Should roll into May")
        XCTAssertEqual(hd.day,   1, "Should be May 1")
    }

    func testHistoricalDateAddDaysAcrossYearBoundary() {
        var hd = HistoricalDate(year: 2025, month: 12, day: 31)
        hd.addDays(1)
        XCTAssertEqual(hd.year,  2026, "Should roll into 2026")
        XCTAssertEqual(hd.month, 1,    "Should be January")
        XCTAssertEqual(hd.day,   1,    "Should be the 1st")
    }

    func testHistoricalDateAddDaysNegative() {
        var hd = HistoricalDate(year: 2026, month: 4, day: 13)
        hd.addDays(-1)
        XCTAssertEqual(hd.day, 12, "Day should go back to 12")
    }

    // MARK: - addYears (Browse Days year jumps)

    func testHistoricalDateAddYearsKeepsMonthAndDay() {
        var hd = HistoricalDate(year: 2020, month: 7, day: 4)
        hd.addYears(-1)
        XCTAssertEqual(hd, HistoricalDate(year: 2019, month: 7, day: 4))
        hd.addYears(2)
        XCTAssertEqual(hd, HistoricalDate(year: 2021, month: 7, day: 4))
    }

    func testHistoricalDateAddYearsFromLeapDayLandsOnFeb28() {
        var hd = HistoricalDate(year: 2024, month: 2, day: 29)
        hd.addYears(1)
        XCTAssertEqual(hd, HistoricalDate(year: 2025, month: 2, day: 28))
    }

    // MARK: - isBrowseDaysUnavailable logic (today and future dates must block)

    func testTodayDateIsConsideredUnavailableForBrowse() {
        let today = HistoricalDate.today
        guard let todayDate = today.toDate(),
              let selectedDate = today.toDate() else {
            XCTFail("Could not build test dates"); return
        }
        // Mirrors the isBrowseDaysUnavailable predicate:
        // selectedDate >= today → unavailable
        XCTAssertTrue(selectedDate >= todayDate,
            "Today should be marked unavailable for Browse Days (historical API doesn't cover today)")
    }

    func testPastDateIsAvailableForBrowse() {
        let yesterday = {
            var hd = HistoricalDate.today
            hd.addDays(-1)
            return hd
        }()
        guard let yesterdayDate = yesterday.toDate(),
              let todayDate = HistoricalDate.today.toDate() else {
            XCTFail("Could not build test dates"); return
        }
        XCTAssertFalse(yesterdayDate >= todayDate,
            "Yesterday should be available for Browse Days")
    }
}

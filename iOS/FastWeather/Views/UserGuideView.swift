//
//  UserGuideView.swift
//  Fast Weather
//
//  User guide with comprehensive instructions for using the app
//

import SwiftUI

struct UserGuideView: View {
    @Environment(\.dismiss) private var dismiss
    
    // Get app version and build number from Info.plist
    private var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0"
    }
    
    private var buildNumber: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "1"
    }
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Welcome to Weather Fast")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    
                    Text("Your accessible, feature-rich weather companion")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .padding(.bottom, 8)
                
                // Getting Started
                GuideSection(
                    icon: "plus.circle.fill",
                    title: "Getting Started",
                    color: .green
                ) {
                    Text("Add cities to track their weather:")
                    BulletPoint("Activate the **+** (Add Location) button on the My Cities tab")
                    BulletPoint("Enter a city, ZIP code, street address, or location name")
                    BulletPoint("Select from search results")
                    BulletPoint("Or browse cities by state/country")
                }
                
                // My Cities Tab
                GuideSection(
                    icon: "list.bullet",
                    title: "My Cities Tab",
                    color: .blue
                ) {
                    Text("View and manage your saved cities:")
                    BulletPoint("**Swipe left** on a city to remove it, or use the **VoiceOver actions menu**")
                    BulletPoint("**Activate** a city to see detailed weather")
                    BulletPoint("**Pull down** to refresh all cities")
                    BulletPoint("Change view: **List** or **Flat** cards")
                    BulletPoint("A **My Location** section at the top (or bottom) shows weather for where you are right now")
                }

                // My Location
                GuideSection(
                    icon: "location.fill",
                    title: "My Location",
                    color: .accentColor
                ) {
                    Text("My Location shows live weather for wherever you are right now, updating automatically as you travel — without permanently adding a city to your list.")
                        .padding(.bottom, 4)

                    Text("**How it works:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("On first launch, Weather Fast asks for location permission")
                    BulletPoint("Your current position is reverse-geocoded to a specific place name — including neighborhood when available (e.g., \"Midtown, New York\" instead of just \"New York\")")
                    BulletPoint("Weather is fetched for your exact GPS coordinates, so the forecast reflects where you actually are")
                    BulletPoint("The location refreshes automatically when the app returns to the foreground after 15 minutes or more away")
                    BulletPoint("**Pull to refresh** also updates your location along with all saved cities")

                    Text("**Press and hold / Actions menu:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Add to My City List** — permanently saves your current location as a city")
                    BulletPoint("**Refresh My Location** — forces an immediate location update")
                    BulletPoint("**View Historical Weather** — opens historical data for your current position")

                    Text("**VoiceOver actions:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("The My Location row supports the same VoiceOver custom actions as saved cities. Open the actions rotor (swipe up or down with one finger) to find:")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    BulletPoint("**Add to My City List** — posts a confirmation announcement when added")
                    BulletPoint("**Refresh My Location** — announces \"Refreshing location\"")
                    BulletPoint("**View Historical Weather** — opens the historical weather sheet")
                    BulletPoint("**Glance Ahead** — reads out the next few hours of forecast")

                    Text("**Settings:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Control My Location in **Settings → My Location** (the first settings group):")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    BulletPoint("**Show My Location** toggle — turns the section on or off entirely")
                    BulletPoint("**Position** — choose whether My Location appears **Before City List** (default) or **After City List**")

                    Text("**If location permission is denied:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("The My Location section shows an \"Open Settings to Enable Location\" button. Tapping it takes you directly to the Location Services settings for Weather Fast.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)

                    Text("**My Location and iCloud Sync:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Your location data is always device-specific and never syncs to your other devices. If you have an iPhone in New York and an iPad in Chicago, each shows weather for where it actually is. Your iPhone will not send its New York position to your iPad.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    Text("The My Location settings (the toggle and the Before/After position) do sync — so your preference for whether the feature is on and where it appears will be consistent across devices.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)

                    Text("**Note:** My Location never appears in your saved city list unless you explicitly choose \"Add to My City List\". It will not show up in iCloud sync, widgets, or Weather in Time comparisons unless added.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.top, 4)
                        .padding(.leading, 16)
                }
                
                // Browse Cities Tab
                GuideSection(
                    icon: "map.fill",
                    title: "Browse Cities",
                    color: .purple
                ) {
                    Text("Discover weather in new locations:")
                    BulletPoint("Browse by **U.S. States** or **International** countries")
                    BulletPoint("Navigate through states/countries → cities")
                    BulletPoint("View weather without adding to your list")
                    BulletPoint("Activate the **+** (Add Location) button to add interesting locations")
                    
                    Text("**Sorting Cities:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Once inside a state or country's city list, the **sort button** (two arrows pointing up and down) in the top-right corner lets you change the order cities appear. VoiceOver announces this button as \"Sort cities. Current sort: [sort order name].\"")
                        .padding(.bottom, 4)
                    BulletPoint("**Name (A–Z)** — Default alphabetical order")
                    BulletPoint("**Name (Z–A)** — Reverse alphabetical")
                    BulletPoint("**North to South** — Cities ordered from highest to lowest latitude")
                    BulletPoint("**South to North** — Cities ordered from lowest to highest latitude")
                    BulletPoint("**East to West** — Cities ordered from highest to lowest longitude")
                    BulletPoint("**West to East** — Cities ordered from lowest to highest longitude")
                    Text("The active sort option is marked with a checkmark. Geographic sorts are useful for exploring cities along a coastline, mountain range, or river corridor. The sort resets to **Name (A–Z)** each time you open a new state or country.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.top, 4)
                }
                
                // Weather in Time
                GuideSection(
                    icon: "clock.fill",
                    title: "Weather in Time",
                    color: .mint
                ) {
                    Text("Weather in Time is aimed at answering the question about tomorrow's weather with a bit of a different approach. It will show you the conditions for all cities in your city list for the same time of day on the previous or next seven days.")
                        .padding(.bottom, 4)
                    
                    Text("**Navigating Through Dates:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**VoiceOver users:** Focus on the **date display** at the top of the screen (e.g., \"Today\"), then **swipe up for next day** or **swipe down for previous day**")
                    BulletPoint("**Alternative:** Use the **left and right arrow buttons** in the toolbar to navigate between days")
                    BulletPoint("**Scrolling cities:** Use **three-finger swipe up or down** to scroll through your city list")
                    BulletPoint("Both methods work for moving backward (earlier dates) or forward (future dates) by one day at a time")
                    
                    Text("**Return to Today:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("Activate the **Return to Today** button located at the top of the My Cities screen")
                    BulletPoint("This button appears when viewing any date other than today")
                    BulletPoint("Instantly returns all cities to current day's weather")
                    
                    Text("**Important Background Behavior:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("The app does **not** automatically revert back to today when it goes to the background. It only resets to today when you completely close and reopen the app. If the weather looks incorrect, check which day you're viewing at the top of the screen.")
                        .font(.callout)
                        .foregroundColor(.orange)
                        .padding(.leading, 16)
                        .padding(.bottom, 8)
                    
                    Text("**How It Works:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**City list shows weather for the selected date** - All cities update together when you change dates")
                    BulletPoint("**City detail view matches the selected date** - Opening a city shows details for the day you're viewing")
                    BulletPoint("**Date range:** 7 days in the past to 7 days in the future")
                    BulletPoint("**Same time each day** - See consistent comparisons across dates")
                }
                
                // Marine Forecast
                GuideSection(
                    icon: "water.waves",
                    title: "Marine Forecast",
                    color: .teal
                ) {
                    Text("View tidal and marine conditions for coastal cities over the next 24 hours. This feature is useful for planning beach trips, boating, surfing, or understanding coastal weather patterns.")
                        .padding(.bottom, 4)
                    
                    Text("**What's Included:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Sea Level Height** - Tidal information showing water level changes throughout the day")
                    BulletPoint("**Wave Height** - Current and forecasted wave conditions")
                    BulletPoint("**Wave Direction** - Direction waves are coming from")
                    BulletPoint("**Wave Period** - Time between wave crests")
                    BulletPoint("**Sea Surface Temperature** - Current water temperature")
                    BulletPoint("**Swell Wave Height** - Long-period wave conditions")
                    BulletPoint("**Ocean Current Velocity** - Speed of ocean currents")
                    BulletPoint("Additional detailed metrics available in settings")
                    
                    Text("**Accessing Marine Forecast:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("Open any city's detail view")
                    BulletPoint("Scroll to the **Marine Forecast** section")
                    BulletPoint("Section appears when enabled in Settings → Detail Categories")
                    BulletPoint("Displays 24-hour forecast starting from current time")
                    
                    Text("**Customization:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("Go to Settings → Marine Forecast to customize which marine fields are displayed")
                    BulletPoint("Reorder marine fields by dragging")
                    BulletPoint("Enable/disable individual data points based on your needs")
                    BulletPoint("Marine Forecast can be hidden entirely in Settings → Detail Categories")
                    
                    Text("**Note:** Marine forecast data is available for coastal locations. Inland cities may show limited or no marine data. Sea Level Height (tidal data) is enabled by default and shown first in the marine section.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.top, 8)
                        .padding(.leading, 16)
                }
                
                // City Detail View
                GuideSection(
                    icon: "info.circle.fill",
                    title: "City Detail View",
                    color: .orange
                ) {
                    Text("Explore comprehensive weather information:")
                    BulletPoint("**Current conditions** with temperature, humidity, wind")
                    BulletPoint("**Hourly forecast** for next 24 hours")
                    BulletPoint("**Daily forecast** for 16 days")
                    BulletPoint("**Marine forecast** for coastal locations (if enabled)")
                    BulletPoint("**Actions menu** for historical data and more")
                    BulletPoint("**Weather alerts** when active (U.S. and select international locations)")
                    
                    Text("**Weather in Time Integration:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("All weather details in this view are based on the date you've selected using Weather in Time. If you're viewing tomorrow's weather in your city list, opening a city's detail view will show tomorrow's forecast, not today's.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                }
                
                // Actions Menu
                GuideSection(
                    icon: "ellipsis.circle.fill",
                    title: "Actions Menu",
                    color: .indigo
                ) {
                    Text("Access additional features from city detail:")
                    BulletPoint("**Refresh** - Update weather data")
                    BulletPoint("**View Historical Weather** - See past weather data")
                    BulletPoint("**Expected Precipitation** - Rainfall forecast (if enabled)")
                    BulletPoint("**Weather Around Me** - Regional weather comparison (if enabled)")
                    BulletPoint("**Remove City** - Delete from your list")
                }
                
                // Weather Around Me & Directional Explorer
                GuideSection(
                    icon: "location.circle.fill",
                    title: "Weather Around Me",
                    color: .purple
                ) {
                    Text("See weather in cities around you in all directions. This feature helps you understand regional weather patterns, track severe weather systems, and build an accurate mental map of conditions in your area.")
                        .padding(.bottom, 4)
                    
                    Text("**What You'll See:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Regional Overview** - Weather in 8 directions (N, NE, E, SE, S, SW, W, NW)")
                    BulletPoint("**Distance** - How far each city is from your selected city")
                    BulletPoint("**Spatial Precision** - How far cities are from the center line (e.g., \"5 miles west of center line\")")
                    BulletPoint("**Current Weather** - Temperature and conditions for each city")
                    BulletPoint("**Weather Movement** - Whether weather systems are approaching, moving away, or moving parallel")
                    
                    Text("**Exploring Along a Direction:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Tap any direction to explore cities along that path. For example, tap \"North\" to see all cities north of your location.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    BulletPoint("**Pick a Direction** - Choose N, NE, E, SE, S, SW, W, or NW from the picker")
                    BulletPoint("**Navigate Cities** - Swipe up for cities farther away, swipe down for closer cities")
                    BulletPoint("**Visual Buttons** - Use \"Closer\" and \"Farther\" buttons to move between cities")
                    BulletPoint("**View All** - Tap \"List All\" to see all cities in that direction at once")
                    
                    Text("**Understanding Spatial Information:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("VoiceOver can announce detailed spatial information to help you build an accurate mental map:")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    BulletPoint("**Distance from Center Line** - How far cities are offset east or west (e.g., \"5 miles west of center line\")")
                    BulletPoint("**Bearing** - Compass direction in degrees (e.g., \"145 degrees\")")
                    BulletPoint("**\"On center line\"** - City is directly along your chosen direction")
                    BulletPoint("**Example:** \"Janesville, 32 miles, 145 degrees, 25 miles east of center line\" tells you distance, bearing, and offset")
                    
                    Text("**Exploration Modes:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Choose between two exploration modes in Settings → Weather Around Me:")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    BulletPoint("**Arc Mode** (default) - Fan-shaped search that expands outward like a cone. Cities within the arc width are included")
                    BulletPoint("**Straight Line Corridor** - Fixed-width corridor along the center line. Cities within the corridor width are included regardless of distance")
                    
                    Text("**Arc Widths** (when using Arc mode):")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Narrow (10°)** - Precise tracking, 17 miles wide at 100 miles")
                    BulletPoint("**Standard (22.5°)** - Balanced coverage, 39 miles wide at 100 miles")
                    BulletPoint("**Medium (45°)** - Broad search, 78 miles wide at 100 miles")
                    BulletPoint("**Wide (90°)** - Maximum coverage, 141 miles wide at 100 miles")
                    
                    Text("**Arc Width at Different Distances:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("The arc expands as you go farther from your starting city. Here's how wide each arc setting is at different distances:")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 12) {
                            Text("Distance")
                                .fontWeight(.semibold)
                                .frame(width: 70, alignment: .leading)
                            Text("Narrow")
                                .fontWeight(.semibold)
                                .frame(width: 60, alignment: .trailing)
                            Text("Standard")
                                .fontWeight(.semibold)
                                .frame(width: 70, alignment: .trailing)
                            Text("Medium")
                                .fontWeight(.semibold)
                                .frame(width: 70, alignment: .trailing)
                            Text("Wide")
                                .fontWeight(.semibold)
                                .frame(width: 70, alignment: .trailing)
                        }
                        .font(.caption)
                        .padding(.bottom, 4)
                        
                        Divider()
                        
                        HStack(spacing: 12) {
                            Text("50 mi")
                                .frame(width: 70, alignment: .leading)
                            Text("9 mi")
                                .frame(width: 60, alignment: .trailing)
                            Text("20 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("38 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("71 mi")
                                .frame(width: 70, alignment: .trailing)
                        }
                        .font(.caption)
                        
                        HStack(spacing: 12) {
                            Text("100 mi")
                                .frame(width: 70, alignment: .leading)
                            Text("17 mi")
                                .frame(width: 60, alignment: .trailing)
                            Text("39 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("77 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("141 mi")
                                .frame(width: 70, alignment: .trailing)
                        }
                        .font(.caption)
                        
                        HStack(spacing: 12) {
                            Text("150 mi")
                                .frame(width: 70, alignment: .leading)
                            Text("26 mi")
                                .frame(width: 60, alignment: .trailing)
                            Text("59 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("115 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("212 mi")
                                .frame(width: 70, alignment: .trailing)
                        }
                        .font(.caption)
                        
                        HStack(spacing: 12) {
                            Text("200 mi")
                                .frame(width: 70, alignment: .leading)
                            Text("35 mi")
                                .frame(width: 60, alignment: .trailing)
                            Text("78 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("153 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("283 mi")
                                .frame(width: 70, alignment: .trailing)
                        }
                        .font(.caption)
                        
                        HStack(spacing: 12) {
                            Text("250 mi")
                                .frame(width: 70, alignment: .leading)
                            Text("44 mi")
                                .frame(width: 60, alignment: .trailing)
                            Text("98 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("191 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("354 mi")
                                .frame(width: 70, alignment: .trailing)
                        }
                        .font(.caption)
                        
                        HStack(spacing: 12) {
                            Text("300 mi")
                                .frame(width: 70, alignment: .leading)
                            Text("52 mi")
                                .frame(width: 60, alignment: .trailing)
                            Text("117 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("230 mi")
                                .frame(width: 70, alignment: .trailing)
                            Text("424 mi")
                                .frame(width: 70, alignment: .trailing)
                        }
                        .font(.caption)
                    }
                    .padding(.leading, 16)
                    .padding(.trailing, 16)
                    .padding(.top, 4)
                    .padding(.bottom, 8)
                    
                    Text("For example, using Standard arc at 150 miles means cities must be within a 59-mile-wide fan shape at that distance to appear in your search.")
                        .font(.callout)
                        .italic()
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    Text("**Corridor Widths** (when using Straight Line Corridor mode):")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**10 miles** - ±5 miles from center line")
                    BulletPoint("**20 miles** - ±10 miles from center line (default)")
                    BulletPoint("**30 miles** - ±15 miles from center line")
                    BulletPoint("**50 miles** - ±25 miles from center line")
                    
                    Text("**Weather Movement Detection:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("When \"Show Weather Movement\" is enabled in settings, VoiceOver announces wind speed and whether weather systems are moving toward or away from your location. This uses wind direction data to analyze movement patterns.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    BulletPoint("**\"Winds X mph\"** - Current wind speed when movement is minimal")
                    BulletPoint("**\"Approaching at X mph\"** - Weather is moving toward your location")
                    BulletPoint("**\"Moving away at X mph\"** - Weather is moving away from you")
                    BulletPoint("**\"Moving parallel at X mph\"** - Weather is moving perpendicular to your direction")
                    
                    Text("**Example VoiceOver Announcements:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("\"Milwaukee, Wisconsin, 80 miles, 5 degrees, 3 miles east of center line, 72°F, Overcast, Alert: Tornado Warning, Approaching at 15 mph, Pressure steady, 2 of 15\"")
                        .font(.callout)
                        .italic()
                        .foregroundColor(.blue)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    Text("With all settings enabled, you hear: city name, distance, bearing, offset from center line, temperature, conditions, weather alerts, wind movement, pressure trends, and position in list.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    Text("\"Oregon, Wisconsin, 10 miles, 180 degrees, On center line, 65°F, Clear, Winds 3 mph, 1 of 8\"")
                        .font(.callout)
                        .italic()
                        .foregroundColor(.blue)
                        .padding(.leading, 16)
                        .padding(.bottom, 8)
                    
                    Text("**Configuring Weather Around Me:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Access settings two ways: tap the gear icon in Weather Around Me, or go to Settings → Weather Around Me.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    BulletPoint("**Default Distance** - How far to search (25-250 miles)")
                    BulletPoint("**Exploration Mode** - Arc or Straight Line Corridor")
                    BulletPoint("**Arc Width** or **Corridor Width** - Adjust based on your chosen mode")
                    BulletPoint("**Show Distance from Center Line** - Toggle offset distance announcements (uses miles/kilometers)")
                    BulletPoint("**Show Bearing** - Toggle compass bearing announcements (e.g., \"145 degrees\")")
                    BulletPoint("**Show Weather Movement** - Toggle wind speed and movement direction")
                    BulletPoint("**Show Pressure Trends** - Toggle pressure comparisons between consecutive cities")
                    BulletPoint("**Show Weather Alerts** - Toggle severe weather alert announcements")
                    
                    Text("**VoiceOver Quick Cycle:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("For experienced VoiceOver users, you can rapidly cycle through exploration modes without opening settings. Focus on the gear icon button and swipe up or down to cycle through all mode combinations.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    BulletPoint("**Swipe Up** - Cycle forward: Corridor 10→20→30→50 miles, then Arc Narrow→Standard→Medium→Wide")
                    BulletPoint("**Swipe Down** - Cycle backward through the same sequence")
                    BulletPoint("**Instant Feedback** - VoiceOver announces the new mode and cities reload automatically")
                    BulletPoint("**Example:** Quickly test different arc widths to see which captures the cities you want")
                    
                    Text("**First Time Loading:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Finding cities along a direction may take 10-20 seconds the first time, but results are cached for instant access next time. The app searches every 10-15 miles along your chosen direction to find nearby cities.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    
                    Text("**Tips:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("Use **Narrow Arc** or **10-mile Corridor** for precise tracking of severe weather along highways")
                    BulletPoint("Use **Wide Arc** or **50-mile Corridor** to get a broader overview of regional conditions")
                    BulletPoint("**Offset distance** helps you determine if a city is directly in the path of a weather system")
                    BulletPoint("**Weather movement** helps you anticipate if storms are heading your way")
                    BulletPoint("Use VoiceOver swipe gestures to quickly explore city by city")
                    BulletPoint("Weather data is prefetched as you navigate for smooth scrolling")
                }
                
                // Historical Weather
                GuideSection(
                    icon: "clock.arrow.circlepath",
                    title: "Historical Weather",
                    color: .brown
                ) {
                    Text("Explore weather from the past:")
                    BulletPoint("**Single Day** - View specific date's weather")
                    BulletPoint("**History** - Compare the same date across years")
                    BulletPoint("**Browse Days** - 30 days in a row; Previous Year and Next Year show the same days in another year")
                    BulletPoint("Data available back to 1940 for most locations")
                }
                
                // Settings
                GuideSection(
                    icon: "gearshape.fill",
                    title: "Settings",
                    color: .gray
                ) {
                    Text("Customize your experience:")
                    BulletPoint("**My Location** - Toggle on/off and choose position (Before or After city list)")
                    BulletPoint("**Units** - °F/°C, mph/km/h/m/s, inches/mm, hPa/inHg/mmHg")
                    BulletPoint("**View Mode** - List or Flat cards")
                    BulletPoint("**Display Mode** - Condensed or Expanded")
                    BulletPoint("**Weather Fields** - Show/hide and reorder")
                    BulletPoint("**Detail Categories** - Customize detail view")
                }
                
                // iCloud Sync
                GuideSection(
                    icon: "icloud.fill",
                    title: "iCloud Sync",
                    color: .blue
                ) {
                    Text("iCloud Sync keeps your saved cities and settings in step across all your iPhones and iPads signed in to the same Apple ID. It's opt-in — nothing moves until you turn it on.")
                        .padding(.bottom, 4)

                    Text("**What syncs:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("All saved cities in your My Cities list")
                    BulletPoint("All settings — units, view mode, display fields, detail categories, and every toggle in Settings")
                    BulletPoint("Weather Around Me preferences")
                    BulletPoint("My Data custom fields")

                    Text("**What doesn't sync:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("Feature flags and Developer Settings — these stay local to each device")
                    BulletPoint("The iCloud Sync toggle itself — you turn it on per device")
                    BulletPoint("Cached weather data — each device fetches its own fresh data")
                    BulletPoint("My Location position data — each device independently detects where it is, so your iPhone in New York and your iPad in Chicago each show their own location")

                    Text("**Turning sync on for the first time:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Go to **Settings → iCloud → Sync with iCloud** and flip the toggle. What happens depends on the state of each side:")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    BulletPoint("**iCloud is empty** — your local cities and settings are uploaded. The toggle turns on immediately.")
                    BulletPoint("**iCloud has data, your device has no cities** — iCloud's data is downloaded silently. The toggle turns on immediately.")
                    BulletPoint("**Both sides have cities** — a dialog appears asking you to choose before the toggle turns on.")

                    Text("**When both sides have cities — the conflict dialog:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("If iCloud already has a city list and this device also has one, the toggle stays off and you're asked to choose:")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    BulletPoint("**Use iCloud List** — downloads iCloud's cities and settings onto this device, then turns sync on")
                    BulletPoint("**Keep My List** — uploads this device's cities and settings to iCloud, then turns sync on")
                    BulletPoint("**Don't Sync** — leaves the toggle off and both lists completely unchanged")
                    Text("You will never lose a city list without explicitly choosing to.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.top, 4)
                        .padding(.bottom, 4)

                    VStack(alignment: .leading, spacing: 8) {
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.orange)
                                .accessibilityHidden(true)
                            Text("**Tip: Enable sync on your most complete device first**")
                                .fontWeight(.semibold)
                        }
                        Text("If you enable sync on your iPhone (20 cities) before your iPad (2 cities), the iPhone's list uploads first. When you then enable on the iPad, iCloud already has data so the conflict dialog appears — and you can choose the iPhone's list. Enabling on the iPad first still works, you'll just see the dialog and choose accordingly.")
                            .font(.callout)
                    }
                    .foregroundColor(.primary)
                    .padding(12)
                    .background(Color.orange.opacity(0.12))
                    .cornerRadius(8)
                    .padding(.top, 8)
                    .accessibilityElement(children: .combine)

                    Text("**Ongoing sync — last change wins:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Once sync is running on both devices, changes flow automatically whenever the app comes to the foreground. If you change a setting on your iPhone, it shows up on your iPad the next time you open Weather Fast there. If you make conflicting changes on two devices before either one syncs, the last one to come online wins.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)

                    Text("**Resetting settings or clearing all cities:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("These are deliberate actions, so they propagate. If you tap \"Reset Settings to Defaults\" or \"Clear All Cities\" while sync is on, those changes sync to your other devices. If you only want to reset one device, turn sync off first, make the change, then decide whether to turn sync back on.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)

                    Text("**Turning sync off:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Flip the toggle back off in Settings → iCloud. Your local data stays exactly as it is — nothing is deleted. iCloud retains a copy of the last synced state, but this device will no longer push or pull changes. Your other devices continue syncing with each other if their toggles remain on.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                }

                // Widgets
                GuideSection(
                    icon: "square.grid.2x2.fill",
                    title: "Home Screen & Lock Screen Widgets",
                    color: .blue
                ) {
                    Text("Weather Fast widgets give you a quick look at conditions without opening the app. Each placed widget is independent, so you can show a different city on each one.")
                        .padding(.bottom, 4)

                    Text("**Available sizes:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Small** — City name, condition icon, current temperature, and today's high/low")
                    BulletPoint("**Medium** — Adds precipitation probability alongside the current conditions")
                    BulletPoint("**Large** — Full current conditions at the top, plus a 5-day forecast below")
                    BulletPoint("**Lock screen circular** — Condition icon and temperature in a compact badge")
                    BulletPoint("**Lock screen rectangular** — City, condition icon, temperature, and high/low in a single bar")

                    Text("**Adding a home screen widget:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("Long-press any empty area of the home screen to enter edit mode")
                    BulletPoint("Tap the **+** button in the top-left corner to open the widget gallery")
                    BulletPoint("Search for **Weather Fast** or scroll to find it")
                    BulletPoint("Swipe through the size options to choose small, medium, or large")
                    BulletPoint("Tap **Add Widget**, then drag it to the position you want")

                    Text("**Adding a lock screen widget:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("Long-press the lock screen and tap **Customize**")
                    BulletPoint("Tap the lock screen face, then tap a widget slot")
                    BulletPoint("Select **Weather Fast** from the widget list")
                    BulletPoint("The circular badge fits the small round slot; the bar fits the wider rectangular slot")

                    Text("**Choosing which city to show:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Widgets default to the first city in your list. To change it:")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    BulletPoint("Long-press the widget and tap **Edit Widget**")
                    BulletPoint("Tap the **City** row to open the picker")
                    BulletPoint("Select any city from your saved cities list")
                    BulletPoint("Placing multiple widgets lets you track several cities at a glance simultaneously")

                    Text("**Update frequency:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Widgets refresh approximately every 30 minutes. iOS adjusts the exact timing based on battery and how often you check a given widget — one you glance at frequently updates more reliably than one you rarely visit.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)

                    Text("**What VoiceOver reads:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Each widget is announced as a single element. The label includes everything you need without having to open the app:")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    BulletPoint("**Small and lock screen:** \"[City], [temperature], [condition], High [H], Low [L]\"")
                    BulletPoint("**Medium:** adds the precipitation percentage at the end")
                    BulletPoint("**Large:** adds each forecast day — \"[Day]: H [high] L [low]\" — after the current conditions summary")
                    BulletPoint("Precipitation probability for a forecast day is included when it is 20% or higher")

                    Text("**Adding or editing a widget with VoiceOver:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Focus on any empty home screen area and open the VoiceOver actions menu (swipe up or down with one finger until you hear the action you want). Choose **Edit Home Screen**, then navigate to the **+** button to open the widget gallery. To edit a widget you've already placed, focus on it and open the actions menu — **Edit Widget** appears as an option there.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)

                    Text("**If the widget shows \"--°\" or a warning triangle:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("A network error occurred during the last refresh — the widget retries automatically on the next update cycle")
                    BulletPoint("If it persists, open the app and confirm your internet connection, then wait for the next cycle")

                    Text("**If the widget shows \"Add a city in the app\":**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("Open Weather Fast and add at least one city — the widget populates on the next refresh")
                }

                // Icons & Graphics
                GuideSection(
                    icon: "photo.fill",
                    title: "Icons & Graphics",
                    color: .pink
                ) {
                    Text("Visual icons used throughout the app with VoiceOver equivalents:")
                    
                    Text("**App Icon:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("The Weather Fast app icon features a large \"WF\" monogram in white against a bright blue sky background, with decorative white clouds surrounding the text. The sunny atmosphere conveys clear, accessible weather information.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                    Text("VoiceOver: \"Weather Fast\"")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 8)
                    
                    Text("**Tab Bar Icons:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**List icon** - My Cities tab (VoiceOver: \"My Cities\")")
                    BulletPoint("**Magnifying glass** - Browse tab (VoiceOver: \"Browse Cities\")")
                    BulletPoint("**Gear** - Settings tab (VoiceOver: \"Settings\")")
                    
                    Text("**Weather Condition Icons:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    
                    // Clear / Mainly clear
                    HStack(alignment: .top, spacing: 12) {
                        HStack(spacing: 4) {
                            Image(systemName: "sun.max.fill")
                                .font(.title2)
                                .foregroundColor(.yellow)
                                .accessibilityHidden(true)
                            Image(systemName: "moon.stars.fill")
                                .font(.title2)
                                .foregroundColor(.indigo)
                                .accessibilityHidden(true)
                        }
                        .frame(width: 64)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Clear sky / Mainly clear")
                                .fontWeight(.semibold)
                            Text("Sun during the day; moon with stars at night")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("VoiceOver: \"Clear sky\" or \"Mainly clear\"")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Partly cloudy
                    HStack(alignment: .top, spacing: 12) {
                        HStack(spacing: 4) {
                            Image(systemName: "cloud.sun.fill")
                                .font(.title2)
                                .foregroundColor(.orange)
                                .accessibilityHidden(true)
                            Image(systemName: "cloud.moon.fill")
                                .font(.title2)
                                .foregroundColor(.indigo)
                                .accessibilityHidden(true)
                        }
                        .frame(width: 64)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Partly cloudy")
                                .fontWeight(.semibold)
                            Text("Cloud with sun during the day; cloud with moon at night")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("VoiceOver: \"Partly cloudy\"")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Overcast
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "cloud.fill")
                            .font(.title2)
                            .foregroundColor(.gray)
                            .frame(width: 32)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Overcast")
                                .fontWeight(.semibold)
                            Text("VoiceOver: \"Overcast\"")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Fog / Rime fog
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "cloud.fog.fill")
                            .font(.title2)
                            .foregroundColor(.gray)
                            .frame(width: 32)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Fog / Depositing rime fog")
                                .fontWeight(.semibold)
                            Text("VoiceOver: \"Fog\" or \"Depositing rime fog\"")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Drizzle
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "cloud.drizzle.fill")
                            .font(.title2)
                            .foregroundColor(.blue)
                            .frame(width: 32)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Light / Moderate / Dense drizzle")
                                .fontWeight(.semibold)
                            Text("VoiceOver: \"Light drizzle\", \"Moderate drizzle\", or \"Dense drizzle\"")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Freezing drizzle / Freezing rain
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "cloud.sleet.fill")
                            .font(.title2)
                            .foregroundColor(.cyan)
                            .frame(width: 32)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Freezing drizzle / Freezing rain")
                                .fontWeight(.semibold)
                            Text("VoiceOver: \"Light freezing drizzle\", \"Dense freezing drizzle\", \"Light freezing rain\", or \"Heavy freezing rain\"")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Rain
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "cloud.rain.fill")
                            .font(.title2)
                            .foregroundColor(.blue)
                            .frame(width: 32)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Slight / Moderate / Heavy rain")
                                .fontWeight(.semibold)
                            Text("VoiceOver: \"Slight rain\", \"Moderate rain\", or \"Heavy rain\"")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Snow fall / Snow grains / Snow showers
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "cloud.snow.fill")
                            .font(.title2)
                            .foregroundColor(.cyan)
                            .frame(width: 32)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Snow fall / Snow grains / Snow showers")
                                .fontWeight(.semibold)
                            Text("VoiceOver: \"Slight snow fall\", \"Moderate snow fall\", \"Heavy snow fall\", \"Snow grains\", \"Slight snow showers\", or \"Heavy snow showers\"")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Rain showers
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "cloud.heavyrain.fill")
                            .font(.title2)
                            .foregroundColor(.indigo)
                            .frame(width: 32)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Slight / Moderate / Violent rain showers")
                                .fontWeight(.semibold)
                            Text("VoiceOver: \"Slight rain showers\", \"Moderate rain showers\", or \"Violent rain showers\"")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    // Thunderstorm
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "cloud.bolt.rain.fill")
                            .font(.title2)
                            .foregroundColor(.purple)
                            .frame(width: 32)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Thunderstorm / Thunderstorm with hail")
                                .fontWeight(.semibold)
                            Text("VoiceOver: \"Thunderstorm\", \"Thunderstorm with slight hail\", or \"Thunderstorm with heavy hail\"")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    Text("VoiceOver announces the exact weather condition by name.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                    
                    Text("**Weather Alert Icons:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Filled warning triangle** - Extreme/Severe/Moderate alerts (red/orange/yellow)")
                    BulletPoint("**Filled circle with exclamation** - Minor alerts (blue)")
                    BulletPoint("**Circle with exclamation** - Unknown severity (gray)")
                    Text("VoiceOver announces: \"Weather alert: [event name]\" with severity level")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                    
                    Text("**Action & Navigation Icons:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Filled location pin** - My Location section header and row badge (VoiceOver: hidden, context provided by section label \"My Location\")")
                    BulletPoint("**Plus circle** - Add location (VoiceOver: \"Add Location\")")
                    BulletPoint("**Circular arrows** - Refresh (VoiceOver: \"Refresh\" or \"Refresh weather\")")
                    BulletPoint("**Three dots circle** - Actions menu (VoiceOver: \"Actions\")")
                    BulletPoint("**Chevron right** - Navigate forward (VoiceOver: included in item name)")
                    BulletPoint("**Chevron down** - Expand menu (VoiceOver: \"[State/Country name]\")")
                    BulletPoint("**Map pin** - Location/browse (VoiceOver: \"Browse by state or country\")")
                    BulletPoint("**Book** - User guide (VoiceOver: \"User Guide\")")
                    BulletPoint("**Hammer** - Developer settings (VoiceOver: \"Developer Settings\")")
                    BulletPoint("**Left arrow** - Previous day in Weather in Time (VoiceOver: \"Previous\")")
                    BulletPoint("**Right arrow** - Next day in Weather in Time (VoiceOver: \"Next\")")
                    BulletPoint("**Calendar with clock badge** - Return to Today button (VoiceOver: \"Today\")")
                    
                    Text("**Data Visualization Icons:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Droplet** - Precipitation amount (VoiceOver: \"Precipitation: [amount]\")")
                    BulletPoint("**Up arrow** - High temperature (VoiceOver: \"High: [temperature]\")")
                    BulletPoint("**Down arrow** - Low temperature (VoiceOver: \"Low: [temperature]\")")
                    BulletPoint("**Compass arrows** - Wind direction (VoiceOver: \"Wind from [direction]\")")
                    BulletPoint("**Clock** - Time/timestamp (VoiceOver: formatted time)")
                    BulletPoint("**Calendar with clock** - Historical weather (VoiceOver: \"View historical weather\")")
                    BulletPoint("**Water waves** - Marine Forecast section (VoiceOver: \"Marine Forecast\")")
                    
                    Text("**Status Icons:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Warning triangle** - Error or unavailable (VoiceOver: describes issue)")
                    BulletPoint("**Checkmark** - Selected item (VoiceOver: \"Selected\")")
                    BulletPoint("**Two arrows up and down** - Browse Cities sort button (VoiceOver: \"Sort cities. Current sort: [sort order name]\")")

                    Text("**Decorative Illustrations:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("These large gray illustrations appear on the Browse Cities tab when no state or country has been selected yet. They are purely decorative and are hidden from VoiceOver — the text prompt beside them conveys the same meaning.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                        .padding(.bottom, 4)
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "map")
                            .font(.title2)
                            .foregroundColor(.secondary)
                            .frame(width: 32)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Tri-fold paper map (U.S. States tab)")
                                .fontWeight(.semibold)
                            Text("A stylized folded road map outline with two vertical crease lines. Appears alongside \"Select a state to view cities\". Hidden from VoiceOver.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "globe")
                            .font(.title2)
                            .foregroundColor(.secondary)
                            .frame(width: 32)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Globe (International tab)")
                                .fontWeight(.semibold)
                            Text("A sphere with horizontal and curved longitude lines suggesting the Earth. Appears alongside \"Select a country to view cities\". Hidden from VoiceOver.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    
                    Text("**Important:** All icons are decorative only. VoiceOver users receive full information through text labels and announcements. You never need to see icons to use the app.")
                        .font(.callout)
                        .foregroundColor(.orange)
                        .padding(.top, 8)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 12)
                        .background(Color.orange.opacity(0.1))
                        .cornerRadius(8)
                    
                    Text("**Expected Precipitation Timeline:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("The Expected Precipitation feature displays a visual timeline showing precipitation forecasts for each time interval. This timeline is visible on screen for sighted users but is hidden from VoiceOver. The same data is available through the audio graph below the timeline, which provides both audio tones (representing precipitation intensity) and individual data points you can explore by swiping. The audio graph format is more efficient for non-visual exploration than reading through a long list of time entries.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                }
                
                // Accessibility
                GuideSection(
                    icon: "accessibility",
                    title: "Accessibility",
                    color: .teal
                ) {
                    Text("Weather Fast is designed for VoiceOver users:")
                    BulletPoint("**Complete VoiceOver support** - All features accessible")
                    BulletPoint("**Descriptive labels** - Clear, context-aware announcements")
                    BulletPoint("**Logical navigation** - Efficient screen reader flow")
                    BulletPoint("**Dynamic Type** - Text scales with system settings")
                    BulletPoint("**High contrast** - Readable in all conditions")
                }
                
                // Keyboard Shortcuts
                GuideSection(
                    icon: "command",
                    title: "Keyboard Shortcuts",
                    color: .green
                ) {
                    Text("Use external keyboard shortcuts for faster navigation (iPad with keyboard):")
                    
                    Text("**General:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**⌘⇧N** - Add new city")
                    
                    Text("More keyboard shortcuts will be added in future updates.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.top, 4)
                }
                
                // Tips & Tricks
                GuideSection(
                    icon: "lightbulb.fill",
                    title: "Tips & Tricks",
                    color: .yellow
                ) {
                    BulletPoint("**Reorder weather fields** in Settings → Weather Fields")
                    BulletPoint("**Drag to reorder** detail categories in Settings")
                    BulletPoint("**Activate** a city in browse to view without adding")
                    BulletPoint("**Pull to refresh** works on all city lists")
                    BulletPoint("**Swipe actions** or **VoiceOver actions menu** available in List view")
                    BulletPoint("**Historical years** can be configured in Settings")
                    BulletPoint("**Place multiple widgets** — one per city — to compare conditions at a glance without opening the app")
                }
                
                // Data Sources
                GuideSection(
                    icon: "cloud.sun.fill",
                    title: "Weather Data",
                    color: .cyan
                ) {
                    Text("Weather Fast uses reliable, free data sources:")
                    BulletPoint("**Open-Meteo** - Current and forecast weather")
                    BulletPoint("**Historical Archive** - Weather back to 1940")
                    BulletPoint("**NWS Alerts** - U.S. weather warnings (when available)")
                    BulletPoint("**OpenStreetMap** - City geocoding")
                    Text("No API keys required. No data tracking.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.top, 4)
                }
                
                // Footer
                VStack(spacing: 12) {
                    Divider()
                    
                    Text("Need more help?")
                        .font(.headline)
                    
                    Text("Weather Fast is designed to be intuitive. Explore the app and discover features as you use it. Most actions are available through standard iOS gestures and VoiceOver commands.")
                        .font(.body)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    
                    Text("Version \(appVersion) (build \(buildNumber))")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .accessibilityLabel("Version \(appVersion) build \(buildNumber)")
                }
                .padding(.top, 24)
                .padding(.bottom, 40)
            }
            .padding()
        }
        .navigationTitle("User Guide")
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Supporting Views

struct GuideSection<Content: View>: View {
    let icon: String
    let title: String
    let color: Color
    @ViewBuilder let content: Content
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundColor(color)
                    .accessibilityHidden(true)
                
                Text(title)
                    .font(.title3)
                    .fontWeight(.semibold)
            }
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.isHeader)
            
            VStack(alignment: .leading, spacing: 8) {
                content
            }
            .font(.body)
        }
        .padding()
        .background(Color(uiColor: .secondarySystemGroupedBackground))
        .cornerRadius(12)
    }
}

struct BulletPoint: View {
    let text: LocalizedStringKey
    
    init(_ text: LocalizedStringKey) {
        self.text = text
    }
    
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text("•")
                .foregroundColor(.accentColor)
                .accessibilityHidden(true)
            Text(text)
        }
    }
}

#Preview {
    NavigationView {
        UserGuideView()
    }
}

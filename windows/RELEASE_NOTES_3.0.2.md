WeatherFast 3.0.2 for Windows is a bug-fix release. It updates 3.0.1, and WeatherFast offers it to you the next time it starts.

## Fixed

### The city list

- After you opened Full Weather and came back, a city's high and low were a week old. The list now always shows today's.
- Removing a city no longer leaves the other cities saying "Loading...". After you remove one, you stay at the same place in the list.
- The word for the sky in the list now matches the Condition line in Full Weather, so the list can't say "mostly cloudy" while the report says "Mainly clear".
- If a city's weather can't be fetched, its line says so and suggests F5, instead of saying "Loading..." for good.
- After you add a city from Search Results, you land on it in the list.
- Searching for a city that's already in your list tells you so.
- Delete removes a city only from the list. It used to take Delete away from the search box too.
- Delete, Alt+U and Alt+D no longer act on the hidden list while Full Weather is showing.

### Full Weather

- F5 in Full Weather refreshes the whole report. It used to drop the hourly and daily sections.
- Opening Full Weather reads the report once, instead of reading its heading two or three times as the forecast and alerts arrive.

### Dialogs

- **Search Results:** Enter adds the selected place, as the window says.
- **Configure:** OK now updates the list (for example, after you change to Celsius), and Enter means OK. OK no longer opens Full Weather when you started from the list.
- **Escape** closes Expected Precipitation, Weather Around Me, Historical Weather, Astronomy, Marine Forecast, My Data, Weather Alerts and Browse Weather Alerts.
- **Browse Cities by State/Country:** screen readers now say whether each city is checked, and Load Cities takes you to the list.
- **Browse Weather Alerts:** choosing a region takes you to its alerts and reads the first one, and Tab no longer skips the list of alert types.
- The lists in these windows have names, so screen readers announce "Moon", "Multi-year results" and so on, instead of no name or the wrong label.
- The Weather menu items have their own access keys: Weather **A**lerts, **E**xpected Precipitation, Weather Around **M**e, **H**istorical Weather, My **D**ata, Ma**r**ine Forecast and As**t**ronomy.

### Other

- The default cities for a new install are capitalized properly (Mexico City, Maui).

Full user guide: https://theideaplace.github.io/WeatherFast/

// Places of the World: curated lists of famous places (bridges, beaches,
// extreme-weather spots) from places-of-the-world.json, shared with iOS and
// Windows (CityData/ is the source).
//
// File shape: { categories: [ { name, description, places: [ { name,
// description, city, state, country, lat, lon } ] } ] }. city and state may
// be missing or null, for example for an Antarctic station.
//
// Plain functions with no DOM access, so they can be tested; app.js uses them.

// The usable categories in a loaded file, in file order. A category without a
// name, or a place without a name or numeric coordinates, is skipped.
function parsePlaceCategories(data) {
    const out = [];
    if (!data || !Array.isArray(data.categories)) return out;
    for (const cat of data.categories) {
        if (!cat || typeof cat !== 'object' || !cat.name) continue;
        const places = [];
        for (const p of Array.isArray(cat.places) ? cat.places : []) {
            if (!p || typeof p !== 'object' || !p.name) continue;
            const lat = Number(p.lat);
            const lon = Number(p.lon);
            if (p.lat === null || p.lon === null || p.lat === undefined || p.lon === undefined ||
                !Number.isFinite(lat) || !Number.isFinite(lon)) continue;
            places.push({ ...p, lat, lon });
        }
        out.push({ name: cat.name, description: cat.description || '', places });
    }
    return out;
}

// Where a place is: "San Francisco, California, United States", or just
// "Antarctica" when there's no town or state.
function placeLocationLine(place) {
    return [place.city, place.state, place.country].filter(Boolean).join(', ');
}

// The name a place gets in Your Cities, as on iOS and Windows: "Golden Gate
// Bridge, San Francisco", or just the name when there's no town (or the town
// is the place's own name).
function placeSavedName(place) {
    return place.city && place.city !== place.name ? `${place.name}, ${place.city}` : place.name;
}

// Countries NWS alerts cover, as the data names them
const NWS_PLACE_COUNTRIES = ['United States', 'Puerto Rico', 'United States Virgin Islands'];

function isNwsPlace(place) {
    return NWS_PLACE_COUNTRIES.includes(place.country);
}

// Saved names of every place NWS covers. A saved place is "Golden Gate
// Bridge, San Francisco", with no country in it, so the alert check can't
// tell it's in the US from the name alone.
function nwsPlaceSavedNames(categories) {
    const names = new Set();
    categories.forEach(cat => cat.places.forEach(p => {
        if (isNwsPlace(p)) names.add(placeSavedName(p));
    }));
    return names;
}

// How a list reads in the chooser: "Famous Bridges (153 places)".
function placeCategoryLabel(category) {
    const n = category.places.length;
    return `${category.name} (${n} place${n === 1 ? '' : 's'})`;
}

// A browse row for a place, in the shape the state/country browse views use.
// display is the saved name (it's also the key in Your Cities, and names the
// Add button); label is what the row shows, the bare name, because the
// location line that follows already gives the town. location and note are
// shown after the weather.
function placeToCityInfo(place) {
    return {
        name: place.name,
        label: place.name,
        display: placeSavedName(place),
        state: place.state || '',
        country: place.country || '',
        lat: place.lat,
        lon: place.lon,
        location: placeLocationLine(place),
        note: place.description || '',
        weather: null
    };
}

// Split a list into runs of at most size items.
function chunk(items, size) {
    const out = [];
    for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
    return out;
}

// Open-Meteo takes many places in one request (comma-separated coordinates)
// and answers with an array in the same order; for a single place it answers
// with one object. Returns one result (or null) per location.
function weatherResultsFromResponse(json, count) {
    const list = Array.isArray(json) ? json : [json];
    const out = [];
    for (let i = 0; i < count; i++) {
        const r = list[i];
        out.push(r && r.current ? r : null);
    }
    return out;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        parsePlaceCategories,
        placeLocationLine,
        placeSavedName,
        placeCategoryLabel,
        isNwsPlace,
        nwsPlaceSavedNames,
        placeToCityInfo,
        chunk,
        weatherResultsFromResponse
    };
}

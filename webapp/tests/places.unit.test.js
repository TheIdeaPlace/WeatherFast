/**
 * Places of the World: the helpers in places.js and the bundled data file
 */
import fs from 'fs';
import path from 'path';
import { axe } from 'jest-axe';

const {
    parsePlaceCategories,
    placeLocationLine,
    placeSavedName,
    placeCategoryLabel,
    isNwsPlace,
    nwsPlaceSavedNames,
    placeToCityInfo,
    chunk,
    weatherResultsFromResponse
} = require('../places.js');

const WEBAPP = path.join(__dirname, '..');
const REPO = path.join(WEBAPP, '..');

const GOLDEN_GATE = {
    name: 'Golden Gate Bridge',
    description: 'Art Deco suspension bridge across the Golden Gate strait',
    city: 'San Francisco', state: 'California', country: 'United States',
    lat: 37.8197, lon: -122.4786
};
const VOSTOK = {
    name: 'Vostok Station', description: 'Coldest temperature ever measured',
    city: null, state: null, country: 'Antarctica', lat: -78.46, lon: 106.84
};

describe('place helpers', () => {
    test('location line', () => {
        expect(placeLocationLine(GOLDEN_GATE)).toBe('San Francisco, California, United States');
        expect(placeLocationLine(VOSTOK)).toBe('Antarctica');
    });

    test('saved name matches iOS and Windows', () => {
        expect(placeSavedName(GOLDEN_GATE)).toBe('Golden Gate Bridge, San Francisco');
        expect(placeSavedName(VOSTOK)).toBe('Vostok Station');
        expect(placeSavedName({ ...GOLDEN_GATE, name: 'Venice', city: 'Venice' })).toBe('Venice');
    });

    test('category label', () => {
        expect(placeCategoryLabel({ name: 'Beaches', places: [1, 2] })).toBe('Beaches (2 places)');
        expect(placeCategoryLabel({ name: 'One', places: [1] })).toBe('One (1 place)');
    });

    test('city info for the browse views', () => {
        expect(placeToCityInfo(GOLDEN_GATE)).toEqual({
            name: 'Golden Gate Bridge',
            label: 'Golden Gate Bridge',
            display: 'Golden Gate Bridge, San Francisco',
            state: 'California',
            country: 'United States',
            lat: 37.8197,
            lon: -122.4786,
            location: 'San Francisco, California, United States',
            note: 'Art Deco suspension bridge across the Golden Gate strait',
            weather: null
        });
        expect(placeToCityInfo(VOSTOK).state).toBe('');
    });

    test('NWS covers the US and its territories, by saved name', () => {
        expect(isNwsPlace(GOLDEN_GATE)).toBe(true);
        expect(isNwsPlace({ country: 'Puerto Rico' })).toBe(true);
        expect(isNwsPlace({ country: 'United States Virgin Islands' })).toBe(true);
        expect(isNwsPlace(VOSTOK)).toBe(false);
        const names = nwsPlaceSavedNames([{ name: 'x', places: [GOLDEN_GATE, VOSTOK] }]);
        expect([...names]).toEqual(['Golden Gate Bridge, San Francisco']);
    });

    test('chunk', () => {
        expect(chunk([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
        expect(chunk([], 50)).toEqual([]);
    });
});

describe('parsePlaceCategories', () => {
    test('skips bad entries', () => {
        const cats = parsePlaceCategories({
            categories: [
                {
                    name: 'Ok', description: 'd', places: [
                        GOLDEN_GATE,
                        { name: 'No coords' },
                        { name: 'Bad lat', lat: 'north', lon: 1 },
                        { name: 'Null lat', lat: null, lon: 1 },
                        { lat: 1, lon: 2 },
                        'not an object',
                        { ...VOSTOK, lat: '-78.46' }
                    ]
                },
                { description: 'no name', places: [] },
                null
            ]
        });
        expect(cats.map(c => c.name)).toEqual(['Ok']);
        expect(cats[0].places.map(p => p.name)).toEqual(['Golden Gate Bridge', 'Vostok Station']);
        expect(cats[0].places[1].lat).toBe(-78.46);
    });

    test('not a places file', () => {
        expect(parsePlaceCategories(null)).toEqual([]);
        expect(parsePlaceCategories([])).toEqual([]);
        expect(parsePlaceCategories({ categories: 'x' })).toEqual([]);
    });
});

describe('weatherResultsFromResponse', () => {
    const ok = n => ({ current: { temperature_2m: n } });

    test('many places answer with an array in order', () => {
        expect(weatherResultsFromResponse([ok(1), ok(2)], 2)).toEqual([ok(1), ok(2)]);
    });

    test('one place answers with an object', () => {
        expect(weatherResultsFromResponse(ok(5), 1)).toEqual([ok(5)]);
    });

    test('short or broken answers leave nulls, never shift places', () => {
        expect(weatherResultsFromResponse([ok(1), {}, null], 4)).toEqual([ok(1), null, null, null]);
    });
});

describe('bundled places-of-the-world.json', () => {
    const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));

    test('web copy matches CityData', () => {
        expect(read(path.join(WEBAPP, 'places-of-the-world.json')))
            .toEqual(read(path.join(REPO, 'CityData', 'places-of-the-world.json')));
    });

    test('every place is usable', () => {
        const raw = read(path.join(WEBAPP, 'places-of-the-world.json'));
        const cats = parsePlaceCategories(raw);
        expect(cats.length).toBeGreaterThanOrEqual(3);
        cats.forEach((cat, i) => {
            // nothing was dropped by the parser
            expect(cat.places.length).toBe(raw.categories[i].places.length);
            expect(cat.description).toBeTruthy();
            // at most 50 places per Open-Meteo request, at most 200 per list
            expect(cat.places.length).toBeLessThanOrEqual(200);
            cat.places.forEach(p => {
                expect(placeLocationLine(p)).toBeTruthy();
                expect(Math.abs(p.lat)).toBeLessThanOrEqual(90);
                expect(Math.abs(p.lon)).toBeLessThanOrEqual(180);
            });
        });
    });
});

describe('Browse markup in index.html', () => {
    beforeEach(() => {
        const html = fs.readFileSync(path.join(WEBAPP, 'index.html'), 'utf8');
        const start = html.indexOf('<section class="state-selector-section">');
        const end = html.indexOf('</section>', start) + '</section>'.length;
        document.body.innerHTML = `<main>${html.slice(start, end)}</main>`;
    });

    test('three tabs, each controlling a panel labelled by it', () => {
        const tabs = [...document.querySelectorAll('.location-tabs [role="tab"]')];
        expect(tabs.map(t => t.textContent.trim()))
            .toEqual(['U.S. States', 'International', 'Places of the World']);
        tabs.forEach(tab => {
            const panel = document.getElementById(tab.getAttribute('aria-controls'));
            expect(panel).not.toBeNull();
            expect(panel.getAttribute('aria-labelledby')).toBe(tab.id);
        });
    });

    test('the list chooser is labelled and described', () => {
        const select = document.getElementById('places-select');
        expect(document.querySelector('label[for="places-select"]')).not.toBeNull();
        expect(document.getElementById(select.getAttribute('aria-describedby'))).not.toBeNull();
    });

    test('no axe violations with the Places panel showing', async () => {
        document.getElementById('us-states-panel').hidden = true;
        document.getElementById('places-panel').hidden = false;
        expect(await axe(document.body)).toHaveNoViolations();
    });
});

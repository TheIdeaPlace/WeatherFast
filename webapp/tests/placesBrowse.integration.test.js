/**
 * Places of the World in the real app: index.html with places.js and app.js
 * loaded, JSON files served from disk, Open-Meteo and NWS mocked.
 */
import fs from 'fs';
import path from 'path';
import { axe } from 'jest-axe';

const WEBAPP = path.join(__dirname, '..');
const read = f => fs.readFileSync(path.join(WEBAPP, f), 'utf8');

const flush = () => new Promise(resolve => setTimeout(resolve, 0));
async function until(check, ms = 3000) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
        if (check()) return;
        await new Promise(resolve => setTimeout(resolve, 10));
    }
    throw new Error('timed out');
}

// One fake current-weather answer per requested coordinate, in order
function meteoAnswer(url) {
    const lats = new URL(url).searchParams.get('latitude').split(',');
    const one = lat => ({
        latitude: Number(lat),
        current: { temperature_2m: 10, weather_code: 0, apparent_temperature: 9,
            relative_humidity_2m: 50, wind_speed_10m: 5, wind_direction_10m: 90 },
        daily: { temperature_2m_max: [12], temperature_2m_min: [4],
            sunrise: ['2026-11-24T07:00'], sunset: ['2026-11-24T16:30'] }
    });
    return lats.length === 1 ? one(lats[0]) : lats.map(one);
}

let meteoCalls;
let holdMeteo;   // when set, Open-Meteo answers wait for it

function installFetch() {
    meteoCalls = [];
    holdMeteo = null;
    global.fetch = jest.fn(async (url) => {
        const u = String(url);
        if (!u.startsWith('http')) {
            const body = read(u.split('?')[0]);
            return { ok: true, status: 200, json: async () => JSON.parse(body) };
        }
        if (u.includes('open-meteo')) {
            meteoCalls.push(u);
            if (holdMeteo) await holdMeteo;
            return { ok: true, status: 200, json: async () => meteoAnswer(u) };
        }
        return { ok: true, status: 200, json: async () => ({ features: [] }) };
    });
    window.fetch = global.fetch;
}

beforeAll(() => {
    const html = read('index.html').replace(/<script[\s\S]*?<\/script>/g, '');
    document.documentElement.innerHTML = html.replace(/^[\s\S]*?<html[^>]*>/i, '').replace(/<\/html>\s*$/i, '');
    localStorage.getItem.mockReturnValue(null);
    window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {} }));
    installFetch();
    // Script-scope variables are reached through this hook
    window.eval(read('places.js'));
    window.eval(read('app.js') + `
        window.__t = {
            get currentStateCities() { return currentStateCities; },
            get currentLocationType() { return currentLocationType; },
            get nwsPlaceNames() { return nwsPlaceNames; },
            fetchWeatherAlerts,
            get cities() { return cities; },
            switchView,
            showYourCities
        };`);
    document.dispatchEvent(new Event('DOMContentLoaded'));
});

beforeEach(async () => {
    installFetch();
    await until(() => document.getElementById('places-select').options.length > 1);
});

const $ = id => document.getElementById(id);
const submit = () => $('state-selector-form').dispatchEvent(new Event('submit', { cancelable: true }));
const key = (el, k) => el.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true }));

describe('Browse tabs', () => {
    test('arrow keys stay within the Browse tabs and change what Load uses', () => {
        $('us-states-tab').click();
        $('us-states-tab').focus();
        key($('us-states-tab'), 'ArrowRight');
        expect(document.activeElement.id).toBe('international-tab');
        expect(window.__t.currentLocationType).toBe('international');
        key(document.activeElement, 'ArrowRight');
        expect(document.activeElement.id).toBe('places-tab');
        expect(window.__t.currentLocationType).toBe('places');
        expect($('places-panel').hidden).toBe(false);
        expect($('us-states-panel').hidden).toBe(true);
        key(document.activeElement, 'ArrowRight');
        expect(document.activeElement.id).toBe('us-states-tab');
        key(document.activeElement, 'End');
        expect(document.activeElement.id).toBe('places-tab');
    });

    test('choosing a Browse tab leaves the Configure tabs alone', () => {
        const configTab = $('current-tab');
        const configPanel = $(configTab.getAttribute('aria-controls'));
        expect(configTab.getAttribute('aria-selected')).toBe('true');
        $('international-tab').click();
        $('places-tab').click();
        expect(configTab.getAttribute('aria-selected')).toBe('true');
        expect(configPanel.hidden).toBe(false);
    });
});

describe('the city list has a screen reader name in every view (WCAG 4.1.2)', () => {
    // Accessibility Insights flagged the list view's listbox as unnamed
    const cityListViolations = async () => {
        const results = await axe($('city-list').closest('section'));
        if (process.env.AXE_DEBUG) {
            process.stderr.write(JSON.stringify(results.violations.map(v =>
                [v.id, v.nodes.slice(0, 2).map(n => n.html.slice(0, 120))])) + '\n');
        }
        return results.violations.map(v => v.id);
    };

    afterAll(() => {
        window.__t.showYourCities();
        window.__t.switchView('flat');
    });

    test.each(['list', 'flat', 'table'])('Your Cities, %s view', async (view) => {
        window.__t.showYourCities();
        window.__t.switchView(view);
        expect($('city-list').getAttribute('role')).toBeTruthy();
        expect($('city-list').getAttribute('aria-label')).toBe('Your cities');
        expect(await cityListViolations()).toEqual([]);
    });

    test('while a list loads, the old list box and its name are gone', async () => {
        let release;
        holdMeteo = new Promise(resolve => { release = resolve; });
        window.__t.switchView('list');
        expect($('city-list').getAttribute('role')).toBe('listbox');
        $('places-tab').click();
        $('places-select').value = 'Famous Bridges';
        submit();
        await until(() => meteoCalls.length === 1);
        expect($('city-list').hasAttribute('role')).toBe(false);
        expect($('city-list').hasAttribute('aria-label')).toBe(false);
        expect($('city-list').hasAttribute('tabindex')).toBe(false);
        window.__t.showYourCities();
        release();
        await new Promise(resolve => setTimeout(resolve, 700));
    });

    test('a Places list in list view is named for the list', async () => {
        window.__t.switchView('list');
        $('places-tab').click();
        $('places-select').value = 'Beaches of the World';
        submit();
        await until(() => document.querySelectorAll('.state-city-item').length === 144, 10000);
        expect($('city-list').getAttribute('role')).toBe('listbox');
        expect($('city-list').getAttribute('aria-label')).toBe('Beaches of the World');
        expect(await cityListViolations()).toEqual([]);
        window.__t.switchView('table');
        expect($('city-list').getAttribute('aria-label')).toBe('Beaches of the World');
        expect(await cityListViolations()).toEqual([]);
        window.__t.switchView('list');
        window.__t.showYourCities();
        expect($('city-list').getAttribute('aria-label')).toBe('Your cities');
    }, 15000);

    test('with no saved cities, Back leaves an empty plain list named Your cities', async () => {
        const saved = window.__t.cities;
        const keys = Object.keys(saved);
        const backup = keys.map(k => [k, saved[k]]);
        keys.forEach(k => delete saved[k]);
        try {
            window.__t.switchView('list');
            $('us-states-tab').click();
            $('state-select').value = 'Wisconsin';
            submit();
            await until(() => document.querySelectorAll('.state-city-item').length > 0, 10000);
            expect($('city-list').getAttribute('aria-label')).toBe('Cities in Wisconsin');
            window.__t.showYourCities();
            expect($('city-list').getAttribute('role')).toBe('list');
            expect($('city-list').hasAttribute('tabindex')).toBe(false);
            expect($('city-list').getAttribute('aria-label')).toBe('Your cities');
        } finally {
            backup.forEach(([k, v]) => { saved[k] = v; });
            window.__t.showYourCities();
        }
    }, 15000);
});

describe('Places of the World', () => {
    beforeEach(() => $('places-tab').click());

    test('lists in the chooser, and the description follows the choice', () => {
        const options = [...$('places-select').options].map(o => o.textContent);
        expect(options[0]).toBe('-- Select a List --');
        expect(options).toContain('Famous Bridges (153 places)');
        const desc = $('places-description').textContent;
        $('places-select').value = 'Famous Bridges';
        $('places-select').dispatchEvent(new Event('change'));
        expect($('places-description').textContent).not.toBe(desc);
        $('places-select').value = '';
        $('places-select').dispatchEvent(new Event('change'));
        expect($('places-description').textContent).toBe(desc);
    });

    test('Load with no list chosen says so', async () => {
        $('places-select').value = '';
        submit();
        await until(() => $('state-selector-error').textContent.length > 0);
        expect($('state-selector-error').textContent).toMatch(/select a list of places/i);
        // The chooser says it's invalid and points at the message
        expect($('places-select').getAttribute('aria-invalid')).toBe('true');
        expect($('places-select').getAttribute('aria-describedby')).toContain('state-selector-error');
        // and stops saying so once a list is chosen and loaded
        $('places-select').value = 'Famous Bridges';
        submit();
        await flush();
        expect($('places-select').hasAttribute('aria-invalid')).toBe(false);
        expect($('places-select').getAttribute('aria-describedby')).toBe('places-description');
        // Let that load finish, so its requests don't count in the next test
        await until(() => document.querySelectorAll('.state-city-card').length === 153, 10000);
        window.__t.showYourCities();
    }, 15000);

    test('a list loads 50 places to a request and shows every place', async () => {
        $('places-select').value = 'Famous Bridges';
        submit();
        await until(() => document.querySelectorAll('.state-city-card').length === 153, 10000);
        expect(meteoCalls.length).toBe(4);   // 50 + 50 + 50 + 3
        expect(new URL(meteoCalls[0]).searchParams.get('latitude').split(',').length).toBe(50);
        expect($('your-cities-heading').textContent).toMatch(/^Famous Bridges \(153\)/);
        const card = [...document.querySelectorAll('.state-city-card')]
            .find(c => c.querySelector('h3').textContent === 'Golden Gate Bridge');
        expect(card.querySelector('.place-location').textContent).toBe('San Francisco, California, United States');
        expect(card.querySelector('button').getAttribute('aria-label'))
            .toBe('Add to My Cities: Golden Gate Bridge, San Francisco');
    }, 15000);

    test('Back while a list is loading keeps Your Cities', async () => {
        let release;
        holdMeteo = new Promise(resolve => { release = resolve; });
        $('places-select').value = 'Beaches of the World';
        submit();
        await until(() => meteoCalls.length === 1);
        $('back-to-your-cities-btn').click();
        release();
        await new Promise(resolve => setTimeout(resolve, 700));
        expect($('your-cities-heading').textContent).toBe('Your Cities');
        expect(window.__t.currentStateCities).toBeNull();
        expect(meteoCalls.length).toBe(1);   // the rest of the list was never asked for
    });

    test('a state still loading does not replace a Places list loaded after it', async () => {
        let release;
        holdMeteo = new Promise(resolve => { release = resolve; });
        $('us-states-tab').click();
        $('state-select').value = 'Wisconsin';
        submit();
        await until(() => meteoCalls.length > 0);
        holdMeteo = null;
        $('places-tab').click();
        $('places-select').value = 'Extreme Weather';
        submit();
        await until(() => document.querySelectorAll('.state-city-card').length === 150, 10000);
        release();
        await new Promise(resolve => setTimeout(resolve, 50));
        expect($('your-cities-heading').textContent).toMatch(/^Extreme Weather/);
        expect(window.__t.currentStateCities.length).toBe(150);
    }, 15000);

    test('saved US places get NWS alerts; other places and unknown names do not', async () => {
        expect(window.__t.nwsPlaceNames.has('Golden Gate Bridge, San Francisco')).toBe(true);
        global.fetch.mockClear();
        await window.__t.fetchWeatherAlerts('Golden Gate Bridge, San Francisco', 37.8, -122.5);
        expect(global.fetch.mock.calls.some(([u]) => String(u).includes('api.weather.gov'))).toBe(true);
        global.fetch.mockClear();
        await window.__t.fetchWeatherAlerts('Millau Viaduct, Millau', 44.08, 3.02);
        expect(global.fetch.mock.calls.some(([u]) => String(u).includes('api.weather.gov'))).toBe(false);
    });
});

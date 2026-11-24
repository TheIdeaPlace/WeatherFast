/**
 * Loads the real app (index.html, places.js, app.js) into the jsdom test
 * page: JSON files are read from disk, Open-Meteo and NWS are mocked.
 * Script-scoped variables are reached through window.__t.
 */
import fs from 'fs';
import path from 'path';

export const WEBAPP = path.join(__dirname, '..', '..');
export const read = f => fs.readFileSync(path.join(WEBAPP, f), 'utf8');

export const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export async function until(check, ms = 3000) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
        if (check()) return;
        await sleep(10);
    }
    throw new Error('timed out');
}

// One fake current-weather answer per requested coordinate, in order
export function meteoAnswer(url) {
    const lats = new URL(url).searchParams.get('latitude').split(',');
    const one = lat => ({
        latitude: Number(lat),
        current: { temperature_2m: 10, weather_code: 0, apparent_temperature: 9,
            relative_humidity_2m: 50, wind_speed_10m: 5, wind_direction_10m: 90, uv_index: 3 },
        hourly: { time: Array.from({ length: 48 }, (_, i) => `2026-11-24T${String(i % 24).padStart(2, '0')}:00`),
            temperature_2m: Array(48).fill(10), weathercode: Array(48).fill(0), cloudcover: Array(48).fill(10),
            precipitation_probability: Array(48).fill(0), windspeed_10m: Array(48).fill(5), uv_index: Array(48).fill(1) },
        daily: { time: ['2026-11-24'], temperature_2m_max: [12], temperature_2m_min: [4],
            sunrise: ['2026-11-24T07:00'], sunset: ['2026-11-24T16:30'] }
    });
    return lats.length === 1 ? one(lats[0]) : lats.map(one);
}

export const state = {
    meteoCalls: [],
    holdMeteo: null,     // when set, Open-Meteo answers wait for it
    alertsFor: () => []  // (url) => NWS features for that point
};

export function installFetch() {
    state.meteoCalls = [];
    state.holdMeteo = null;
    global.fetch = jest.fn(async (url) => {
        const u = String(url);
        if (!u.startsWith('http')) {
            const body = read(u.split('?')[0]);
            return { ok: true, status: 200, json: async () => JSON.parse(body) };
        }
        if (u.includes('open-meteo')) {
            state.meteoCalls.push(u);
            if (state.holdMeteo) await state.holdMeteo;
            return { ok: true, status: 200, json: async () => meteoAnswer(u) };
        }
        if (u.includes('api.weather.gov')) {
            return { ok: true, status: 200, json: async () => ({ features: state.alertsFor(u) }) };
        }
        return { ok: true, status: 200, json: async () => ({}) };
    });
    window.fetch = global.fetch;
}

export function loadApp() {
    const html = read('index.html').replace(/<script[\s\S]*?<\/script>/g, '');
    document.documentElement.innerHTML = html.replace(/^[\s\S]*?<html[^>]*>/i, '').replace(/<\/html>\s*$/i, '');
    localStorage.getItem.mockReturnValue(null);
    window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {} }));
    window.confirm = jest.fn(() => true);
    installFetch();
    window.eval(read('places.js'));
    window.eval(read('app.js') + `
        window.__t = {
            get currentStateCities() { return currentStateCities; },
            get currentLocationType() { return currentLocationType; },
            get nwsPlaceNames() { return nwsPlaceNames; },
            get cities() { return cities; },
            get currentConfig() { return currentConfig; },
            fetchWeatherAlerts,
            switchView,
            showYourCities,
            renderCityList,
            alertsCache
        };`);
    document.dispatchEvent(new Event('DOMContentLoaded'));
}

export const $ = id => document.getElementById(id);
export const key = (el, k, opts = {}) =>
    el.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true, ...opts }));

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

// One fake answer per requested coordinate, in order, with every hourly and
// daily field the request asked for (so Full Weather can render)
export function meteoAnswer(url) {
    const params = new URL(url).searchParams;
    const lats = params.get('latitude').split(',');
    const fields = name => (params.get(name) || '').split(',').filter(Boolean);
    const days = Number(params.get('forecast_days') || 1);
    const hours = Math.max(48, days * 24);
    const valueFor = (field, i, daily) => {
        if (field === 'sunrise') return `2026-11-${String(24 + i).padStart(2, '0')}T07:00`;
        if (field === 'sunset') return `2026-11-${String(24 + i).padStart(2, '0')}T16:30`;
        if (/weather_?code/.test(field)) return 0;
        if (/duration/.test(field)) return 36000;
        if (/probability|cover|humidity/.test(field)) return 20;
        if (/temperature|dewpoint|apparent/.test(field)) return daily && /min/.test(field) ? 4 : 10;
        return 1;
    };
    const one = lat => {
        const hourly = { time: Array.from({ length: hours }, (_, i) => {
            const d = new Date(Date.UTC(2026, 10, 24, i));
            return d.toISOString().slice(0, 16);
        }) };
        fields('hourly').forEach(f => { hourly[f] = hourly.time.map((_, i) => valueFor(f, i, false)); });
        const daily = { time: Array.from({ length: days }, (_, i) => `2026-11-${String(24 + i).padStart(2, '0')}`) };
        fields('daily').forEach(f => { daily[f] = daily.time.map((_, i) => valueFor(f, i, true)); });
        return {
            latitude: Number(lat),
            current: { time: '2026-11-24T12:00', temperature_2m: 10, weather_code: 0, apparent_temperature: 9,
                relative_humidity_2m: 50, wind_speed_10m: 5, wind_direction_10m: 90, wind_gusts_10m: 8,
                uv_index: 3, dewpoint_2m: 2, pressure_msl: 1013, visibility: 20000, cloud_cover: 10,
                precipitation: 0, rain: 0, showers: 0, snowfall: 0, is_day: 1 },
            hourly,
            daily
        };
    };
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
            fetchWeatherForCity,
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

/**
 * Focus and dialogs in the real app: the fixes from the accessibility audit.
 * Dialogs take focus, keep Tab inside, close on Escape and give focus back;
 * focus survives the list being rebuilt; alerts open; List view is built in
 * order; the View menu and Configure reordering keep focus.
 */
import { loadApp, installFetch, state, until, sleep, $, key } from './helpers/loadApp';

const MADISON = 'Madison, Wisconsin, United States';
const SAN_DIEGO = 'San Diego, California, United States';

const alert = (over = {}) => ({
    properties: {
        id: over.id || 'a1',
        event: 'Flood Warning',
        severity: 'Severe',
        headline: "Flood Warning until 6 PM. Don't drive through water",
        description: "Rivers are rising. It's dangerous to cross flooded roads.",
        instruction: "Turn around, don't drown.",
        onset: new Date(Date.now() - 3600e3).toISOString(),
        expires: new Date(Date.now() + 3600e3).toISOString(),
        areaDesc: 'Dane County',
        ...over
    }
});

const byKey = k => [...document.querySelectorAll('[data-focus-key]')].find(e => e.dataset.focusKey === k);
const focused = () => document.activeElement;
const open = (sel) => [...document.querySelectorAll('.modal')].filter(m => !m.hidden).map(m => m.id);

beforeAll(async () => {
    loadApp();
    await until(() => byKey(`title|${MADISON}`), 5000);
});

beforeEach(async () => {
    installFetch();
    window.__t.showYourCities();
    if (window.__t.currentConfig.defaultView !== 'flat') window.__t.switchView('flat');
    await sleep(200);
});

describe('dialogs', () => {
    test('Full Weather: focus moves to its title, Tab stays in, Escape returns focus to the city', async () => {
        const opener = byKey(`title|${MADISON}`);
        opener.focus();
        opener.click();
        const dialog = $('weather-details-dialog');
        expect(dialog.hidden).toBe(false);
        expect(focused()).toBe($('weather-details-title'));
        await until(() => !$('weather-details-content').hasAttribute('aria-busy'), 5000);

        // The weather fetch rebuilt the list behind the dialog: the button
        // that opened it is a new element now
        window.__t.renderCityList();
        expect(byKey(`title|${MADISON}`)).not.toBe(opener);

        // Tab from the last control wraps to the first, inside the dialog
        $('close-weather-details-btn').focus();
        key(focused(), 'Tab');
        expect(dialog.contains(focused())).toBe(true);
        key(focused(), 'Tab', { shiftKey: true });
        expect(dialog.contains(focused())).toBe(true);

        key(focused(), 'Escape');
        expect(dialog.hidden).toBe(true);
        expect(focused()).toBe(byKey(`title|${MADISON}`));
    });

    test.each([
        ['history', 'historical-weather-dialog', 'historical-weather-title', 'close-historical-weather-btn'],
        ['precip', 'precipitation-nowcast-dialog', 'precipitation-nowcast-title', 'close-precipitation-nowcast-btn'],
        ['around', 'weather-around-me-dialog', 'weather-around-me-title', 'close-weather-around-me-btn']
    ])('%s: opens with focus on its title and Close returns focus', async (action, dialogId, titleId, closeId) => {
        const opener = byKey(`${action}|${SAN_DIEGO}`);
        opener.focus();
        opener.click();
        expect($(dialogId).hidden).toBe(false);
        expect(focused()).toBe($(titleId));
        expect($(titleId).textContent).toContain('San Diego');
        $(closeId).click();
        expect($(dialogId).hidden).toBe(true);
        expect(focused()).toBe(byKey(`${action}|${SAN_DIEGO}`));
    });

    test('Configure: opens on its selected tab; Escape cancels back to the Configure button', () => {
        $('configure-btn').focus();
        $('configure-btn').click();
        expect($('config-dialog').hidden).toBe(false);
        expect(focused().getAttribute('role')).toBe('tab');
        key(focused(), 'Escape');
        expect($('config-dialog').hidden).toBe(true);
        expect(focused()).toBe($('configure-btn'));
    });

    test('shortcuts do nothing while a dialog is open', () => {
        $('configure-btn').click();
        key(focused(), 'v', { altKey: true });
        expect($('view-menu').hidden).toBe(true);
        key(focused(), 'Escape');
    });
});

describe('alerts', () => {
    beforeEach(() => {
        state.alertsFor = (u) => u.includes('43.07') ? [
            alert({ id: 'minor', event: 'Frost Advisory', severity: 'Minor', headline: 'Frost tonight' }),
            alert()
        ] : [];
        // Fresh checks, not the cached "no alerts"
        Object.keys(window.__t.alertsCache).forEach(k => delete window.__t.alertsCache[k]);
    });

    test("a badge with an apostrophe in the alert opens, names the dialog, and lists every alert", async () => {
        window.__t.renderCityList();
        await until(() => document.querySelector('.alert-badge'), 3000);
        const badge = document.querySelector('.alert-badge');
        // Severity in words, the most serious first
        expect(badge.textContent).toContain('Severe: Flood Warning, +1 more');
        expect(badge.hasAttribute('onclick')).toBe(false);
        badge.focus();
        badge.click();
        const dialog = $('alert-details-dialog');
        expect(dialog.hidden).toBe(false);
        const title = $('alert-details-title');
        expect(title).not.toBeNull();
        expect(title.textContent).toBe(`2 weather alerts for ${MADISON}`);
        expect(focused()).toBe(title);
        expect(dialog.getAttribute('aria-describedby')).toBe('alert-details-headline');
        const events = [...dialog.querySelectorAll('.alert-event')].map(h => h.textContent);
        expect(events).toEqual(['Severe: Flood Warning', 'Minor: Frost Advisory']);
        expect(dialog.textContent).toContain("Turn around, don't drown.");
        $('close-alert-details-btn').click();
        expect(dialog.hidden).toBe(true);
        expect(focused().classList.contains('alert-badge')).toBe(true);
    });

    test('List view Alerts button opens them, and says so when there are none', async () => {
        window.__t.switchView('list');
        const list = $('city-list');
        await until(() => document.querySelector('[data-action="alerts"]'));
        // Madison is selected first
        document.querySelector('[data-action="alerts"]').click();
        await until(() => !$('alert-details-dialog').hidden);
        $('close-alert-details-btn').click();
        // San Diego has none
        list.focus();
        key(list, 'ArrowDown');
        document.querySelector('[data-action="alerts"]').click();
        await until(() => ($('sr-announcer') || {}).textContent === `No active weather alerts for ${SAN_DIEGO}`);
        expect($('alert-details-dialog').hidden).toBe(true);
    });
});

describe('focus survives the list being rebuilt', () => {
    test('Move Down keeps you on the arrow, or the other one at the end', () => {
        const down = byKey(`down|${MADISON}`);
        down.focus();
        down.click();
        expect(Object.keys(window.__t.cities)).toEqual([SAN_DIEGO, MADISON]);
        // Madison is last now: no Down arrow, so its Up arrow
        expect(focused()).toBe(byKey(`up|${MADISON}`));
        byKey(`up|${MADISON}`).click();
        expect(Object.keys(window.__t.cities)).toEqual([MADISON, SAN_DIEGO]);
        expect(focused()).toBe(byKey(`down|${MADISON}`));
    });

    test('weather arriving rebuilds once and keeps focus where it was', async () => {
        const btn = byKey(`history|${SAN_DIEGO}`);
        btn.focus();
        window.__t.renderCityList();
        await sleep(300);
        expect(focused()).toBe(byKey(`history|${SAN_DIEGO}`));
    });

    test('Remove lands on the next city', async () => {
        // Add a third city so removing the first leaves two
        window.__t.cities['Portland, Oregon, United States'] = [45.5, -122.6];
        window.__t.renderCityList();
        byKey(`remove|${MADISON}`).focus();
        byKey(`remove|${MADISON}`).click();
        expect(window.confirm).toHaveBeenCalled();
        expect(focused()).toBe(byKey(`title|${SAN_DIEGO}`));
        // put Madison back first
        const rest = { ...window.__t.cities };
        Object.keys(window.__t.cities).forEach(k => delete window.__t.cities[k]);
        window.__t.cities[MADISON] = [43.074761, -89.3837613];
        window.__t.cities[SAN_DIEGO] = rest[SAN_DIEGO];
        window.__t.renderCityList();
    });
});

describe('List view', () => {
    test('items are in order, once each, and the buttons follow the selection', async () => {
        window.__t.switchView('list');
        const list = $('city-list');
        await sleep(300);
        const names = [...list.querySelectorAll('.list-view-item')].map(i => i.dataset.cityName);
        expect(names).toEqual([MADISON, SAN_DIEGO]);
        const ids = [...list.querySelectorAll('.list-view-item')].map(i => i.id);
        expect(new Set(ids).size).toBe(ids.length);

        const historyBtn = document.querySelector('[data-action="history"]');
        expect(historyBtn.textContent).toBe(`History for ${MADISON}`);
        expect(historyBtn.hasAttribute('aria-label')).toBe(false);
        expect(document.querySelector('[data-action="up"]').disabled).toBe(true);

        list.focus();
        key(list, 'ArrowDown');
        expect(list.getAttribute('aria-activedescendant')).toBe('list-item-1');
        expect(historyBtn.textContent).toBe(`History for ${SAN_DIEGO}`);

        // Move San Diego up: it stays selected and focus stays on Move Up's
        // place (now off at the top, so Move Down)
        document.querySelector('[data-action="up"]').focus();
        document.querySelector('[data-action="up"]').click();
        expect(Object.keys(window.__t.cities)).toEqual([SAN_DIEGO, MADISON]);
        const active = document.getElementById(list.getAttribute('aria-activedescendant'));
        expect(active.dataset.cityName).toBe(SAN_DIEGO);
        expect(focused().dataset.focusKey).toBe(`down|${SAN_DIEGO}`);
        document.querySelector('[data-action="down"]').click();
        expect(Object.keys(window.__t.cities)).toEqual([MADISON, SAN_DIEGO]);
    });
});

describe('Browse', () => {
    test('a loaded list takes you to its heading; Back takes you to the Load button', async () => {
        $('places-tab').click();
        $('places-select').value = 'Beaches of the World';
        $('choose-places-btn').focus();
        $('state-selector-form').dispatchEvent(new Event('submit', { cancelable: true }));
        await until(() => document.querySelectorAll('.state-city-card').length === 144, 10000);
        const heading = $('your-cities-heading');
        expect(focused()).toBe(heading);
        // The heading is just the name; Back is beside it
        expect(heading.textContent).toBe('Beaches of the World (144)');
        expect($('back-to-your-cities-btn').hidden).toBe(false);
        $('back-to-your-cities-btn').focus();
        $('back-to-your-cities-btn').click();
        expect(focused()).toBe($('choose-places-btn'));
        expect($('back-to-your-cities-btn').hidden).toBe(true);
    }, 15000);

    test('Add from a browse list keeps focus on the button, now Remove', async () => {
        $('places-tab').click();
        $('places-select').value = 'Famous Bridges';
        $('state-selector-form').dispatchEvent(new Event('submit', { cancelable: true }));
        await until(() => document.querySelectorAll('.state-city-card').length === 153, 10000);
        const k = 'toggle|Golden Gate Bridge, San Francisco';
        byKey(k).focus();
        byKey(k).click();
        await until(() => byKey(k) && byKey(k).textContent.includes('Remove'), 3000);
        expect(focused()).toBe(byKey(k));
        byKey(k).click();
        await until(() => byKey(k).textContent.includes('Add'));
        expect(focused()).toBe(byKey(k));
        window.__t.showYourCities();
    }, 15000);
});

describe('View menu', () => {
    test('items are menuitemradio; the current one is focused; choosing returns to the button', () => {
        const btn = $('view-menu-btn');
        btn.focus();
        key(btn, 'ArrowDown');
        expect($('view-menu').hidden).toBe(false);
        expect(focused().getAttribute('role')).toBe('menuitemradio');
        expect(focused().getAttribute('aria-checked')).toBe('true');
        document.querySelector('#view-menu [data-view="table"]').click();
        expect($('view-menu').hidden).toBe(true);
        expect(focused()).toBe(btn);
        expect(document.querySelector('#view-menu [data-view="table"]').getAttribute('aria-checked')).toBe('true');
        window.__t.switchView('flat');
    });
});

describe('Configure field order', () => {
    test('moving a field keeps focus on its arrow and keeps unsaved checks', () => {
        $('configure-btn').click();
        $('citylist-tab').click();
        const order = window.__t.currentConfig.cityListOrder;
        const second = order[1];
        const box = document.querySelector(`input[name="citylist-${order[0]}"]`);
        box.checked = !box.checked;
        const changed = box.checked;
        const up = byKey(`order-up|${second}`);
        up.focus();
        up.click();
        expect(window.__t.currentConfig.cityListOrder[0]).toBe(second);
        // At the top its Up arrow is off, so focus is on its Down arrow
        expect(focused()).toBe(byKey(`order-down|${second}`));
        // The box changed before the move (the first field, now second) kept its change
        expect(document.querySelector(`input[name="citylist-${order[0]}"]`).checked).toBe(changed);
        key(focused(), 'Escape');
    });
});

/**
 * Historical Weather dialog, driven through the real index.html and app.js:
 * view switching, 30-day stepping, Previous/Next Year, and archive limits.
 */

const fs = require('fs');
const { axe } = require('jest-axe');
const path = require('path');

const ROOT = path.join(__dirname, '..');

// One archive response per requested range, with a row for every day in it
function archiveResponse(url) {
  const params = new URL(url).searchParams;
  const start = params.get('start_date');
  const end = params.get('end_date');
  const time = [];
  for (let d = new Date(`${start}T00:00:00Z`); d <= new Date(`${end}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1)) {
    time.push(d.toISOString().slice(0, 10));
  }
  return {
    daily: {
      time,
      temperature_2m_max: time.map(() => 20),
      temperature_2m_min: time.map(() => 10),
      precipitation_sum: time.map(() => 0),
      weathercode: time.map(() => 0)
    }
  };
}

function archiveRequests() {
  return fetch.mock.calls
    .map(([url]) => String(url))
    .filter(url => url.includes('archive-api.open-meteo.com'))
    .map(url => {
      const params = new URL(url).searchParams;
      return { start: params.get('start_date'), end: params.get('end_date') };
    });
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0));

async function settle() {
  for (let i = 0; i < 5; i++) await flush();
}

const byId = id => document.getElementById(id);
const disabled = id => byId(id).getAttribute('aria-disabled') === 'true';

async function chooseView(value) {
  const radio = document.querySelector(`input[name="hist-mode"][value="${value}"]`);
  radio.checked = true;
  radio.dispatchEvent(new Event('change', { bubbles: true }));
  await settle();
}

async function loadDate(iso) {
  byId('hist-date-input').value = iso;
  byId('hist-load-btn').click();
  await settle();
}

async function press(id) {
  fetch.mockClear();
  byId(id).click();
  await settle();
}

beforeAll(() => {
  const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
  document.documentElement.innerHTML = html.replace(/<script[\s\S]*?<\/script>/g, '');

  fetch.mockImplementation(async (url) => {
    const target = String(url);
    if (target.includes('archive-api.open-meteo.com')) {
      return { ok: true, json: async () => archiveResponse(target) };
    }
    return { ok: true, json: async () => ([]) };
  });
  localStorage.getItem.mockReturnValue(null);

  // Load the scripts the way the page does, as classic scripts sharing one global scope
  for (const file of ['historical-dates.js', 'app.js']) {
    const script = document.createElement('script');
    script.textContent = fs.readFileSync(path.join(ROOT, file), 'utf8');
    document.body.appendChild(script);
  }
});

beforeEach(async () => {
  fetch.mockClear();
  window.showHistoricalWeather('Madison, Wisconsin, United States', 43.07, -89.38);
  await settle();
});

describe('Historical Weather dialog', () => {
  const today = () => window.HistoricalDates.todayISO();
  const year = () => window.HistoricalDates.yearOf(today());

  test('opens on the same day across 20 years', () => {
    expect(byId('historical-weather-dialog').hidden).toBe(false);
    expect(document.querySelector('input[name="hist-mode"]:checked').value).toBe('multiYear');
    expect(byId('hist-prev-btn').textContent).toContain('Previous 20 Years');
    expect(byId('hist-year-nav').hidden).toBe(true);
    // At most 20 single-day requests, none in the future
    const requests = archiveRequests();
    expect(requests.length).toBeGreaterThan(0);
    expect(requests.length).toBeLessThanOrEqual(20);
    requests.forEach(r => expect(r.end <= today()).toBe(true));
    expect(disabled('hist-next-btn')).toBe(true);
  });

  test('every view offers labeled controls', () => {
    const legend = document.querySelector('.historical-view-modes legend');
    expect(legend.textContent).toBe('View');
    expect(document.querySelector('label[for="hist-date-input"]').textContent).toBe('Date');
    ['singleDay', 'dailyBrowse', 'multiYear'].forEach(value => {
      expect(document.querySelector(`input[name="hist-mode"][value="${value}"]`).closest('label')).not.toBeNull();
    });
  });

  test('Browse Days loads 30 days and steps 30 days at a time', async () => {
    await chooseView('dailyBrowse');
    await loadDate(`${year() - 2}-03-01`);
    expect(archiveRequests().pop()).toEqual({ start: `${year() - 2}-03-01`, end: window.HistoricalDates.addDays(`${year() - 2}-03-01`, 29) });
    expect(byId('hist-prev-btn').textContent).toContain('Previous 30 Days');
    expect(byId('hist-year-nav').hidden).toBe(false);

    await press('hist-next-btn');
    const start = window.HistoricalDates.addDays(`${year() - 2}-03-01`, 30);
    expect(archiveRequests()).toEqual([{ start, end: window.HistoricalDates.addDays(start, 29) }]);
    expect(byId('hist-date-input').value).toBe(start);
  });

  test('Previous Year and Next Year keep the same 30 days', async () => {
    await chooseView('dailyBrowse');
    const start = `${year() - 3}-06-10`;
    await loadDate(start);

    await press('hist-prev-year-btn');
    expect(archiveRequests()).toEqual([{ start: `${year() - 4}-06-10`, end: `${year() - 4}-07-09` }]);
    expect(byId('historical-current-date').textContent).toBe(`June 10, ${year() - 4} to July 9, ${year() - 4}`);

    await press('hist-next-year-btn');
    await press('hist-next-year-btn');
    expect(archiveRequests()).toEqual([{ start: `${year() - 2}-06-10`, end: `${year() - 2}-07-09` }]);
    expect(byId('hist-next-year-btn').getAttribute('aria-label')).toContain(String(year() - 1));
  });

  test('a year jump from Feb 29 lands on Feb 28', async () => {
    await chooseView('dailyBrowse');
    await loadDate('2024-02-29');
    await press('hist-next-year-btn');
    expect(archiveRequests()[0].start).toBe('2025-02-28');
  });

  test('Next Year is unavailable when the range would start today or later', async () => {
    await chooseView('dailyBrowse');
    await loadDate(window.HistoricalDates.addYears(today(), -1));
    expect(disabled('hist-next-year-btn')).toBe(true);
    // An unavailable button keeps focus and does nothing
    await press('hist-next-year-btn');
    expect(archiveRequests()).toEqual([]);
  });

  test('browse ranges end by today', async () => {
    await chooseView('dailyBrowse');
    const start = window.HistoricalDates.addDays(today(), -10);
    await loadDate(start);
    expect(archiveRequests().pop()).toEqual({ start, end: today() });
    expect(disabled('hist-next-btn')).toBe(true);
  });

  test('Browse Days from today starts 29 days back so the range ends today', async () => {
    await chooseView('dailyBrowse');
    expect(byId('hist-date-input').value).toBe(window.HistoricalDates.addDays(today(), -29));
    expect(archiveRequests().pop()).toEqual({ start: window.HistoricalDates.addDays(today(), -29), end: today() });
  });

  test('Previous Year stops at the 1940 archive start', async () => {
    await chooseView('dailyBrowse');
    await loadDate('1940-01-20');
    expect(disabled('hist-prev-year-btn')).toBe(true);
    expect(disabled('hist-prev-btn')).toBe(true);
  });

  test('Single Day steps one day and stops at today', async () => {
    await chooseView('singleDay');
    expect(byId('hist-prev-btn').textContent).toContain('Previous Day');
    expect(byId('hist-year-nav').hidden).toBe(true);
    expect(disabled('hist-next-btn')).toBe(true);

    await press('hist-prev-btn');
    const yesterday = window.HistoricalDates.addDays(today(), -1);
    expect(archiveRequests()).toEqual([{ start: yesterday, end: yesterday }]);
    expect(disabled('hist-next-btn')).toBe(false);
  });

  test('Same Day Across Years shifts the window by 20 years', async () => {
    await press('hist-prev-btn');
    const years = archiveRequests().map(r => Number(r.start.slice(0, 4)));
    expect(Math.max(...years)).toBe(year() - 20);
    expect(Math.min(...years)).toBe(year() - 39);
    expect(disabled('hist-next-btn')).toBe(false);
  });

  test('rejects a date outside the archive', async () => {
    await chooseView('dailyBrowse');
    fetch.mockClear();
    byId('hist-date-input').value = '1939-12-31';
    byId('hist-load-btn').click();
    await settle();
    expect(archiveRequests()).toEqual([]);
  });

  test.each(['multiYear', 'dailyBrowse', 'singleDay'])('has no axe violations in the %s view', async (view) => {
    if (view !== 'multiYear') await chooseView(view);
    const results = await axe(byId('historical-weather-dialog'));
    expect(results).toHaveNoViolations();
  });
});

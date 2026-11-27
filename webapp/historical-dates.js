/**
 * Date math for the Historical Weather dialog.
 *
 * Dates are ISO "yyyy-mm-dd" strings, the format the Open-Meteo archive uses,
 * so they compare correctly as strings and never shift with the time zone.
 * The archive covers 1940-01-01 through today and rejects end dates after today.
 */
(function (root) {
    'use strict';

    const ARCHIVE_START = '1940-01-01';
    const BROWSE_DAYS = 30;
    const YEAR_WINDOW = 20;

    function parse(iso) {
        const [y, m, d] = iso.split('-').map(Number);
        return { y, m, d };
    }

    function format(y, m, d) {
        return `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    }

    function isLeapYear(y) {
        return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
    }

    // Today's calendar date where the user is
    function todayISO(now = new Date()) {
        return format(now.getFullYear(), now.getMonth() + 1, now.getDate());
    }

    function addDays(iso, days) {
        const { y, m, d } = parse(iso);
        const dt = new Date(Date.UTC(y, m - 1, d + days));
        return format(dt.getUTCFullYear(), dt.getUTCMonth() + 1, dt.getUTCDate());
    }

    // Same calendar day in another year; Feb 29 lands on Feb 28 in non-leap years
    function addYears(iso, years) {
        const { y, m, d } = parse(iso);
        const year = y + years;
        const day = (m === 2 && d === 29 && !isLeapYear(year)) ? 28 : d;
        return format(year, m, day);
    }

    function yearOf(iso) {
        return parse(iso).y;
    }

    function inArchive(iso, today = todayISO()) {
        return iso >= ARCHIVE_START && iso <= today;
    }

    function minISO(a, b) {
        return a < b ? a : b;
    }

    // A browse range of `days` days starting at `start`, ending no later than today
    function browseRange(start, days = BROWSE_DAYS, today = todayISO()) {
        return { start, end: minISO(addDays(start, days - 1), today) };
    }

    // Stepping moves the start by `days`; the new start must be in the archive
    function canStepDays(start, days, today = todayISO()) {
        return inArchive(addDays(start, days), today);
    }

    // A year jump keeps the range, which must still start before today
    function canShiftYear(start, years, today = todayISO()) {
        const shifted = addYears(start, years);
        return shifted >= ARCHIVE_START && shifted < today;
    }

    // Years shown for the same day: `count` years ending at `endYear`, newest first, none before 1940
    function yearWindow(endYear, count = YEAR_WINDOW) {
        const years = [];
        for (let y = endYear; y > endYear - count && y >= yearOf(ARCHIVE_START); y--) {
            years.push(y);
        }
        return years;
    }

    function canShiftYearWindow(endYear, direction, count = YEAR_WINDOW, today = todayISO()) {
        if (direction < 0) return endYear - count >= yearOf(ARCHIVE_START);
        return endYear < yearOf(today);
    }

    // "November 26, 2026" (or without the year), independent of the time zone
    function formatLong(iso, { withYear = true } = {}) {
        const { y, m, d } = parse(iso);
        const options = { month: 'long', day: 'numeric', timeZone: 'UTC' };
        if (withYear) options.year = 'numeric';
        return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', options);
    }

    // "Nov 26, 2026"
    function formatShort(iso) {
        const { y, m, d } = parse(iso);
        return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC'
        });
    }

    const api = {
        ARCHIVE_START,
        BROWSE_DAYS,
        YEAR_WINDOW,
        todayISO,
        addDays,
        addYears,
        yearOf,
        inArchive,
        browseRange,
        canStepDays,
        canShiftYear,
        yearWindow,
        canShiftYearWindow,
        formatLong,
        formatShort
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    } else {
        root.HistoricalDates = api;
    }
})(typeof window !== 'undefined' ? window : this);

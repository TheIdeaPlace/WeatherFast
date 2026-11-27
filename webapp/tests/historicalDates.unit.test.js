/**
 * Historical Weather date math (historical-dates.js)
 */

const HD = require('../historical-dates.js');

const TODAY = '2026-11-26';

describe('Historical dates', () => {
  test('addDays crosses month and year boundaries', () => {
    expect(HD.addDays('2025-12-31', 1)).toBe('2026-01-01');
    expect(HD.addDays('2024-03-01', -1)).toBe('2024-02-29');
    expect(HD.addDays('2025-11-01', 30)).toBe('2025-12-01');
  });

  test('addYears keeps the calendar day', () => {
    expect(HD.addYears('2020-07-04', -1)).toBe('2019-07-04');
    expect(HD.addYears('2020-07-04', 2)).toBe('2022-07-04');
  });

  test('addYears moves Feb 29 to Feb 28 in non-leap years', () => {
    expect(HD.addYears('2024-02-29', 1)).toBe('2025-02-28');
    expect(HD.addYears('2024-02-29', 4)).toBe('2028-02-29');
    expect(HD.addYears('2000-02-29', 100)).toBe('2100-02-28');
  });

  test('inArchive covers 1940 through today', () => {
    expect(HD.inArchive('1940-01-01', TODAY)).toBe(true);
    expect(HD.inArchive('1939-12-31', TODAY)).toBe(false);
    expect(HD.inArchive(TODAY, TODAY)).toBe(true);
    expect(HD.inArchive('2026-11-27', TODAY)).toBe(false);
  });

  test('browseRange is 30 days and ends no later than today', () => {
    expect(HD.browseRange('2025-11-01', 30, TODAY)).toEqual({ start: '2025-11-01', end: '2025-11-30' });
    // The archive rejects end dates after today
    expect(HD.browseRange('2026-11-10', 30, TODAY)).toEqual({ start: '2026-11-10', end: TODAY });
  });

  test('canStepDays keeps the new start inside the archive', () => {
    expect(HD.canStepDays('2026-10-27', 30, TODAY)).toBe(true);   // lands on today
    expect(HD.canStepDays('2026-10-28', 30, TODAY)).toBe(false);  // would start tomorrow
    expect(HD.canStepDays('1940-01-31', -30, TODAY)).toBe(true);
    expect(HD.canStepDays('1940-01-30', -30, TODAY)).toBe(false);
    expect(HD.canStepDays(TODAY, 1, TODAY)).toBe(false);
  });

  test('canShiftYear needs the shifted start before today', () => {
    expect(HD.canShiftYear('2025-11-01', 1, TODAY)).toBe(true);
    expect(HD.canShiftYear('2025-11-26', 1, TODAY)).toBe(false);
    expect(HD.canShiftYear('2025-12-01', 1, TODAY)).toBe(false);
    expect(HD.canShiftYear('1941-01-01', -1, TODAY)).toBe(true);
    expect(HD.canShiftYear('1940-06-01', -1, TODAY)).toBe(false);
  });

  test('yearWindow lists years newest first and stops at 1940', () => {
    expect(HD.yearWindow(2026, 3)).toEqual([2026, 2025, 2024]);
    expect(HD.yearWindow(1941, 5)).toEqual([1941, 1940]);
  });

  test('canShiftYearWindow stops at 1940 and at this year', () => {
    expect(HD.canShiftYearWindow(2026, 1, 20, TODAY)).toBe(false);
    expect(HD.canShiftYearWindow(2006, 1, 20, TODAY)).toBe(true);
    expect(HD.canShiftYearWindow(1960, -1, 20, TODAY)).toBe(true);
    expect(HD.canShiftYearWindow(1959, -1, 20, TODAY)).toBe(false);
  });

  test('formatting does not shift with the time zone', () => {
    expect(HD.formatLong('2025-01-01')).toBe('January 1, 2025');
    expect(HD.formatLong('2025-12-31', { withYear: false })).toBe('December 31');
    expect(HD.formatShort('2025-07-04')).toBe('Jul 4, 2025');
  });

  test('todayISO uses the local calendar date', () => {
    expect(HD.todayISO(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05');
  });
});

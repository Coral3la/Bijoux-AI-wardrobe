import { describe, expect, it } from 'vitest';

import { CATEGORIES, CONDITIONS, SUBCATEGORIES } from './enums';

describe('the closed vocabulary mirror', () => {
  it('gives every category a subcategory list', () => {
    expect(Object.keys(SUBCATEGORIES).sort()).toEqual([...CATEGORIES].sort());
  });

  it('has no duplicate subcategory within a category', () => {
    for (const [category, subs] of Object.entries(SUBCATEGORIES)) {
      expect(new Set(subs).size, category).toBe(subs.length);
    }
  });

  it('does not reuse a subcategory across two categories', () => {
    const all = Object.values(SUBCATEGORIES).flat();
    expect(new Set(all).size).toBe(all.length);
  });

  // Transcribed from docs/02-DATA-MODEL.md rather than derived from the array
  // under test, so a value added on one side of the hand-mirror fails here
  // instead of moving the expectation with it. Nothing can compare this file
  // against app/enums.py, which is what makes the literal worth writing out.
  // The order is load-bearing on this one: it is also the item_category type's
  // sort order, which migration 0003 appended to.
  it('mirrors the nine categories in order', () => {
    expect([...CATEGORIES]).toEqual([
      'top',
      'bottom',
      'dress',
      'outerwear',
      'shoes',
      'bag',
      'accessory',
      'swimwear',
      'sleepwear',
    ]);
  });

  it('mirrors the eight weather conditions', () => {
    expect([...CONDITIONS]).toEqual([
      'clear',
      'partly_cloudy',
      'cloudy',
      'fog',
      'drizzle',
      'rain',
      'snow',
      'thunderstorm',
    ]);
  });
});

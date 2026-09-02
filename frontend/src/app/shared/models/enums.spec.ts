import { describe, expect, it } from 'vitest';

import { CATEGORIES, CONDITIONS, OCCASIONS, ROLES, SLOTS, SUBCATEGORIES, roleOf } from './enums';

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
  // Transcribed from docs/02-DATA-MODEL.md, which adopted the list at task
  // 2.11 from 04-API-SPEC.md's `replace_role`. Six, not nine: `outerwear` is
  // `outer` here, and `dress`, `swimwear` and `sleepwear` are not roles.
  it('mirrors the six roles in order', () => {
    expect([...ROLES]).toEqual(['top', 'bottom', 'outer', 'shoes', 'bag', 'accessory']);
  });

  // The map is the ↻ badge's whole rule for which tiles it appears on, so the
  // three categories with no role are asserted as such rather than left out.
  it('resolves every category that has a role, and only those', () => {
    expect(CATEGORIES.filter((category) => roleOf(category) !== undefined)).toEqual([
      'top',
      'bottom',
      'outerwear',
      'shoes',
      'bag',
      'accessory',
    ]);
    expect(roleOf('outerwear')).toBe('outer');
    expect(roleOf('dress')).toBeUndefined();
    expect(roleOf(null)).toBeUndefined();
  });

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

  // Two, and in this order: it is the order a day's entries must reach
  // POST /trips/pack in and the order the trip page stacks its cards in. A slot
  // is *when* and an occasion is *what for*, which is why `evening` appears in
  // both lists in this file without the two meaning the same thing.
  it('mirrors the two slots in order', () => {
    expect([...SLOTS]).toEqual(['day', 'evening']);
  });

  it('mirrors the six occasions', () => {
    expect([...OCCASIONS]).toEqual(['casual', 'work', 'evening', 'sport', 'formal', 'travel']);
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

import { describe, expect, it } from 'vitest';

import { CATEGORIES, SUBCATEGORIES } from './enums';

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
});

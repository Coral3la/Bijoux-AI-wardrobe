import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { ItemStatsResponse } from '../../shared/models/item.model';
import { WardrobeInsights } from './wardrobe-insights';

let fixture: ComponentFixture<WardrobeInsights>;
let mock: HttpTestingController;

function stats(overrides: Partial<ItemStatsResponse> = {}): ItemStatsResponse {
  return {
    total: 138,
    by_category: { top: 41 },
    by_color: { black: 22 },
    processing: 0,
    failed: 2,
    worn: 102,
    never_worn: 34,
    most_worn: { id: 'item-1', display_name: 'light blue mom jeans', wear_count: 12 },
    ...overrides,
  };
}

function statsRequest() {
  return mock.expectOne(`${environment.apiUrl}/items/stats`);
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

function panel(): HTMLElement | null {
  return element().querySelector('section');
}

// The copy is never spelled out in an assertion: the key and its parameters
// are what this file defends, so the expected string is built from the same
// key the component reads. A reworded string keeps these tests green, a
// renamed key or a wrong number does not.
function t(key: string, params?: Record<string, string | number>): string {
  return TestBed.inject(I18nService).t(key, params);
}

async function render(): Promise<void> {
  fixture = TestBed.createComponent(WardrobeInsights);
  await fixture.whenStable();
}

describe('WardrobeInsights', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([{ path: 'wardrobe/:id', children: [] }]),
      ],
    });
    mock = TestBed.inject(HttpTestingController);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    try {
      mock.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });

  it('counts the never-worn against the tagged wardrobe rather than the total', async () => {
    await render();

    statsRequest().flush(stats());
    await fixture.whenStable();

    // 102 + 34, which is the `ready` population the two numbers partition —
    // not `total`, which counts the two failed rows as well. A line reading
    // "34 of 138" would count the never-worn against a population the wear
    // numbers exclude, and it would do it directly under a header stating
    // that same 138 about a different set of rows. DECISIONS.md 188.
    expect(text()).toContain(t('wardrobe.insights.neverWorn.other', { count: 34, ready: 136 }));
    expect(text()).toContain('34');
    expect(text()).toContain('136');
    expect(text()).not.toContain('138');
  });

  it('names the most-worn garment and links to it', async () => {
    await render();

    statsRequest().flush(stats());
    await fixture.whenStable();

    expect(text()).toContain(
      t('wardrobe.insights.mostWorn.other', { name: 'light blue mom jeans', count: 12 }),
    );
    expect(element().querySelector('a')?.getAttribute('href')).toBe('/wardrobe/item-1');
  });

  it('does not say "1 items" or "1 wears"', async () => {
    await render();

    statsRequest().flush(
      stats({
        worn: 5,
        never_worn: 1,
        most_worn: { id: 'item-2', display_name: 'black wool coat', wear_count: 1 },
      }),
    );
    await fixture.whenStable();

    expect(text()).toContain(t('wardrobe.insights.neverWorn.one', { ready: 6 }));
    expect(text()).toContain(t('wardrobe.insights.mostWorn.one', { name: 'black wool coat' }));
  });

  // First empty state: a wardrobe nothing has been worn in. The count is
  // correct and it is not an insight — the application has not been told what
  // she wears yet, and printing the whole wardrobe back at her as a reproach
  // is the one thing this panel exists not to do. DECISIONS.md 188.
  it('renders nothing at all when nothing has been worn', async () => {
    await render();

    statsRequest().flush(stats({ worn: 0, never_worn: 136, most_worn: null }));
    await fixture.whenStable();

    expect(panel()).toBeNull();
    expect(text().trim()).toBe('');
  });

  // Second empty state, softened rather than hidden: the same statistic at its
  // far end is a real fact, where "0 items you have never worn" is a boast
  // about a number.
  it('says everything has been worn rather than printing a zero', async () => {
    await render();

    statsRequest().flush(stats({ worn: 136, never_worn: 0 }));
    await fixture.whenStable();

    expect(text()).toContain(t('wardrobe.insights.allWorn'));
    expect(text()).not.toContain('0');
    expect(text()).not.toContain(t('wardrobe.insights.neverWorn.other', { count: 0, ready: 136 }));
  });

  // Third state: the panel disappears and takes its failure with it. The
  // wardrobe around it is not this component's to disturb — WeatherStrip's
  // rule, DECISIONS.md 180.
  it('disappears silently when the request fails', async () => {
    await render();

    statsRequest().flush(
      { code: 'internal_error' },
      { status: 500, statusText: 'Internal Server Error' },
    );
    await fixture.whenStable();

    expect(panel()).toBeNull();
    expect(text().trim()).toBe('');
  });
});

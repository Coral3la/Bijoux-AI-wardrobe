import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { ItemFilters } from '../../core/state/wardrobe.store';
import { Category } from '../../shared/models/enums';
import { CategoryCounts, FilterBar } from './filter-bar';

let fixture: ComponentFixture<FilterBar>;
let mock: HttpTestingController;
let emitted: ItemFilters[] = [];

// The bar is given its numbers rather than counting anything, so this is a
// literal and not a wardrobe: the page owns the arithmetic. Two categories
// carry a value and the other seven do not, which is the shape a real wardrobe
// has and is what makes the zero on an empty category visible here.
const COUNTS: CategoryCounts = {
  all: 32,
  byCategory: new Map<Category, number>([
    ['top', 10],
    ['bottom', 5],
  ]),
};

async function render(filters: ItemFilters = {}): Promise<void> {
  fixture = TestBed.createComponent(FilterBar);
  fixture.componentRef.setInput('filters', filters);
  fixture.componentRef.setInput('counts', COUNTS);
  fixture.componentInstance.filtersChanged.subscribe((next) => emitted.push(next));
  await fixture.whenStable();
}

function buttons(): HTMLButtonElement[] {
  return [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')];
}

function buttonWith(label: string): HTMLButtonElement {
  return buttons().find((candidate) => candidate.textContent?.trim() === label)!;
}

function maybeButtonWith(label: string): HTMLButtonElement | undefined {
  return buttons().find((candidate) => candidate.textContent?.trim() === label);
}

// A category chip is two spans — the label and its count — so the label alone
// is what names it, and matching on the button's whole text would mean knowing
// the number to find the chip that carries it. The disclosure and Clear filters
// have no spans at all and keep buttonWith above.
function chipWith(label: string): HTMLButtonElement {
  return buttons().find(
    (candidate) => candidate.querySelector('span')?.textContent?.trim() === label,
  )!;
}

function swatch(label: string): HTMLButtonElement {
  return buttons().find((candidate) => candidate.getAttribute('aria-label') === label)!;
}

function ranges(): HTMLInputElement[] {
  return [
    ...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLInputElement>(
      'input[type=range]',
    ),
  ];
}

async function open(): Promise<void> {
  buttonWith('Filters').click();
  await fixture.whenStable();
}

// The gate's range input is not a browser's: it does not snap to `step`, and an
// unbound one reads 50 rather than the midpoint. Both handles are bound in the
// template for that reason, and this helper deliberately sets a value the
// browser would have snapped — the rounding under test belongs to the store.
async function drag(input: HTMLInputElement, value: string): Promise<void> {
  input.value = value;
  input.dispatchEvent(new Event('input'));
  await fixture.whenStable();
}

describe('FilterBar', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    mock = TestBed.inject(HttpTestingController);
    emitted = [];

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  // The counts came onto the chips at the Atelier pass, so the chip is no
  // longer identified by its whole text and this asserts both halves: an
  // unwired count renders nothing where a zero renders a zero, and the two
  // are only distinguishable if the number is read. Accessories is the third
  // assertion because it is a category the fixture gives no entry for, which
  // is the case that must print 0 rather than blank. DECISIONS.md 219.
  it('renders one chip per category with its count, plus All', async () => {
    await render();

    expect(chipWith('All').textContent).toContain('32');
    expect(chipWith('Tops').textContent).toContain('10');
    expect(chipWith('Accessories').textContent).toContain('0');
  });

  it('emits the category a chip names', async () => {
    await render();

    chipWith('Bottoms').click();

    expect(emitted).toEqual([{ category: 'bottom' }]);
  });

  // Two chips, never one: with a single control on screen a per-chip binding
  // and a global one are indistinguishable, which is how two mutations survived
  // 108 passing tests at 1.5. DECISIONS.md 093.
  it('marks only the selected chip as pressed', async () => {
    await render({ category: 'top' });

    expect(chipWith('Tops').getAttribute('aria-pressed')).toBe('true');
    expect(chipWith('Bottoms').getAttribute('aria-pressed')).toBe('false');
    expect(chipWith('All').getAttribute('aria-pressed')).toBe('false');
  });

  it('clears the category through All, leaving the other dimensions alone', async () => {
    await render({ category: 'top', color_primary: 'black' });

    chipWith('All').click();

    expect(emitted).toEqual([{ category: undefined, color_primary: 'black' }]);
  });

  it('keeps the panel shut until it is asked for', async () => {
    await render();

    expect(ranges()).toHaveLength(0);
    expect(buttonWith('Filters').getAttribute('aria-expanded')).toBe('false');
    // The one chip in the row with no number on it, because it names no subset
    // of the grid. Asserted as the whole trimmed text, which is what a count
    // appearing here would break. DECISIONS.md 219.
    expect(buttonWith('Filters').textContent?.trim()).toBe('Filters');
  });

  it('opens the panel on the disclosure', async () => {
    await render();

    await open();

    expect(buttonWith('Filters').getAttribute('aria-expanded')).toBe('true');
    expect(ranges()).toHaveLength(4);
  });

  // The label is the only thing telling one swatch from another to a screen
  // reader, because the control is a colour and carries no text at all.
  it('gives every swatch a name and emits the colour it names', async () => {
    await render();
    await open();

    expect(swatch('Light blue')).toBeTruthy();
    swatch('Navy').click();

    expect(emitted).toEqual([{ color_primary: 'navy' }]);
  });

  it('clears the colour when the selected swatch is tapped again', async () => {
    await render({ color_primary: 'navy' });
    await open();

    swatch('Navy').click();

    expect(emitted).toEqual([{ color_primary: undefined }]);
  });

  it('emits both bounds of a range when either handle moves', async () => {
    await render();
    await open();

    await drag(ranges()[0], '3');

    expect(emitted).toEqual([{ formality_min: 3, formality_max: 5 }]);
  });

  // The bar reports what the control said and rounds nothing. jsdom does not
  // snap to `step`, so 2.7 arrives here intact — and the store is where it
  // becomes a 3. A bar that rounded would hide a missing coercion downstream.
  //
  // Both dimensions, and the second one is here because the first mutation run
  // said so: rounding inside setFormality survived the whole suite while the
  // identical claim about setWarmth was defended, because only a warmth handle
  // was ever dragged with a fraction. Two near-identical methods, one test —
  // 1.5's lesson arriving from the other side. 06-TESTING-STRATEGY.md.
  it('reports an unsnapped warmth value rather than rounding it', async () => {
    await render();
    await open();

    await drag(ranges()[3], '2.7');

    expect(emitted).toEqual([{ warmth_min: 1, warmth_max: 2.7 }]);
  });

  it('reports an unsnapped formality value rather than rounding it', async () => {
    await render();
    await open();

    await drag(ranges()[0], '3.4');

    expect(emitted).toEqual([{ formality_min: 3.4, formality_max: 5 }]);
  });

  it('offers Clear filters only while something is filtered', async () => {
    await render();

    expect(maybeButtonWith('Clear filters')).toBeUndefined();

    await render({ category: 'top' });

    expect(maybeButtonWith('Clear filters')).toBeTruthy();
  });

  it('clears every dimension at once', async () => {
    await render({ category: 'top', color_primary: 'black', warmth_min: 2 });

    buttonWith('Clear filters').click();

    expect(emitted).toEqual([{}]);
  });
});

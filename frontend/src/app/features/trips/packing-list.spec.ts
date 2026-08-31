import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { Item } from '../../shared/models/item.model';
import { PackingList } from './packing-list';

let fixture: ComponentFixture<PackingList>;

function item(overrides: Partial<Item> = {}): Item {
  return {
    id: 'item-1',
    short_id: 'AB12CD',
    status: 'ready',
    image_public_id: 'bijoux/users/1/abc',
    image_url: 'https://res.cloudinary.com/demo/image/upload/w_300/abc.jpg',
    category: 'top',
    subcategory: 'shirt',
    fit: 'relaxed',
    length: 'long_sleeve',
    rise: null,
    color_primary: 'white',
    color_secondary: null,
    pattern: 'solid',
    material: 'cotton',
    formality: 3,
    warmth: 2,
    layer: 'base',
    water_resistant: false,
    display_name: 'white oversized shirt',
    attributes: {},
    ai_confidence: 0.9,
    user_edited: false,
    error_message: null,
    wear_count: 0,
    last_worn_at: null,
    is_archived: false,
    created_at: '2026-08-19T09:00:00Z',
    updated_at: '2026-08-19T09:00:00Z',
    ...overrides,
  };
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

function boxes(): HTMLInputElement[] {
  return [...element().querySelectorAll<HTMLInputElement>('input[type="checkbox"]')];
}

// The strike class, not input.checked. A checkbox toggles itself natively on
// click, so `checked` reads back true-then-false whether or not the component
// wrote anything — a mutation making toggle() add-only survived the whole suite
// on exactly that. This class is bound to the signal, so it can only be right
// if the state is. 06-TESTING-STRATEGY.md's 4.5 entry, one shape along.
function struck(): boolean[] {
  return [...element().querySelectorAll('label span')].map((s) =>
    s.className.includes('line-through'),
  );
}

function headings(): string[] {
  return [...element().querySelectorAll('h3')].map((h) => h.textContent?.trim() ?? '');
}

function labels(): string[] {
  return [...element().querySelectorAll('label span')].map((s) => s.textContent?.trim() ?? '');
}

function render(items: readonly Item[]): void {
  fixture = TestBed.createComponent(PackingList);
  fixture.componentRef.setInput('items', items);
  fixture.detectChanges();
}

describe('PackingList', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const mock = TestBed.inject(HttpTestingController);
    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  it('groups the items by category and counts each group', () => {
    render([
      item({ id: 'a', category: 'top', display_name: 'white shirt' }),
      item({ id: 'b', category: 'top', display_name: 'black sweater' }),
      item({ id: 'c', category: 'shoes', display_name: 'brown boots' }),
    ]);

    expect(headings()).toEqual(['Tops (2)', 'Shoes (1)']);
  });

  // In CATEGORIES order, not in arrival order: two trips carrying the same
  // garments have to list them the same way. The fixture arrives shoes-first
  // precisely so the two orders differ.
  it('orders the groups by the vocabulary rather than by arrival', () => {
    render([
      item({ id: 'a', category: 'shoes', display_name: 'brown boots' }),
      item({ id: 'b', category: 'bottom', display_name: 'blue jeans' }),
      item({ id: 'c', category: 'top', display_name: 'white shirt' }),
    ]);

    expect(headings()).toEqual(['Tops (1)', 'Bottoms (1)', 'Shoes (1)']);
  });

  it('starts with nothing ticked', () => {
    render([item({ id: 'a' }), item({ id: 'b', display_name: 'black sweater' })]);

    expect(struck()).toEqual([false, false]);
  });

  // The two ids differ from the two positions on purpose: a toggle keyed by
  // index rather than by id passes when they agree, which is 4.5's shadowed
  // $index one shape along (06-TESTING-STRATEGY.md).
  it('ticks the row that was clicked and no other', () => {
    render([
      item({ id: 'a', category: 'top', display_name: 'white shirt' }),
      item({ id: 'b', category: 'top', display_name: 'black sweater' }),
      item({ id: 'c', category: 'top', display_name: 'grey cardigan' }),
    ]);

    boxes()[1].click();
    fixture.detectChanges();

    expect(struck()).toEqual([false, true, false]);
  });

  it('unticks a row that is ticked again', () => {
    render([item({ id: 'a' })]);

    boxes()[0].click();
    fixture.detectChanges();
    expect(struck()).toEqual([true]);

    boxes()[0].click();
    fixture.detectChanges();
    expect(struck()).toEqual([false]);
  });

  it('drives the checkbox itself from the state, not from the click', () => {
    render([item({ id: 'a' })]);
    boxes()[0].click();
    fixture.detectChanges();

    expect(boxes()[0].checked).toBe(true);
  });

  // display_name is null on a row the wardrobe never finished tagging, and a
  // packing list with a blank line in it is a garment nobody can identify.
  it('names an untagged garment rather than leaving the row empty', () => {
    render([item({ id: 'a', display_name: null })]);

    expect(labels()).toEqual([en['item.untitled']]);
  });

  // A null category cannot reach this list today — every packed item comes out
  // of a look and the stylist is served ready rows — but the type admits one,
  // and a Map keyed by CATEGORIES alone would drop it silently.
  it('keeps an item with no category, at the end, under its own heading', () => {
    render([
      item({ id: 'a', category: null, display_name: 'mystery garment' }),
      item({ id: 'b', category: 'top', display_name: 'white shirt' }),
    ]);

    expect(headings()).toEqual(['Tops (1)', 'Other (1)']);
    expect(text()).toContain('mystery garment');
  });

  it('renders nothing but its heading for an empty list', () => {
    render([]);

    expect(headings()).toEqual([]);
    expect(text()).toContain(en['trip.view.packingList']);
  });
});

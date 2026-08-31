import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { Item } from '../../shared/models/item.model';
import { Look } from '../../shared/models/look.model';
import { StillWorn, TripLook } from './trip-look';

let fixture: ComponentFixture<TripLook>;
let swapped: Item[];

// Its own copy, as every spec in this project keeps its own: no test module here
// imports a fixture from another, and the one that started doing so would make
// a change to one screen's fixture a change to another screen's test.
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

function look(overrides: Partial<Look> = {}): Look {
  return {
    id: 'look-1',
    occasion: 'work',
    title: 'Morning meetings',
    items: [item()],
    reasoning: 'The high-rise jean balances the oversized shirt.',
    weather_note: 'Mild at 18°C — the blazer is enough.',
    is_saved: false,
    feedback: null,
    worn_at: null,
    ...overrides,
  };
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

function tiles(): HTMLElement[] {
  return [...element().querySelectorAll<HTMLElement>('li')];
}

function badges(): HTMLButtonElement[] {
  return [...element().querySelectorAll<HTMLButtonElement>('li button')];
}

// Per tile rather than as a count, because the mutation this is here to catch —
// binding the overlay to `swappingItemId() !== null` instead of to this item's
// id — puts a spinner on every tile and a count of one would still be wrong in
// the same direction as a count of three.
function waiting(): boolean[] {
  return tiles().map((tile) => tile.querySelector('[role="status"]') !== null);
}

function names(): string[] {
  return [...element().querySelectorAll('img')].map((image) => image.getAttribute('alt') ?? '');
}

function render(current: Look, inputs: Record<string, unknown> = {}): void {
  fixture = TestBed.createComponent(TripLook);
  fixture.componentRef.setInput('look', current);
  for (const [name, value] of Object.entries(inputs)) {
    fixture.componentRef.setInput(name, value);
  }
  swapped = [];
  fixture.componentInstance.swap.subscribe((chosen: Item) => swapped.push(chosen));
  fixture.detectChanges();
}

describe('TripLook', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const mock = TestBed.inject(HttpTestingController);
    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  it('renders the title, the reasoning and the weather note', () => {
    render(look());

    expect(element().querySelector('h2')?.textContent).toContain('Morning meetings');
    expect(text()).toContain('The high-rise jean balances the oversized shirt.');
    expect(text()).toContain('Mild at 18°C — the blazer is enough.');
  });

  // The order the server sent, which is look_items.position. The fixture arrives
  // shoes-before-top precisely because the look card's layer grouping would put
  // the base layer first — so this fails if the arrangement is ever borrowed.
  it('keeps the server order rather than grouping by layer', () => {
    render(
      look({
        items: [
          item({ id: 'a', category: 'shoes', layer: 'standalone', display_name: 'brown boots' }),
          item({ id: 'b', category: 'top', layer: 'base', display_name: 'white shirt' }),
        ],
      }),
    );

    expect(names()).toEqual(['brown boots', 'white shirt']);
  });

  it('puts a badge on every garment that has a role', () => {
    render(
      look({
        items: [
          item({ id: 'a', category: 'top' }),
          item({ id: 'b', category: 'shoes' }),
          item({ id: 'c', category: 'bag' }),
        ],
      }),
    );

    expect(badges()).toHaveLength(3);
  });

  // Replacing a dress can legally return a top and a bottom, which is not the
  // single-item swap `replace_role` names. AUDITS.md O-25.
  it('draws no badge on a dress', () => {
    render(
      look({
        items: [item({ id: 'a', category: 'dress' }), item({ id: 'b', category: 'shoes' })],
      }),
    );

    expect(badges()).toHaveLength(1);
    expect(waiting()).toEqual([false, false]);
  });

  it('names the garment each badge would replace', () => {
    render(look({ items: [item({ id: 'a', display_name: 'white shirt' })] }));

    expect(badges()[0].getAttribute('aria-label')).toBe('Swap white shirt for something else');
  });

  it('names an untagged garment rather than leaving the badge unlabelled', () => {
    render(look({ items: [item({ id: 'a', display_name: null })] }));

    expect(badges()[0].getAttribute('aria-label')).toBe(
      `Swap ${en['item.untitled']} for something else`,
    );
  });

  // The second badge, not the first: a handler that emits the look's opening
  // item passes on a one-item fixture and on any assertion that only counts.
  it('emits the garment whose badge was pressed', () => {
    render(
      look({
        items: [item({ id: 'a', category: 'top' }), item({ id: 'b', category: 'shoes' })],
      }),
    );

    badges()[1].click();

    expect(swapped.map((chosen) => chosen.id)).toEqual(['b']);
  });

  it('disables every badge while a swap is in flight', () => {
    render(
      look({
        items: [item({ id: 'a', category: 'top' }), item({ id: 'b', category: 'shoes' })],
      }),
      { swappingItemId: 'a' },
    );

    expect(badges().map((badge) => badge.disabled)).toEqual([true, true]);
  });

  // The wait is drawn on the tile that was tapped and on no other. A mutation
  // binding the overlay to "a swap is running" covers the whole look, which is
  // the pack's wait borrowed by a screen that has something to keep.
  it('covers the tapped tile alone with the spinner', () => {
    render(
      look({
        items: [
          item({ id: 'a', category: 'top' }),
          item({ id: 'b', category: 'shoes' }),
          item({ id: 'c', category: 'bag' }),
        ],
      }),
      { swappingItemId: 'b' },
    );

    expect(waiting()).toEqual([false, true, false]);
    expect(text()).toContain(en['trip.swap.doing']);
  });

  it('shows no spinner when nothing is being swapped', () => {
    render(look({ items: [item({ id: 'a' }), item({ id: 'b' })] }));

    expect(waiting()).toEqual([false, false]);
  });

  // The separator is a translator's string and the list has no "and": Intl
  // would write one and take the browser's locale with it, on a screen whose
  // every other word came from en.json. DECISIONS.md 206's refusal, one
  // sentence along.
  it('joins the still-worn days with the separator and never with an "and"', () => {
    const worn: StillWorn = { name: 'blue jeans', days: [2, 3, 5] };
    render(look(), { stillWorn: worn });

    expect(text()).toContain("You'll still wear the blue jeans on Day 2, Day 3, Day 5.");
    expect(text()).not.toContain(' and ');
  });

  // The separator is read from the table rather than typed into the join, and
  // this is the only assertion that can tell the two apart: en.json's value is
  // ", ", so a hard-coded ", " renders identically and survives every other test
  // in this file. A second table with a different separator is what makes the
  // key load-bearing.
  it('takes the separator from the string table rather than from the code', async () => {
    const loading = TestBed.inject(I18nService).load();
    TestBed.inject(HttpTestingController)
      .expectOne('/i18n/en.json')
      .flush({ ...en, 'trip.swap.daysSeparator': ' / ' });
    await loading;

    render(look(), { stillWorn: { name: 'blue jeans', days: [2, 5] } });

    expect(text()).toContain('Day 2 / Day 5');
  });

  it('says nothing about other days when the garment is worn on none', () => {
    render(look(), { stillWorn: null });

    expect(text()).not.toContain('still wear');
  });

  it('renders the swap error inside the look', () => {
    render(look(), { errorKey: 'trip.error.itemNotInLook' });

    expect(element().querySelector('[role="alert"]')?.textContent).toContain(
      en['trip.error.itemNotInLook'],
    );
  });

  it('renders no alert when the swap has not failed', () => {
    render(look());

    expect(element().querySelector('[role="alert"]')).toBeNull();
  });
});

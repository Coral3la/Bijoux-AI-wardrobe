import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { Item } from '../../shared/models/item.model';
import { Look, MissingPiece } from '../../shared/models/look.model';
import { LookCard } from './look-card';

let fixture: ComponentFixture<LookCard>;
let mock: HttpTestingController;
let tries = 0;
let swapped: Item[] = [];

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
    is_archived: false,
    created_at: '2026-08-19T09:00:00Z',
    updated_at: '2026-08-19T09:00:00Z',
    ...overrides,
  };
}

function look(items: readonly Item[], overrides: Partial<Look> = {}): Look {
  return {
    id: 'look-1',
    occasion: 'work',
    title: 'Morning meetings',
    items,
    reasoning: 'The high-rise jean balances the oversized shirt.',
    weather_note: 'Mild at 18°C — the blazer is enough.',
    ...overrides,
  };
}

async function render(
  value: Look,
  missingPieces: readonly MissingPiece[] = [],
  message = '',
  swappingItemId: string | null = null,
): Promise<void> {
  fixture = TestBed.createComponent(LookCard);
  fixture.componentRef.setInput('look', value);
  fixture.componentRef.setInput('missingPieces', missingPieces);
  fixture.componentRef.setInput('message', message);
  fixture.componentRef.setInput('swappingItemId', swappingItemId);
  fixture.componentInstance.tryAgain.subscribe(() => tries++);
  fixture.componentInstance.swap.subscribe((item) => swapped.push(item));
  await fixture.whenStable();
}

// Found by the accessible name rather than by the glyph: the ↻ is decoration
// and the aria-label is what a screen reader reads out, so a badge that lost
// its name would still pass a test that clicked on the character.
function badges(): HTMLButtonElement[] {
  return [...element().querySelectorAll<HTMLButtonElement>('button[aria-label]')].filter(
    (candidate) => (candidate.getAttribute('aria-label') ?? '').startsWith('Swap '),
  );
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

function headings(): string[] {
  return [...element().querySelectorAll('h3')].map((node) => node.textContent?.trim() ?? '');
}

// DOM order across the whole card, not per group: the point of the sort is the
// sequence a user's eye and a screen reader both take, and asserting inside one
// group would pass on a card whose groups came out backwards.
function itemsInOrder(): string[] {
  return [...element().querySelectorAll('img')].map((node) => node.alt);
}

function links(): string[] {
  return [...element().querySelectorAll('a')].map((node) => node.getAttribute('href') ?? '');
}

describe('LookCard', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    mock = TestBed.inject(HttpTestingController);
    tries = 0;
    swapped = [];

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

  // §2.9: by layer and category, not in arbitrary order. The input is shuffled
  // against both axes at once — outer before base, and shoes before bottom
  // inside the layer that holds them — so a card that sorted on one alone
  // cannot pass this.
  it('lays the items out by layer, then by category inside a layer', async () => {
    await render(
      look([
        item({ id: 'a', category: 'bag', layer: 'standalone', display_name: 'tote' }),
        item({ id: 'b', category: 'outerwear', layer: 'outer', display_name: 'blazer' }),
        item({ id: 'c', category: 'shoes', layer: 'standalone', display_name: 'loafers' }),
        item({ id: 'd', category: 'bottom', layer: 'base', display_name: 'jeans' }),
        item({ id: 'e', category: 'top', layer: 'base', display_name: 'shirt' }),
      ]),
    );

    expect(headings()).toEqual([
      en['vocabulary.layer.base'],
      en['vocabulary.layer.outer'],
      en['vocabulary.layer.standalone'],
    ]);
    expect(itemsInOrder()).toEqual(['shirt', 'jeans', 'blazer', 'loafers', 'tote']);
  });

  // An untagged row cannot lead the card. Nothing on the wire promises a layer
  // — item.model.ts types it nullable — so the sort sends null to the end and
  // the heading says so rather than filing it under a layer it is not in.
  it('puts an item with no layer last, under its own heading', async () => {
    await render(
      look([
        item({ id: 'a', category: null, layer: null, display_name: 'unknown' }),
        item({ id: 'b', category: 'top', layer: 'base', display_name: 'shirt' }),
      ]),
    );

    expect(headings()).toEqual([en['vocabulary.layer.base'], en['stylist.look.layerOther']]);
    expect(itemsInOrder()).toEqual(['shirt', 'unknown']);
  });

  it('renders the title, the message, the reasoning and the weather note', async () => {
    await render(look([item()]), [], 'A work outfit for a mild day.');

    expect(text()).toContain('Morning meetings');
    expect(text()).toContain('A work outfit for a mild day.');
    expect(text()).toContain('The high-rise jean balances the oversized shirt.');
    expect(text()).toContain('Mild at 18°C — the blazer is enough.');
  });

  it('names the missing pieces from the shared vocabulary, and only when there are any', async () => {
    await render(look([item()]));
    expect(text()).not.toContain(en['stylist.look.missing']);

    await render(look([item()]), [
      { category: 'shoes', description: 'A neutral closed shoe would complete this.', reason: '…' },
    ]);

    expect(text()).toContain(en['stylist.look.missing']);
    expect(text()).toContain(en['vocabulary.category.shoes']);
    expect(text()).toContain('A neutral closed shoe would complete this.');
  });

  // t() falls back to the key it was given, so a category outside the nine
  // would put `vocabulary.category.…` in front of the user.
  it('prints the description alone when the missing piece names no known category', async () => {
    await render(look([item()]), [
      { category: 'hosiery', description: 'Tights would carry this into November.', reason: '…' },
    ]);

    expect(text()).toContain('Tights would carry this into November.');
    expect(text()).not.toContain('vocabulary.category.');
  });

  it('opens the item detail page from a tile', async () => {
    await render(look([item({ id: 'item-7' })]));

    expect(links()).toContain('/wardrobe/item-7');
  });

  it('offers a swap badge on every item that has a role, naming the garment', async () => {
    await render(
      look([
        item({ id: 'a', category: 'shoes', layer: 'standalone', display_name: 'loafers' }),
        item({ id: 'b', category: 'top', layer: 'base', display_name: 'shirt' }),
      ]),
    );

    expect(badges().map((badge) => badge.getAttribute('aria-label'))).toEqual([
      'Swap shirt for something else',
      'Swap loafers for something else',
    ]);

    badges()[0].click();
    await fixture.whenStable();

    expect(swapped.map((garment) => garment.id)).toEqual(['b']);
  });

  // The vocabulary decides this, not the layout: `replace_role` has no `dress`
  // — replacing one can legally return a top and a bottom, which is not a
  // single-item swap — so the badge that would send it is not drawn.
  // AUDITS.md O-25.
  it('draws no badge on a dress', async () => {
    await render(
      look([
        item({ id: 'a', category: 'dress', layer: 'standalone', display_name: 'slip dress' }),
        item({ id: 'b', category: 'shoes', layer: 'standalone', display_name: 'heels' }),
      ]),
    );

    expect(badges().map((badge) => badge.getAttribute('aria-label'))).toEqual([
      'Swap heels for something else',
    ]);
  });

  // 05-FRONTEND-SPEC.md: the spinner is on that tile alone and the rest of the
  // card stays put — so the other garments are still rendered, still in order,
  // and the badges are held rather than removed.
  it('waits on the tile being replaced and leaves the rest of the card alone', async () => {
    await render(
      look([
        item({ id: 'a', category: 'shoes', layer: 'standalone', display_name: 'loafers' }),
        item({ id: 'b', category: 'top', layer: 'base', display_name: 'shirt' }),
      ]),
      [],
      '',
      'a',
    );

    const waiting = [...element().querySelectorAll('[role="status"]')];
    expect(waiting).toHaveLength(1);
    expect(waiting[0].textContent).toContain(en['stylist.look.swapping']);
    expect(itemsInOrder()).toEqual(['shirt', 'loafers']);
    expect(badges().every((badge) => badge.disabled)).toBe(true);
  });

  it('asks for another look', async () => {
    await render(look([item()]));

    [...element().querySelectorAll('button')]
      .find((candidate) => candidate.textContent?.trim() === en['stylist.look.tryAgain'])!
      .click();
    await fixture.whenStable();

    expect(tries).toBe(1);
  });
});

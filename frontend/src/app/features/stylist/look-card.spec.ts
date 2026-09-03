import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { Item } from '../../shared/models/item.model';
import { Feedback, Look, MissingPiece } from '../../shared/models/look.model';
import { LookCard } from './look-card';
import { LookDraft } from './look-request-form';

let fixture: ComponentFixture<LookCard>;
let mock: HttpTestingController;
let tries = 0;
let swapped: Item[] = [];
let saves = 0;
let ratings: (Feedback | null)[] = [];

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

function look(items: readonly Item[], overrides: Partial<Look> = {}): Look {
  return {
    id: 'look-1',
    occasion: 'work',
    title: 'Morning meetings',
    items,
    reasoning: 'The high-rise jean balances the oversized shirt.',
    weather_note: 'Mild at 18°C — the blazer is enough.',
    is_saved: false,
    feedback: null,
    worn_at: null,
    ...overrides,
  };
}

// 2026-09-01 is a Tuesday, transcribed rather than derived: an expectation that
// formatted its own date with the formatter under test would agree with a broken
// one. DECISIONS.md 220.
function answeredDraft(overrides: Partial<LookDraft> = {}): LookDraft {
  return {
    occasion: 'casual',
    date: '2026-09-01',
    include_outerwear: null,
    notes: 'something long enough to be left out of the kicker',
    ...overrides,
  };
}

async function render(
  value: Look,
  missingPieces: readonly MissingPiece[] = [],
  message = '',
  swappingItemId: string | null = null,
  busy = false,
  answered: LookDraft | null = null,
): Promise<void> {
  fixture = TestBed.createComponent(LookCard);
  fixture.componentRef.setInput('look', value);
  fixture.componentRef.setInput('answered', answered);
  fixture.componentRef.setInput('missingPieces', missingPieces);
  fixture.componentRef.setInput('message', message);
  fixture.componentRef.setInput('swappingItemId', swappingItemId);
  fixture.componentRef.setInput('busy', busy);
  fixture.componentInstance.tryAgain.subscribe(() => tries++);
  fixture.componentInstance.swap.subscribe((item) => swapped.push(item));
  fixture.componentInstance.save.subscribe(() => saves++);
  fixture.componentInstance.rated.subscribe((value) => ratings.push(value));
  await fixture.whenStable();
}

// Both found by accessible name, like the swap badges above and for the same
// reason: every glyph on these three controls is aria-hidden decoration, so a
// test that clicked the character would pass on a button with no name at all.
// It is also what pins the names as fixed — aria-pressed carries the state.
function thumb(direction: 'Up' | 'Down'): HTMLButtonElement {
  const label = en[`stylist.look.thumb${direction}` as keyof typeof en];
  const button = element().querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);
  if (button === null) {
    throw new Error(`the card has no thumb ${direction} button`);
  }
  return button;
}

function heart(): HTMLButtonElement {
  const button = element().querySelector<HTMLButtonElement>(
    `button[aria-label="${en['stylist.look.save']}"]`,
  );
  if (button === null) {
    throw new Error('the card has no save button');
  }
  return button;
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

// The header's first child when it is there at all, which is what makes its
// absence assertable: matched structurally rather than by class, so a restyle
// does not silently retarget this at the message below it.
function kicker(): string | null {
  return element().querySelector('header > p:first-child')?.textContent?.trim() ?? null;
}

function text(): string {
  return element().textContent ?? '';
}

// The caption under each tile, in DOM order. The layer headings this file used
// to read are gone: the layer is printed per tile now, so what was a heading
// over a group is a line under a garment. DECISIONS.md 220.
function metas(): string[] {
  return [...element().querySelectorAll('li > div:last-child > span:nth-child(2)')].map(
    (node) => node.textContent?.trim() ?? '',
  );
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
    saves = 0;
    ratings = [];

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

    expect(itemsInOrder()).toEqual(['shirt', 'jeans', 'blazer', 'loafers', 'tote']);
  });

  // An untagged row cannot lead the card. Nothing on the wire promises a layer
  // — item.model.ts types it nullable — so the sort sends null to the end, and
  // the caption prints what the garment actually has rather than filing it
  // under a layer it is not in. With neither layer nor category there is
  // nothing true to print, so the line is absent instead of empty.
  it('puts an item with no layer last, and captions it with what it has', async () => {
    await render(
      look([
        item({ id: 'a', category: null, layer: null, display_name: 'unknown' }),
        item({ id: 'b', category: 'top', layer: 'base', display_name: 'shirt' }),
      ]),
    );

    expect(itemsInOrder()).toEqual(['shirt', 'unknown']);
    expect(metas()).toEqual([`${en['vocabulary.layer.base']} · ${en['vocabulary.category.top']}`]);
  });

  it('renders the title, the count, the message, the reasoning and the weather note', async () => {
    await render(look([item()]), [], 'A work outfit for a mild day.');

    expect(text()).toContain('Morning meetings');
    // The kicker beside the title, which the Ritual strip added: one piece, so
    // the singular key. I18nService has no plural rule, so a card that reached
    // for one key would read "1 pieces" here. DECISIONS.md 058, 220.
    expect(text()).toContain(en['stylist.look.pieces.one']);
    expect(text()).toContain('A work outfit for a mild day.');
    expect(text()).toContain('The high-rise jean balances the oversized shirt.');
    expect(text()).toContain('Mild at 18°C — the blazer is enough.');
  });

  // The card is self-describing: the parameters are above the title the model
  // gave, so a look can be read without scrolling back to the form. Notes are
  // excluded — free text, and this line is three fields at 11px.
  it('prints the parameters the look was built for', async () => {
    await render(look([item()]), [], '', null, false, answeredDraft());

    expect(kicker()).toBe('Casual · Tue 1 Sept · Auto coat');
    expect(kicker()).not.toContain('something long enough');
  });

  // Every caller that is not the stylist has no request to describe, and the
  // input is optional for exactly that. The selector only ever matches a
  // paragraph that leads the header, so with no kicker there is nothing above
  // the title and the message keeps its place below it.
  it('says nothing above the title when it was given no parameters', async () => {
    await render(look([item()]), [], 'A work outfit for a mild day.');

    expect(kicker()).toBeNull();
    expect(text()).toContain('A work outfit for a mild day.');
  });

  it('names the coat override in the three ways the request can carry it', async () => {
    await render(look([item()]), [], '', null, false, answeredDraft());
    expect(kicker()).toContain(en['stylist.look.coat.auto']);

    await render(look([item()]), [], '', null, false, answeredDraft({ include_outerwear: true }));
    expect(kicker()).toContain(en['stylist.look.coat.yes']);

    await render(look([item()]), [], '', null, false, answeredDraft({ include_outerwear: false }));
    expect(kicker()).toContain(en['stylist.look.coat.no']);
  });

  it('counts the pieces in the plural once there is more than one', async () => {
    await render(look([item({ id: 'a' }), item({ id: 'b' })]));

    expect(text()).toContain('2 pieces');
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

  // The vocabulary decides this, not the layout: `dress` is a role and means
  // "swap this dress for a different dress" — the backend's `_locked_block`
  // prints the clarifier that keeps rule 2's `top and bottom OR dress` from
  // letting the model answer with a top+bottom pair. AUDITS.md O-25.
  it('draws a badge on a dress alongside the other garments', async () => {
    await render(
      look([
        item({ id: 'a', category: 'dress', layer: 'standalone', display_name: 'slip dress' }),
        item({ id: 'b', category: 'shoes', layer: 'standalone', display_name: 'heels' }),
      ]),
    );

    expect(badges().map((badge) => badge.getAttribute('aria-label'))).toEqual([
      'Swap slip dress for something else',
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

  describe('LookCard — the heart', () => {
    it('emits a save when it is tapped', async () => {
      await render(look([item()]));

      heart().click();

      expect(saves).toBe(1);
    });

    it('reports the saved state through aria-pressed rather than its label', async () => {
      // The accessible name is fixed and the state is on aria-pressed. A label
      // that swapped between "Save" and "Unsave" would announce the change twice
      // and disagree with itself about which way the next press goes.
      await render(look([item()], { is_saved: false }));
      expect(heart().getAttribute('aria-pressed')).toBe('false');
      expect(heart().getAttribute('aria-label')).toBe(en['stylist.look.save']);

      await render(look([item()], { is_saved: true }));
      expect(heart().getAttribute('aria-pressed')).toBe('true');
      expect(heart().getAttribute('aria-label')).toBe(en['stylist.look.save']);
    });

    it('fills in when the look is saved', async () => {
      await render(look([item()], { is_saved: true }));
      expect(heart().textContent?.trim()).toBe('\u2665');

      await render(look([item()], { is_saved: false }));
      expect(heart().textContent?.trim()).toBe('\u2661');
    });

    it('is disabled while the save is in flight', async () => {
      await render(look([item()]), [], '', null, true);

      expect(heart().disabled).toBe(true);
    });

    it('does not disable the try-again button while saving', async () => {
      // The two controls are independent: a save in flight is not a reason to
      // stop someone rerolling the look.
      await render(look([item()]), [], '', null, true);

      const tryAgain = [...element().querySelectorAll('button')].find(
        (candidate) => candidate.textContent?.trim() === en['stylist.look.tryAgain'],
      );
      expect(tryAgain?.disabled).toBe(false);
    });
  });

  describe('LookCard — the thumbs', () => {
    it('rates the look up and down', async () => {
      await render(look([item()]));

      thumb('Up').click();
      thumb('Down').click();

      expect(ratings).toEqual([1, -1]);
    });

    it('clears the rating when the thumb already on is pressed again', async () => {
      // The tap that withdraws a rating is the same button, not a third
      // control — so the card emits the value to write rather than the button
      // that was pressed.
      await render(look([item()], { feedback: 1 }));

      thumb('Up').click();

      expect(ratings).toEqual([null]);
    });

    it('replaces the rating when the other thumb is pressed', async () => {
      await render(look([item()], { feedback: 1 }));

      thumb('Down').click();

      expect(ratings).toEqual([-1]);
    });

    it('reports which thumb is on through aria-pressed', async () => {
      await render(look([item()], { feedback: 1 }));
      expect(thumb('Up').getAttribute('aria-pressed')).toBe('true');
      expect(thumb('Down').getAttribute('aria-pressed')).toBe('false');

      await render(look([item()], { feedback: -1 }));
      expect(thumb('Up').getAttribute('aria-pressed')).toBe('false');
      expect(thumb('Down').getAttribute('aria-pressed')).toBe('true');
    });

    it('shows neither as pressed on an unrated look', async () => {
      await render(look([item()], { feedback: null }));

      expect(thumb('Up').getAttribute('aria-pressed')).toBe('false');
      expect(thumb('Down').getAttribute('aria-pressed')).toBe('false');
    });

    it('keeps a fixed accessible name in both states', async () => {
      // aria-pressed carries the state. A name that changed with it would
      // announce the change twice and disagree about the next press.
      await render(look([item()], { feedback: 1 }));
      expect(thumb('Up').getAttribute('aria-label')).toBe(en['stylist.look.thumbUp']);

      await render(look([item()], { feedback: null }));
      expect(thumb('Up').getAttribute('aria-label')).toBe(en['stylist.look.thumbUp']);
    });

    it('disables both thumbs and the heart together while a write is in flight', async () => {
      // One flag, because the store takes one write at a time: a rating and a
      // save cannot be running together.
      await render(look([item()]), [], '', null, true);

      expect([thumb('Up').disabled, thumb('Down').disabled, heart().disabled]).toEqual([
        true,
        true,
        true,
      ]);
    });
  });
});

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { Item } from '../../shared/models/item.model';
import { SetPicker } from './set-picker';

let fixture: ComponentFixture<SetPicker>;
let mock: HttpTestingController;
let picked: string[];
let closed: number;

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
    set_id: null,
    created_at: '2026-08-19T09:00:00Z',
    updated_at: '2026-08-19T09:00:00Z',
    ...overrides,
  };
}

function host(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return host().textContent ?? '';
}

// The candidate tiles, and not every button in the sheet: the backdrop, the
// chips and the dismiss control are buttons too.
function tiles(): HTMLButtonElement[] {
  return [...host().querySelectorAll<HTMLButtonElement>('li button')];
}

function names(): string[] {
  return tiles().map((tile) => tile.textContent?.trim() ?? '');
}

function chip(label: string): HTMLButtonElement {
  return [...host().querySelectorAll<HTMLButtonElement>('button')].find(
    (candidate) => candidate.textContent?.trim() === label,
  )!;
}

async function press(label: string): Promise<void> {
  chip(label).click();
  await fixture.whenStable();
}

async function render(
  items: readonly Item[],
  currentItemId = 'current',
  saving = false,
  errorKey: string | null = null,
): Promise<void> {
  fixture = TestBed.createComponent(SetPicker);
  fixture.componentRef.setInput('items', items);
  fixture.componentRef.setInput('currentItemId', currentItemId);
  fixture.componentRef.setInput('saving', saving);
  fixture.componentRef.setInput('errorKey', errorKey);
  fixture.componentInstance.picked.subscribe((candidate) => picked.push(candidate.id));
  fixture.componentInstance.dismissed.subscribe(() => closed++);
  await fixture.whenStable();
}

describe('SetPicker', () => {
  beforeEach(async () => {
    picked = [];
    closed = 0;
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    mock = TestBed.inject(HttpTestingController);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  // A plain element carrying role="dialog", not <dialog>: jsdom implements
  // neither showModal nor show nor close, so a dialog-based sheet could not be
  // opened by any test in this project. This assertion is what would notice
  // somebody "fixing" it to the native element. DECISIONS.md 098.
  it('is a plain element with a dialog role rather than a dialog element', async () => {
    await render([]);

    expect(host().querySelector('dialog')).toBeNull();
    const sheet = host().querySelector('[role=dialog]');
    expect(sheet).not.toBeNull();
    expect(sheet!.getAttribute('aria-modal')).toBe('true');
  });

  describe('what it offers', () => {
    it('never offers the garment being viewed', async () => {
      await render([item({ id: 'current', display_name: 'the one on screen' }), item({ id: 'b' })]);

      expect(names()).toEqual(['white oversized shirt']);
      expect(text()).not.toContain('the one on screen');
    });

    // A garment already in a set is 422 set_member_taken on the wire. Offering
    // it would make the commonest tap the one error the user cannot act on.
    it('never offers a garment that already belongs to a set', async () => {
      await render([
        item({ id: 'a', set_id: 'set-9', display_name: 'already spoken for' }),
        item({ id: 'b', display_name: 'free' }),
      ]);

      expect(names()).toEqual(['free']);
    });

    // Including this set's own members: re-adding one answers 200 and changes
    // nothing, so the sheet would appear to have done nothing at all.
    it('offers no garment with a set_id, including this garment’s own set', async () => {
      await render([item({ id: 'a', set_id: 'set-1' }), item({ id: 'b', set_id: 'set-1' })], 'c');

      expect(tiles()).toHaveLength(0);
      expect(text()).toContain('Nothing here to pair this with');
    });

    // 422 set_item_unavailable otherwise. The same gate item detail puts on
    // *Style around this*, for the same reason.
    it('offers neither a processing garment nor a failed one', async () => {
      await render([
        item({ id: 'a', status: 'processing', display_name: null }),
        item({ id: 'b', status: 'failed', display_name: 'never finished' }),
        item({ id: 'c', display_name: 'ready' }),
      ]);

      expect(names()).toEqual(['ready']);
    });

    // The excluded categories are the server's configuration and this client
    // has no copy of them, so the sheet offers a swimsuit and the wire refuses
    // it. Asserted rather than left implicit: a future task adding a mirror
    // here should have to delete a test that says why there is none.
    it('offers a garment from a category the stylist excludes', async () => {
      await render([item({ id: 'a', category: 'swimwear', display_name: 'red swimsuit' })]);

      expect(names()).toEqual(['red swimsuit']);
    });

    // GET /items answers created_at DESC and the filter preserves it, so this
    // holds without a sort. It is asserted because a sort added later — by
    // name, by category — would be invisible to every other test here.
    it('keeps the wardrobe’s own order, newest first', async () => {
      await render([
        item({ id: 'a', display_name: 'newest', created_at: '2026-09-03T09:00:00Z' }),
        item({ id: 'b', display_name: 'middle', created_at: '2026-09-02T09:00:00Z' }),
        item({ id: 'c', display_name: 'oldest', created_at: '2026-09-01T09:00:00Z' }),
      ]);

      expect(names()).toEqual(['newest', 'middle', 'oldest']);
    });
  });

  describe('the category chips', () => {
    it('narrows the tiles to one category', async () => {
      await render([
        item({ id: 'a', category: 'top', display_name: 'a shirt' }),
        item({ id: 'b', category: 'bottom', display_name: 'some jeans' }),
      ]);

      await press('Bottoms');

      expect(names()).toEqual(['some jeans']);
    });

    // Self-clearing, like the filter bar's: pressing the pressed chip is the
    // way back to All rather than a dead end.
    it('goes back to everything when the pressed chip is pressed again', async () => {
      await render([
        item({ id: 'a', category: 'top', display_name: 'a shirt' }),
        item({ id: 'b', category: 'bottom', display_name: 'some jeans' }),
      ]);

      await press('Bottoms');
      await press('Bottoms');

      expect(names()).toEqual(['a shirt', 'some jeans']);
    });

    // The closed vocabulary rather than a summary of the wardrobe: a row that
    // grew and shrank with the collection would move under the reader's finger.
    it('draws every category even where the wardrobe has none', async () => {
      await render([item({ id: 'a', category: 'top' })]);

      expect(chip('Shoes')).toBeDefined();
      expect(chip('Swimwear')).toBeDefined();
    });

    // appChip paints and announces from one input. No aria-pressed is bound in
    // this template, which is what keeps the announced state from drifting from
    // the painted one — the failure chip.ts warns about.
    it('announces the pressed chip, and All while nothing is chosen', async () => {
      await render([item({ id: 'a', category: 'top' })]);

      expect(chip('All').getAttribute('aria-pressed')).toBe('true');

      await press('Tops');

      expect(chip('Tops').getAttribute('aria-pressed')).toBe('true');
      expect(chip('All').getAttribute('aria-pressed')).toBe('false');
    });

    // The All chip's label is one short word, so no assertion against en.json's
    // own value can tell a real lookup from a typed literal. A second table
    // with a different value can.
    it('reads the All label from the string table', async () => {
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [provideHttpClient(), provideHttpClientTesting()],
      });
      mock = TestBed.inject(HttpTestingController);
      const loading = TestBed.inject(I18nService).load();
      mock.expectOne('/i18n/en.json').flush({ ...en, 'item.set.pick.all': 'Everything' });
      await loading;

      await render([item({ id: 'a' })]);

      expect(chip('Everything')).toBeDefined();
    });
  });

  describe('picking', () => {
    it('emits the garment that was tapped', async () => {
      await render([item({ id: 'a' }), item({ id: 'b' })]);

      tiles()[1].click();
      await fixture.whenStable();

      expect(picked).toEqual(['b']);
    });

    // The sheet is not closed from inside on a pick: the request has not been
    // made yet, and a failure has to have somewhere to render.
    it('does not close itself when a garment is picked', async () => {
      await render([item({ id: 'a' })]);

      tiles()[0].click();
      await fixture.whenStable();

      expect(closed).toBe(0);
    });

    it('disables every tile while a pick is in flight', async () => {
      await render([item({ id: 'a' }), item({ id: 'b' })], 'current', true);

      expect(tiles().every((tile) => tile.disabled)).toBe(true);
    });

    it('renders the error key it is given', async () => {
      await render([item({ id: 'a' })], 'current', false, 'item.set.error.taken');

      expect(text()).toContain('already belongs to another set');
    });

    it('closes on the backdrop and on the dismiss control', async () => {
      await render([item({ id: 'a' })]);

      host().querySelector<HTMLButtonElement>('.absolute.inset-0')!.click();
      chip('Close').click();
      await fixture.whenStable();

      expect(closed).toBe(2);
    });
  });

  // The photograph is decorative here because the name is printed inside the
  // same button: with alt text the tile would be announced twice.
  it('leaves the tile photographs out of the accessible name', async () => {
    await render([item({ id: 'a' })]);

    expect(host().querySelector('img')!.getAttribute('alt')).toBe('');
  });
});

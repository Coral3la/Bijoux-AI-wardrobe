import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { Item, ItemUpdate } from '../../shared/models/item.model';
import { TagEditor } from './tag-editor';

let fixture: ComponentFixture<TagEditor>;
let mock: HttpTestingController;
let emitted: ItemUpdate[];

function item(overrides: Partial<Item> = {}): Item {
  return {
    id: 'item-1',
    short_id: 'AB12CD',
    status: 'ready',
    image_public_id: 'bijoux/users/1/abc',
    image_url: 'https://res.cloudinary.com/demo/image/upload/w_300/abc.jpg',
    category: 'bottom',
    subcategory: 'jeans',
    fit: 'straight',
    length: 'full',
    rise: 'high',
    color_primary: 'light_blue',
    color_secondary: null,
    pattern: 'denim_wash',
    material: 'denim',
    formality: 2,
    warmth: 2,
    layer: 'base',
    water_resistant: false,
    display_name: 'light blue straight jeans',
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

function host(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

// Queried by id, not by formcontrolname: a property binding does not reflect
// as an attribute, so only the two statically-named controls would be findable
// that way. Every control carries an id for this reason.
function select(name: string): HTMLSelectElement {
  return host().querySelector<HTMLSelectElement>(`select#${name}`)!;
}

function optionValues(name: string): string[] {
  return [...select(name).options].map((option) => option.value);
}

// jsdom fires no change event on a programmatic assignment — and neither does a
// browser. Every spec here dispatches it by hand rather than relying on the
// assignment, which is the property 06-TESTING-STRATEGY.md records for 1.9.
async function choose(name: string, value: string): Promise<void> {
  const control = select(name);
  control.value = value;
  control.dispatchEvent(new Event('change'));
  await fixture.whenStable();
}

async function type(name: string, value: string): Promise<void> {
  const input = host().querySelector<HTMLInputElement>(`input#${name}`)!;
  input.value = value;
  input.dispatchEvent(new Event('input'));
  await fixture.whenStable();
}

async function save(): Promise<void> {
  host().querySelector('form')!.dispatchEvent(new Event('submit'));
  await fixture.whenStable();
}

async function render(value: Item): Promise<void> {
  fixture = TestBed.createComponent(TagEditor);
  fixture.componentRef.setInput('item', value);
  emitted = [];
  fixture.componentInstance.save.subscribe((change) => emitted.push(change));
  await fixture.whenStable();
}

describe('TagEditor', () => {
  beforeEach(async () => {
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

  it('seeds every control from the row', async () => {
    await render(item());

    expect(select('category').value).toBe('bottom');
    expect(select('rise').value).toBe('high');
    expect(select('color_secondary').value).toBe('');
  });

  it('renders the vocabulary as words rather than database values', async () => {
    await render(item());

    expect(host().textContent).toContain('Light blue');
    expect(host().textContent).not.toContain('light_blue');
  });

  // 119: all fourteen, every time. The server's clearing branch is guarded by
  // `field not in changes`, so sending everything is what stops it firing
  // behind a form that has already cleared those fields on screen.
  it('sends all fourteen fields on every save', async () => {
    await render(item());
    await save();

    expect(Object.keys(emitted[0]).sort()).toEqual(
      [
        'category',
        'color_primary',
        'color_secondary',
        'display_name',
        'fit',
        'formality',
        'layer',
        'length',
        'material',
        'pattern',
        'rise',
        'subcategory',
        'warmth',
        'water_resistant',
      ].sort(),
    );
  });

  it('sends an unset field as null rather than an empty string', async () => {
    await render(item());
    await choose('fit', '');
    await save();

    expect(emitted[0].fit).toBeNull();
    expect(emitted[0].category).toBe('bottom');
  });

  // STAGE-1 1.9 in as many words: five empty fields on screen before saving.
  // All five, because 1.2a gave fit and length category rules of their own.
  it('empties all five dependent fields when the category changes', async () => {
    await render(item());
    await choose('category', 'top');

    expect(select('subcategory').value).toBe('');
    expect(select('rise').value).toBe('');
    expect(select('fit').value).toBe('');
    expect(select('length').value).toBe('');
    expect(select('layer').value).toBe('');
  });

  it('sends those five as explicit nulls after a category change', async () => {
    await render(item());
    await choose('category', 'top');
    await save();

    expect(emitted[0]).toMatchObject({
      category: 'top',
      subcategory: null,
      rise: null,
      fit: null,
      length: null,
      layer: null,
    });
  });

  it('narrows the subcategory options to the chosen category', async () => {
    await render(item());
    expect(optionValues('subcategory')).toContain('jeans');

    await choose('category', 'shoes');

    expect(optionValues('subcategory')).toContain('heels');
    expect(optionValues('subcategory')).not.toContain('jeans');
  });

  // 124: SUBCATEGORIES is a value mirror that already exists. The rules that
  // narrow fit, length and rise by category are not mirrored and must not be —
  // every word stays on offer and the server refuses what it refuses.
  it('offers every fit regardless of category', async () => {
    await render(item({ category: 'top' }));

    expect(optionValues('fit')).toContain('skinny');
  });

  // 123: the placeholder represents "not chosen yet", never "clear this".
  it('offers no way to clear a category that is set', async () => {
    await render(item());

    expect(optionValues('category')).not.toContain('');
  });

  it('offers a placeholder while the row has no category', async () => {
    await render(item({ category: null, subcategory: null, display_name: null }));

    expect(optionValues('category')).toContain('');
    expect(select('category').value).toBe('');
  });

  it('refuses to save while the category placeholder is selected', async () => {
    await render(item({ category: null, subcategory: null }));
    await save();

    expect(emitted).toEqual([]);
    expect(host().textContent).toContain('Choose a category before saving');
  });

  it('saves once a category is chosen on a row that had none', async () => {
    await render(item({ category: null, subcategory: null }));
    await choose('category', 'top');
    await save();

    expect(emitted).toHaveLength(1);
    expect(emitted[0].category).toBe('top');
  });

  // The measured jsdom behaviour: assigning a value the select has no option
  // for leaves value "" and selectedIndex -1. That is what a row carrying a
  // tag this category does not offer looks like in the DOM.
  it('reads an illegal value as unselected rather than as itself', async () => {
    await render(item());
    const control = select('fit');
    control.value = 'not-a-fit';

    expect(control.value).toBe('');
    expect(control.selectedIndex).toBe(-1);
  });

  // 115, one screen over: jsdom does not snap to step, so the rounding is ours.
  it('rounds and clamps a scale the control did not snap', async () => {
    await render(item());
    const range = host().querySelector<HTMLInputElement>('input#formality')!;
    range.value = '3.7';
    range.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    await save();

    expect(emitted[0].formality).toBe(4);
  });

  it('sends a blank name as null rather than as an empty string', async () => {
    await render(item());
    await type('display_name', '   ');
    await save();

    expect(emitted[0].display_name).toBeNull();
  });

  it('trims the name it sends', async () => {
    await render(item());
    await type('display_name', '  black tank top  ');
    await save();

    expect(emitted[0].display_name).toBe('black tank top');
  });

  // B's condition: a rejection that also empties the form is a screen nobody
  // tries twice. The error is an input, so this is what proves the values are
  // not re-seeded when it arrives.
  it('keeps every entered value when a rejection comes back', async () => {
    await render(item());
    await choose('category', 'top');
    await type('display_name', 'black tank top');
    fixture.componentRef.setInput('errorKey', 'item.error.save');
    await fixture.whenStable();

    expect(select('category').value).toBe('top');
    expect(host().querySelector<HTMLInputElement>('input#display_name')!.value).toBe(
      'black tank top',
    );
    expect(host().textContent).toContain("We couldn't save those tags");
  });

  it('disables the save while one is in flight', async () => {
    await render(item());
    fixture.componentRef.setInput('saving', true);
    await fixture.whenStable();

    const button = host().querySelector<HTMLButtonElement>('button[type=submit]')!;
    expect(button.disabled).toBe(true);
    expect(button.textContent).toContain('Saving');
  });
});

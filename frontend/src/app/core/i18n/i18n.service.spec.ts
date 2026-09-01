import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { I18nService } from './i18n.service';

describe('I18nService', () => {
  let service: I18nService;
  let mock: HttpTestingController;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(I18nService);
    mock = TestBed.inject(HttpTestingController);

    const loading = service.load();
    mock.expectOne('/i18n/en.json').flush({
      'wardrobe.title': 'Wardrobe',
      'wardrobe.greeting': 'Hello {{name}}',
      'wardrobe.count': '{{ name }}, you have {{count}} items',
      'upload.tooMany': 'Choose at most {{max}} files',
      'spec.mixed': 'It is {{condition}} in {{city}} today',
      'spec.leading': '{{name}} — welcome back',
      'spec.adjacent': '{{a}}{{b}}',
    });
    await loading;
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  it('returns the string for a known key', () => {
    expect(service.t('wardrobe.title')).toBe('Wardrobe');
  });

  it('returns the key itself when it is missing', () => {
    expect(service.t('nothing.here')).toBe('nothing.here');
  });

  it('interpolates a named parameter', () => {
    expect(service.t('wardrobe.greeting', { name: 'Coral' })).toBe('Hello Coral');
  });

  it('interpolates every placeholder and tolerates whitespace in the braces', () => {
    expect(service.t('wardrobe.count', { name: 'Coral', count: 138 })).toBe(
      'Coral, you have 138 items',
    );
  });

  it('coerces a numeric parameter', () => {
    expect(service.t('upload.tooMany', { max: 20 })).toBe('Choose at most 20 files');
  });

  it('leaves a placeholder visible when no value is supplied for it', () => {
    expect(service.t('wardrobe.greeting', {})).toBe('Hello {{name}}');
  });

  it('leaves placeholders alone when no parameters are passed at all', () => {
    expect(service.t('wardrobe.greeting')).toBe('Hello {{name}}');
  });

  // `segments` is `t` cut at the placeholders instead of through them, so an
  // authored sentence can carry a content span without the key being split.
  // DECISIONS.md 213.
  describe('segments', () => {
    it('returns one authored run for a string with no placeholders', () => {
      expect(service.segments('wardrobe.title')).toEqual([{ text: 'Wardrobe', content: false }]);
    });

    it('returns the key itself, authored, when the key is missing', () => {
      expect(service.segments('nothing.here')).toEqual([{ text: 'nothing.here', content: false }]);
    });

    it('splits an authored sentence around a content value', () => {
      expect(service.segments('wardrobe.greeting', undefined, { name: 'Coral' })).toEqual([
        { text: 'Hello ', content: false },
        { text: 'Coral', content: true },
      ]);
    });

    it('keeps params authored and content marked in the same sentence', () => {
      expect(
        service.segments('spec.mixed', { condition: 'clear' }, { city: 'Tel Aviv-Yafo' }),
      ).toEqual([
        { text: 'It is ', content: false },
        { text: 'clear', content: false },
        { text: ' in ', content: false },
        { text: 'Tel Aviv-Yafo', content: true },
        { text: ' today', content: false },
      ]);
    });

    // The property the mechanism exists for: the split follows the placeholder,
    // not English word order, so a translation that leads with the name still
    // marks the name and only the name.
    it('marks a content value that leads the sentence', () => {
      expect(service.segments('spec.leading', undefined, { name: 'קורל' })).toEqual([
        { text: 'קורל', content: true },
        { text: ' — welcome back', content: false },
      ]);
    });

    it('leaves an unsupplied placeholder inside the authored run', () => {
      expect(service.segments('wardrobe.greeting')).toEqual([
        { text: 'Hello {{name}}', content: false },
      ]);
    });

    // Not left to object key order: a value the caller called content is
    // content, whatever else it was also passed as.
    it('lets content win when a name is in both dictionaries', () => {
      expect(
        service.segments('wardrobe.greeting', { name: 'params' }, { name: 'content' }),
      ).toEqual([
        { text: 'Hello ', content: false },
        { text: 'content', content: true },
      ]);
    });

    it('emits no empty run between adjacent placeholders', () => {
      expect(service.segments('spec.adjacent', { a: 'one' }, { b: 'two' })).toEqual([
        { text: 'one', content: false },
        { text: 'two', content: true },
      ]);
    });
  });
});

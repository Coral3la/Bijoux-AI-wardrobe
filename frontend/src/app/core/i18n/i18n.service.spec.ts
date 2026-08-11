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
});

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { I18nService } from '../../core/i18n/i18n.service';
import { AuthoredLine } from './authored-line';

// The table is this file's own and deliberately unlike `en.json`: if the
// component ever printed a hardcoded greeting instead of reading the key, these
// strings are what would catch it.
const TABLE = {
  'spec.greeting': 'Good evening, {{name}}',
  'spec.nameless': 'Good evening',
  'spec.mixed': 'It is {{condition}} in {{city}} today',
  'spec.leading': '{{name}} — welcome back',
};

let fixture: ComponentFixture<AuthoredLine>;
let mock: HttpTestingController;

async function render(inputs: {
  key: string;
  params?: Record<string, string | number>;
  content?: Record<string, string | number>;
}): Promise<HTMLElement> {
  fixture = TestBed.createComponent(AuthoredLine);
  fixture.componentRef.setInput('key', inputs.key);
  if (inputs.params !== undefined) {
    fixture.componentRef.setInput('params', inputs.params);
  }
  if (inputs.content !== undefined) {
    fixture.componentRef.setInput('content', inputs.content);
  }
  await fixture.whenStable();
  return fixture.nativeElement as HTMLElement;
}

function spans(host: HTMLElement): HTMLSpanElement[] {
  return [...host.querySelectorAll('span')];
}

describe('AuthoredLine', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    mock = TestBed.inject(HttpTestingController);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(TABLE);
    await loading;
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  // The load-bearing one. Every segment is a separate element, so the sentence
  // is only correct if no whitespace was introduced between them — one stray
  // space here and the greeting reads "Good evening,  Coral".
  it('renders the sentence exactly as the table wrote it', async () => {
    const host = await render({ key: 'spec.greeting', content: { name: 'Coral' } });

    expect(host.textContent).toBe('Good evening, Coral');
  });

  it('wraps only the content value in the content face', async () => {
    const host = await render({ key: 'spec.greeting', content: { name: 'Coral' } });

    const faced = spans(host).filter((span) => span.classList.contains('font-sans'));
    expect(faced.map((span) => span.textContent)).toEqual(['Coral']);
  });

  it('renders a sentence with no placeholders as one authored run', async () => {
    const host = await render({ key: 'spec.nameless' });

    expect(host.textContent).toBe('Good evening');
    expect(spans(host).some((span) => span.classList.contains('font-sans'))).toBe(false);
  });

  // Both dictionaries in one sentence: the condition is a word from our own
  // vocabulary and stays authored, the city came off a geocoder and does not.
  it('keeps params authored and content in the content face', async () => {
    const host = await render({
      key: 'spec.mixed',
      params: { condition: 'clear' },
      content: { city: 'Tel Aviv-Yafo' },
    });

    expect(host.textContent).toBe('It is clear in Tel Aviv-Yafo today');
    const faced = spans(host).filter((span) => span.classList.contains('font-sans'));
    expect(faced.map((span) => span.textContent)).toEqual(['Tel Aviv-Yafo']);
  });

  // The property the whole mechanism exists for: a key that opens with its
  // placeholder still wraps the right run. A Hebrew translation words the
  // greeting this way round and nothing else about the component changes.
  it('wraps a content value that leads the sentence', async () => {
    const host = await render({ key: 'spec.leading', content: { name: 'קורל' } });

    expect(host.textContent).toBe('קורל — welcome back');
    expect(spans(host)[0].classList.contains('font-sans')).toBe(true);
  });
});

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { OCCASIONS } from '../../shared/models/enums';
import { Weather } from '../../shared/models/weather.model';
import { LookDraft, LookRequestForm, forecastHorizon, todayInLocalTime } from './look-request-form';

let fixture: ComponentFixture<LookRequestForm>;
let mock: HttpTestingController;
let emitted: LookDraft[] = [];
let submits = 0;

function draft(overrides: Partial<LookDraft> = {}): LookDraft {
  return {
    occasion: 'casual',
    date: '2026-08-27',
    include_outerwear: null,
    notes: '',
    ...overrides,
  };
}

function weather(overrides: Partial<Weather> = {}): Weather {
  return {
    date: '2026-08-27',
    temp_min_c: 12,
    temp_max_c: 19,
    precip_mm: 0.2,
    wind_kph: 14,
    condition: 'partly_cloudy',
    rule: 'Outerwear optional.',
    ...overrides,
  };
}

async function render(
  initial: LookDraft = draft(),
  forecast: Weather | null = null,
): Promise<void> {
  fixture = TestBed.createComponent(LookRequestForm);
  fixture.componentRef.setInput('draft', initial);
  fixture.componentRef.setInput('weather', forecast);
  fixture.componentInstance.draftChanged.subscribe((next) => emitted.push(next));
  fixture.componentInstance.submitted.subscribe(() => submits++);
  await fixture.whenStable();
}

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function text(): string {
  return element().textContent ?? '';
}

function buttons(): HTMLButtonElement[] {
  return [...element().querySelectorAll('button')];
}

function buttonWith(label: string): HTMLButtonElement {
  return buttons().find((candidate) => candidate.textContent?.trim() === label)!;
}

function dateInput(): HTMLInputElement {
  return element().querySelector('input[type=date]')!;
}

function notes(): HTMLTextAreaElement {
  return element().querySelector('textarea')!;
}

async function press(label: string): Promise<void> {
  buttonWith(label).click();
  await fixture.whenStable();
}

describe('LookRequestForm', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    mock = TestBed.inject(HttpTestingController);
    emitted = [];
    submits = 0;

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

  it('renders one chip per occasion, from the shared vocabulary', async () => {
    await render();

    for (const occasion of OCCASIONS) {
      expect(text()).toContain(en[`vocabulary.occasion.${occasion}` as keyof typeof en]);
    }
  });

  it('marks the chosen occasion and emits the next one', async () => {
    await render(draft({ occasion: 'work' }));

    expect(buttonWith('Work').getAttribute('aria-pressed')).toBe('true');
    expect(buttonWith('Evening').getAttribute('aria-pressed')).toBe('false');

    await press('Evening');
    expect(emitted).toEqual([draft({ occasion: 'evening' })]);
  });

  // The category chips clear when tapped again; these cannot. The request has
  // no "no occasion", so a second tap has to leave the choice standing rather
  // than arm a button that would 422.
  it('keeps the occasion when the chosen chip is tapped again', async () => {
    await render(draft({ occasion: 'work' }));

    await press('Work');
    expect(emitted).toEqual([draft({ occasion: 'work' })]);
  });

  it('carries the coat override as the endpoint spells it', async () => {
    await render();

    expect(buttonWith('Auto').getAttribute('aria-pressed')).toBe('true');

    await press('Yes');
    await press('No');
    expect(emitted.map((next) => next.include_outerwear)).toEqual([true, false]);
  });

  it('emits the date the picker was set to', async () => {
    await render();

    dateInput().value = '2026-09-01';
    dateInput().dispatchEvent(new Event('change'));
    await fixture.whenStable();

    expect(emitted).toEqual([draft({ date: '2026-09-01' })]);
  });

  // A cleared date input is not a date, and emitting '' would send one to a
  // schema that answers 422 for it.
  it('emits nothing when the date is cleared', async () => {
    await render();

    dateInput().value = '';
    dateInput().dispatchEvent(new Event('change'));
    await fixture.whenStable();

    expect(emitted).toEqual([]);
  });

  // The horizon 04-API-SPEC.md measured, transcribed rather than derived: an
  // expectation read from the constant it guards would move with it.
  it('bounds the picker at the forecast horizon', async () => {
    await render();

    const max = new Date();
    max.setDate(max.getDate() + 15);
    expect(dateInput().getAttribute('max')).toBe(todayInLocalTime(max));
    expect(dateInput().getAttribute('max')).toBe(forecastHorizon());
  });

  it('emits the notes as they are typed', async () => {
    await render();

    notes().value = 'meeting with a client';
    notes().dispatchEvent(new Event('input'));
    await fixture.whenStable();

    expect(emitted).toEqual([draft({ notes: 'meeting with a client' })]);
  });

  it('prints both temperatures and the condition above the button', async () => {
    await render(draft(), weather());

    expect(text()).toContain('12–19°C · Partly cloudy');
  });

  // Absent rather than apologetic: an account with no home location has no
  // forecast to print, and the suggest request is what says so.
  it('prints nothing when there is no forecast', async () => {
    await render(draft(), null);

    expect(text()).not.toContain('°C');
  });

  it('asks for a look on submit', async () => {
    await render();

    element().querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    expect(submits).toBe(1);
  });

  // Inside a form an untyped button submits it. Picking an occasion is not
  // asking for a look, and neither is choosing a coat.
  it('does not submit when a chip is pressed', async () => {
    await render();

    await press('Evening');
    await press('Yes');

    expect(submits).toBe(0);
  });
});

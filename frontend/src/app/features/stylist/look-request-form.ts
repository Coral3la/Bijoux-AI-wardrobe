import { ChangeDetectionStrategy, Component, inject, input, output } from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';
import { OCCASIONS, Occasion } from '../../shared/models/enums';
import { Weather } from '../../shared/models/weather.model';

// Transcribed from 04-API-SPEC.md, which measured it against the provider on
// 2026-08-26: `today + 15`, sixteen days counting today. It bounds the date
// input so the commonest `forecast_unavailable` never has to be explained —
// this is the documented contract, not a narrowing of it. There is deliberately
// no lower bound: nothing in the docs refuses a past date, and inventing a
// floor here would be this screen deciding something no document has.
const FORECAST_HORIZON_DAYS = 15;

// What the four controls hold, named for the wire wherever the wire has a name
// (DECISIONS.md 059's rule applied to a shape that never goes on it). The
// coat override is `boolean | null` rather than an Auto/Yes/No vocabulary of
// its own, because `null` is already what 04-API-SPEC.md means by "let the
// weather rule decide" — a third word here would be a third thing to keep in
// step with the endpoint.
export interface LookDraft {
  readonly occasion: Occasion;
  readonly date: string;
  readonly include_outerwear: boolean | null;
  readonly notes: string;
}

// Local, not UTC. `toISOString().slice(0, 10)` is the shorter spelling and it
// is wrong for half the world for part of every day: it would open the picker
// on yesterday in Tel Aviv before 03:00 and on tomorrow in Los Angeles after
// 17:00. The date the user means is the one on their own wall.
export function todayInLocalTime(now = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

export function forecastHorizon(now = new Date()): string {
  const horizon = new Date(now);
  horizon.setDate(horizon.getDate() + FORECAST_HORIZON_DAYS);
  return todayInLocalTime(horizon);
}

@Component({
  selector: 'app-look-request-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- A real form, so the return key submits from the date and notes fields
         the way it does on login. The occasion and coat controls are buttons
         with type="button" for the same reason: inside a form an untyped
         button submits it, and picking "Evening" is not asking for a look. -->
    <form class="flex flex-col gap-6" (submit)="submit($event)">
      <fieldset class="flex flex-col gap-2">
        <legend class="text-sm font-medium">{{ i18n.t('stylist.occasion.legend') }}</legend>
        <!-- Scrolls rather than wraps, and nothing scrolls it for the user, for
             the reason filter-bar.ts records: scrollIntoView is undefined in
             jsdom. Six chips fit a phone where the wardrobe's nine did not. -->
        <div class="flex flex-nowrap items-center gap-2 overflow-x-auto pb-1">
          @for (occasion of occasions; track occasion) {
            <button
              type="button"
              [attr.aria-pressed]="draft().occasion === occasion"
              (click)="chooseOccasion(occasion)"
              [class]="chipClass(draft().occasion === occasion)"
            >
              {{ i18n.t('vocabulary.occasion.' + occasion) }}
            </button>
          }
        </div>
      </fieldset>

      <div class="flex flex-col gap-2">
        <label for="look-date" class="text-sm font-medium">
          {{ i18n.t('stylist.date.label') }}
        </label>
        <input
          id="look-date"
          type="date"
          [value]="draft().date"
          [max]="horizon"
          (change)="chooseDate($event)"
          class="min-h-11 rounded-md bg-surface px-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        />
      </div>

      <fieldset class="flex flex-col gap-2">
        <legend class="text-sm font-medium">{{ i18n.t('stylist.coat.legend') }}</legend>
        <div class="flex items-center gap-2">
          @for (choice of coatChoices; track choice.key) {
            <button
              type="button"
              [attr.aria-pressed]="draft().include_outerwear === choice.value"
              (click)="chooseCoat(choice.value)"
              [class]="chipClass(draft().include_outerwear === choice.value)"
            >
              {{ i18n.t(choice.key) }}
            </button>
          }
        </div>
      </fieldset>

      <div class="flex flex-col gap-2">
        <label for="look-notes" class="text-sm font-medium">
          {{ i18n.t('stylist.notes.label') }}
        </label>
        <textarea
          id="look-notes"
          rows="3"
          [value]="draft().notes"
          [placeholder]="i18n.t('stylist.notes.placeholder')"
          (input)="changeNotes($event)"
          class="rounded-md bg-surface p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        ></textarea>
      </div>

      <!-- Above the button, where 05-FRONTEND-SPEC.md's mockup puts it: it is
           the last thing read before committing to a day. Absent rather than
           apologetic when there is no forecast — see StylistStore.loadWeather. -->
      @if (weather(); as forecast) {
        <p class="text-sm">{{ weatherLine(forecast) }}</p>
      }

      <button
        type="submit"
        class="min-h-11 rounded-md bg-accent px-4 text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('stylist.submit') }}
      </button>
    </form>
  `,
})
export class LookRequestForm {
  protected readonly i18n = inject(I18nService);

  // The draft is the page's, not this component's, and that is what makes a
  // rejected request survivable: the form is unmounted while the skeleton is
  // up, and state held here would take the user's notes down with it every
  // time the endpoint answered 400. Same arrangement as FilterBar, for a
  // different reason — there it was one owner for the URL, here it is one
  // owner that outlives the control.
  readonly draft = input.required<LookDraft>();
  readonly weather = input<Weather | null>(null);

  readonly draftChanged = output<LookDraft>();
  readonly submitted = output<void>();

  protected readonly occasions = OCCASIONS;
  protected readonly horizon = forecastHorizon();

  protected readonly coatChoices = [
    { key: 'stylist.coat.auto', value: null },
    { key: 'stylist.coat.yes', value: true },
    { key: 'stylist.coat.no', value: false },
  ] as const;

  // Both temperatures, not one. `build_rule` reads the maximum (DECISIONS.md
  // 142) but a person dressing reads the span — 12 to 19 is a different day
  // from 18 to 19 under the same "partly cloudy".
  protected weatherLine(weather: Weather): string {
    return this.i18n.t('stylist.weather', {
      min: Math.round(weather.temp_min_c),
      max: Math.round(weather.temp_max_c),
      condition: this.i18n.t(`vocabulary.condition.${weather.condition}`),
    });
  }

  protected chipClass(selected: boolean): string {
    const base =
      'min-h-11 shrink-0 rounded-full px-4 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
    return selected ? `${base} bg-accent text-surface` : `${base} bg-surface`;
  }

  // Not single-valued the way the category chips are: tapping the selected
  // occasion again leaves it selected, because the request has no "no
  // occasion" to fall back to. The filter bar could clear to "All"; this
  // cannot, and a chip row with nothing chosen would arm a button that 422s.
  protected chooseOccasion(occasion: Occasion): void {
    this.draftChanged.emit({ ...this.draft(), occasion });
  }

  protected chooseDate(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    // An empty date input is a cleared field, not a date. Dropped rather than
    // emitted, so the picker falls back to the day it was opened on instead of
    // sending `date: ""` and collecting a 422 for it.
    if (value !== '') {
      this.draftChanged.emit({ ...this.draft(), date: value });
    }
  }

  protected chooseCoat(include_outerwear: boolean | null): void {
    this.draftChanged.emit({ ...this.draft(), include_outerwear });
  }

  protected changeNotes(event: Event): void {
    this.draftChanged.emit({ ...this.draft(), notes: (event.target as HTMLTextAreaElement).value });
  }

  protected submit(event: Event): void {
    event.preventDefault();
    this.submitted.emit();
  }
}

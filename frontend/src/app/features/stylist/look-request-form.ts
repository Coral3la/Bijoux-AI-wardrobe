import { ChangeDetectionStrategy, Component, inject, input, output } from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';
import { OCCASIONS, Occasion } from '../../shared/models/enums';

// Transcribed from 04-API-SPEC.md, which measured it against the provider on
// 2026-08-26: `today + 15`, sixteen days counting today. It bounds the date
// input so the commonest `forecast_unavailable` never has to be explained —
// this is the documented contract, not a narrowing of it. There is deliberately
// no lower bound: nothing in the docs refuses a past date, and inventing a
// floor here would be this screen deciding something no document has.
const FORECAST_HORIZON_DAYS = 15;

// The second copy of this pair, and the one that turns the duplication into a
// standing cost rather than a one-off. `filter-bar.ts` carries the same two
// constants for the same reason: the shared `appChip` directive sets its font
// size in the base string every variant shares, so 11px cannot be reached from
// a call site. Two converted screens now draw an identical chip from two
// declarations; the third screen to need it should convert the directive
// instead of copying this again. DECISIONS.md 219, 220.
const CHIP =
  'inline-flex min-h-11 shrink-0 items-center rounded-full border px-4 text-[11px] font-medium tracking-[0.18em] uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
const CHIP_STATES = {
  inactive: 'border-line text-ink-muted',
  active: 'border-ink bg-ink text-canvas',
} as const;

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
         button submits it, and picking "Evening" is not asking for a look.

         The stone panel is what makes this read as a standing control rather
         than a step. It is on screen under the look now, and a form drawn
         straight onto the canvas beneath a result reads as leftover rather than
         as the thing that produced it. DECISIONS.md 220. -->
    <form class="flex flex-col gap-4 rounded-sm bg-surface-elevated p-6" (submit)="submit($event)">
      <!-- Two dimensions on one row wherever there is width for them: occasion
           and coat are both short chip rows, and pairing them is what gets the
           whole control down to three bands from five. -->
      <div class="grid gap-4 md:grid-cols-2">
        <fieldset class="flex flex-col gap-2">
          <legend class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase">
            {{ i18n.t('stylist.occasion.legend') }}
          </legend>
          <!-- Wrapping, where 1.8's row scrolled: nothing ever scrolled it for
               the user, and the Atelier chip is small enough that six of them
               wrap to two lines on a phone.

               aria-pressed is bound here rather than left to appChip, which
               this row no longer uses. One expression paints and announces, so
               there is nothing for the two to drift apart over. -->
          <div class="flex flex-wrap items-center gap-1.5">
            @for (occasion of occasions; track occasion) {
              <button
                type="button"
                [attr.aria-pressed]="draft().occasion === occasion"
                [class]="chipClass(draft().occasion === occasion)"
                (click)="chooseOccasion(occasion)"
              >
                {{ i18n.t('vocabulary.occasion.' + occasion) }}
              </button>
            }
          </div>
        </fieldset>

        <fieldset class="flex flex-col gap-2">
          <legend class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase">
            {{ i18n.t('stylist.coat.legend') }}
          </legend>
          <div class="flex flex-wrap items-center gap-1.5">
            @for (choice of coatChoices; track choice.key) {
              <button
                type="button"
                [attr.aria-pressed]="draft().include_outerwear === choice.value"
                [class]="chipClass(draft().include_outerwear === choice.value)"
                (click)="chooseCoat(choice.value)"
              >
                {{ i18n.t(choice.key) }}
              </button>
            }
          </div>
        </fieldset>
      </div>

      <div class="flex flex-col gap-2">
        <label
          for="look-date"
          class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase"
          >{{ i18n.t('stylist.date.label') }}</label
        >
        <input
          id="look-date"
          type="date"
          [value]="draft().date"
          [max]="horizon"
          (change)="chooseDate($event)"
          class="min-h-11 rounded-sm border border-line bg-canvas px-3 py-2 text-sm focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        />
      </div>

      <div class="flex flex-col gap-2">
        <label
          for="look-notes"
          class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase"
          >{{ i18n.t('stylist.notes.label') }}</label
        >
        <textarea
          id="look-notes"
          rows="2"
          [value]="draft().notes"
          [placeholder]="i18n.t('stylist.notes.placeholder')"
          (input)="changeNotes($event)"
          class="rounded-sm border border-line bg-canvas px-3 py-2 text-sm focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        ></textarea>
      </div>

      <!-- The label is the parent's, because only the parent knows whether a
           look is on screen: this is "Style me" on an empty screen and "Change
           and restyle" under a result, and both press the same flow. The form
           has no opinion about which, and holding one here would mean giving
           the form a second input that says the same thing as the first.
           DECISIONS.md 220. -->
      <button
        type="submit"
        class="ms-auto inline-flex min-h-11 items-center gap-x-2 rounded-full border border-ink bg-ink px-6 text-[11px] font-medium tracking-[0.22em] text-canvas uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t(submitLabel()) }}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="h-3 w-3"
          aria-hidden="true"
        >
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
      </button>
    </form>
  `,
})
export class LookRequestForm {
  protected readonly i18n = inject(I18nService);

  // The draft is the page's, not this component's. That was load-bearing until
  // DR.20, when the form stopped unmounting: state held here used to go down
  // with the skeleton and take the user's notes with it. It stays the page's
  // because the page is what composes the request and what decides the submit
  // label from the look — one owner, still, for a different reason.
  readonly draft = input.required<LookDraft>();
  // An i18n key rather than a rendered string, so the form keeps its one rule
  // about strings: everything it prints, it looks up.
  readonly submitLabel = input('stylist.submit');

  readonly draftChanged = output<LookDraft>();
  readonly submitted = output<void>();

  protected readonly occasions = OCCASIONS;
  protected readonly horizon = forecastHorizon();

  protected readonly coatChoices = [
    { key: 'stylist.coat.auto', value: null },
    { key: 'stylist.coat.yes', value: true },
    { key: 'stylist.coat.no', value: false },
  ] as const;

  protected chipClass(active: boolean): string {
    return `${CHIP} ${active ? CHIP_STATES.active : CHIP_STATES.inactive}`;
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

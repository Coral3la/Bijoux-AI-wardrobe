import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { TripsApi } from '../../core/api/trips.api';
import { I18nService } from '../../core/i18n/i18n.service';
import { Condition } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';
import { Look } from '../../shared/models/look.model';
import { TripDay, TripDetail } from '../../shared/models/trip.model';
import { ItemCard } from '../wardrobe/item-card';
import { PackingList } from './packing-list';

// Local to this screen rather than in `enums.ts`, which mirrors `app/enums.py`
// value for value: a glyph has no counterpart on the server and never will.
// Every one of them is decoration — `aria-hidden` in the template, with the
// condition's own `vocabulary.condition.*` string carrying the meaning — so a
// reader who gets no emoji loses nothing.
const CONDITION_GLYPH: Readonly<Record<Condition, string>> = {
  clear: '☀',
  partly_cloudy: '⛅',
  cloudy: '☁',
  fog: '🌫',
  drizzle: '🌦',
  rain: '🌧',
  snow: '❄',
  thunderstorm: '⛈',
};

// Two branches and no table, unlike the pack path's seven. `GET /trips/{id}`
// documents one code of its own — 404 `not_found`, which is the same answer for
// another account's trip as for one that never existed — and `401` is the
// interceptor's, which redirects before this ever runs.
export function tripLoadErrorKey(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const code = (error.error as { code?: string } | null)?.code;
    // The status is read beside the code, and only here: a 404 that never
    // reached the application carries no body to hold one, and it is the same
    // fact about the same URL. A malformed id is FastAPI's 422 rather than a
    // 404 — the path parameter is typed as a UUID — and falls to the general
    // message, which 04-API-SPEC.md's failure list does not mention.
    if (code === 'not_found' || error.status === 404) {
      return 'trip.error.notFound';
    }
  }
  return 'trip.error.load';
}

@Component({
  selector: 'app-trip-detail-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ItemCard, PackingList, RouterLink],
  template: `
    <main class="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <!-- Outside every branch below, which is what the error states need: a
           trip that does not load leaves this screen with nothing on it, and a
           back link inside the loaded branch would strand the user on the
           message. It is the fifth bespoke navigation control in this project
           and AUDITS.md O-29 counts it. -->
      <a
        routerLink="/wardrobe"
        class="inline-flex min-h-11 items-center self-start text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('trip.back') }}
      </a>

      @if (detail(); as loaded) {
        <header class="flex flex-col gap-1">
          <!-- Body face, not font-display. The destination is a place name off
               the geocoder, and Fraunces is latin-subset, so a non-Latin one
               would fall back per character and render in two faces on one
               line. DECISIONS.md 071 names this screen. -->
          <h1 class="text-3xl">{{ loaded.trip.destination }}</h1>
          <p class="text-sm">
            {{
              i18n.t('trip.view.dates', {
                start: loaded.trip.start_date,
                end: loaded.trip.end_date,
              })
            }}
          </p>
          <!-- The line the feature lands on, and it is here rather than under
               the packing list where 05-FRONTEND-SPEC.md first drew it: the
               counts are the confirmation sentence 4.5 already wrote, word for
               word, and splitting one sentence across two ends of a screen
               costs more than either placement gains. -->
          <p class="text-sm font-medium">{{ headerLine() }}</p>
        </header>

        <!-- Buttons with aria-pressed rather than a tablist, matching the
             occasion chips one screen over. A real tablist owes the reader
             arrow-key roving and a tabpanel relationship; this is a filter over
             one region, which is what the chips are too. -->
        <div
          class="flex flex-nowrap gap-2 overflow-x-auto pb-1"
          role="group"
          [attr.aria-label]="i18n.t('trip.view.days')"
        >
          @for (day of loaded.trip.days; track day.day) {
            <button
              type="button"
              (click)="select(day.day)"
              [attr.aria-pressed]="selectedDay() === day.day"
              [class]="tabClass(selectedDay() === day.day)"
            >
              <span class="block text-sm font-medium">
                {{ i18n.t('trip.day.legend', { day: day.day }) }}
              </span>
              <span class="block text-xs">{{ day.date }}</span>
              <span class="block text-lg" aria-hidden="true">{{ glyph(day) }}</span>
              <span class="block text-sm">
                {{ i18n.t('trip.view.temp', { temp: temperature(day) }) }}
              </span>
              <!-- The glyph above is decoration, so the condition is named
                   here or it is named nowhere. -->
              <span class="sr-only">{{ i18n.t('vocabulary.condition.' + day.condition) }}</span>
            </button>
          }
        </div>

        @if (selectedLook(); as look) {
          <article class="flex flex-col gap-4 rounded-lg bg-surface p-5">
            <!-- Body face again, one rule further: the title is written by the
                 model. The look card applies it at the same heading. -->
            <h2 class="text-2xl">{{ look.title }}</h2>

            <!-- In the order the server sent, which is look_items.position and
                 therefore the model's own — the saved list's arrangement, not
                 the look card's layer grouping. The card groups because it is
                 read as an outfit being assembled; this one sits under a day
                 tab and is read as what that day looks like. -->
            <ul class="grid grid-cols-4 gap-2">
              @for (item of look.items; track item.id) {
                <li><app-item-card [item]="item" /></li>
              }
            </ul>

            <p class="text-sm">{{ look.reasoning }}</p>
            <p class="text-sm">{{ look.weather_note }}</p>
          </article>
        } @else {
          <!-- A day with no look, which is a real state rather than an error:
               a repack detaches a look that was saved, rated or worn instead of
               deleting it, and the day it belonged to keeps its forecast and
               loses its outfit. AUDITS.md O-32, DECISIONS.md 200. -->
          <p class="rounded-lg bg-surface p-5 text-sm text-current/70">
            {{ i18n.t('trip.view.day.noLook') }}
          </p>
        }

        <app-packing-list [items]="packingItems()" />
      } @else if (errorKey(); as key) {
        <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
      } @else {
        <p class="text-sm" role="status" aria-live="polite">{{ i18n.t('trip.view.loading') }}</p>
      }
    </main>
  `,
})
export class TripDetailPage {
  protected readonly i18n = inject(I18nService);
  private readonly api = inject(TripsApi);

  // The snapshot, as item detail reads it: nothing changes the id under this
  // component, because every route into it is a fresh navigation — from the
  // form after a pack, or from the address bar.
  private readonly id = inject(ActivatedRoute).snapshot.paramMap.get('id') ?? '';

  protected readonly detail = signal<TripDetail | null>(null);
  protected readonly errorKey = signal<string | null>(null);

  // The ordinal, not the index, because that is what the day carries and what
  // the join is keyed by. Day 1 on arrival even when day 1 has no look: the
  // strip is the trip's calendar, and an opening selection that depended on
  // which days happened to keep a look would leave the user working out why
  // day 3 is the one lit up.
  protected readonly selectedDay = signal(1);

  private readonly looksById = computed(() => {
    const looks = new Map<string, Look>();
    for (const look of this.detail()?.looks ?? []) {
      looks.set(look.id, look);
    }
    return looks;
  });

  // Every item the response carries, from the looks alone: the trip object
  // holds ids and no rows, and 04-API-SPEC.md's own acceptance criterion is
  // that every packed item appears in at least one look. This map is what makes
  // the packing list and the reuse clause renderable without a second request.
  private readonly itemsById = computed(() => {
    const items = new Map<string, Item>();
    for (const look of this.detail()?.looks ?? []) {
      for (const item of look.items) {
        items.set(item.id, item);
      }
    }
    return items;
  });

  protected readonly selectedLook = computed(() => {
    const day = this.detail()?.trip.days.find((candidate) => candidate.day === this.selectedDay());
    // Two ways to have no look and one rendering: the day carries null, or it
    // carries an id the response did not hydrate. The second cannot happen from
    // this endpoint and the type permits it, so it is folded into the first
    // rather than given a branch that could never be reached.
    return day?.look_id === undefined || day.look_id === null
      ? null
      : (this.looksById().get(day.look_id) ?? null);
  });

  // Ids that hydrate to nothing are dropped rather than rendered as a blank
  // row. It takes a detached look to produce one — the item is still packed and
  // the row describing it left with the look — and a checkbox beside no name is
  // not something a user can act on.
  protected readonly packingItems = computed<readonly Item[]>(() => {
    const items = this.itemsById();
    return (this.detail()?.trip.packing_list.item_ids ?? [])
      .map((id) => items.get(id))
      .filter((item): item is Item => item !== undefined);
  });

  // The counts, then the reuse clause when there is one to make. Composed
  // through a key rather than joined with a separator in code, so the character
  // between the two clauses is a translator's to change.
  protected readonly headerLine = computed(() => {
    const summary = this.detail()?.trip.packing_list.reuse_summary;
    if (summary === undefined) {
      return '';
    }

    // Pluralised on the looks alone, which is 4.5's reading unchanged:
    // item_count cannot be one, because a wearable look is at least a top, a
    // bottom and shoes, whereas a one-day trip really does pack one look.
    const counts =
      summary.look_count === 1
        ? this.i18n.t('trip.packed.counts.one', { items: summary.item_count })
        : this.i18n.t('trip.packed.counts.other', {
            items: summary.item_count,
            looks: summary.look_count,
          });

    const reuse = this.reuseClause();
    return reuse === null ? counts : this.i18n.t('trip.view.headerLine', { counts, reuse });
  });

  constructor() {
    this.api.get(this.id).subscribe({
      next: (detail) => this.detail.set(detail),
      error: (failure: unknown) => this.errorKey.set(tripLoadErrorKey(failure)),
    });
  }

  protected select(day: number): void {
    this.selectedDay.set(day);
  }

  // The day's high, which is what this project already means by "the
  // temperature": the weather strip prints it, summarize_forecast prints it to
  // the model, and DECISIONS.md 142 settled it there. temp_min_c is on the wire
  // and goes unrendered, because a tab wide enough for a range is a tab that
  // fits three days on a phone.
  protected temperature(day: TripDay): number {
    return Math.round(day.temp_max_c);
  }

  protected glyph(day: TripDay): string {
    return CONDITION_GLYPH[day.condition];
  }

  protected tabClass(selected: boolean): string {
    const base =
      'min-h-11 shrink-0 rounded-lg px-4 py-2 text-center focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
    return selected ? `${base} bg-accent text-surface` : `${base} bg-surface`;
  }

  // Three ways to have no clause and one answer to all of them: nothing is worn
  // twice, the garment was never named, or the look that wore it was detached
  // and its row left with it. The alternative is a sentence reading "You'll
  // wear Untitled item on 3 days", which names nothing and takes the header
  // line with it.
  private reuseClause(): string | null {
    const reused = this.detail()?.trip.packing_list.reuse_summary.most_reused;
    if (reused === undefined || reused === null) {
      return null;
    }
    const name = this.itemsById().get(reused.item_id)?.display_name;
    if (name === undefined || name === null) {
      return null;
    }
    // "wear" rather than the specification's "appear", and that is the whole
    // reason for the rewording: display_name is written by the model and its
    // grammatical number is unknowable here, so "the jeans appear" and "the
    // blazer appears" cannot both come out of one template. The verb after
    // "you'll" is invariant.
    return this.i18n.t('trip.view.reuse', { name, days: reused.days });
  }
}

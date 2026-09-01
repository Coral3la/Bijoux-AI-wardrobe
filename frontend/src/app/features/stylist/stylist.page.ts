import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { ItemsApi } from '../../core/api/items.api';
import { I18nService } from '../../core/i18n/i18n.service';
import { LooksStore } from '../../core/state/looks.store';
import { StylistStore } from '../../core/state/stylist.store';
import { WardrobeStore } from '../../core/state/wardrobe.store';
import { roleOf } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';
import { Feedback, Look, SuggestRequest } from '../../shared/models/look.model';
import { Weather } from '../../shared/models/weather.model';
import { Skeleton } from '../../shared/ui/skeleton';
import { LookCard } from './look-card';
import { LookDraft, LookRequestForm, todayInLocalTime } from './look-request-form';

// Three lines for a four-to-eight second wait, so the last one is reached at
// six and rested on. 05-FRONTEND-SPEC.md names the first two; the third is the
// step between them and the answer.
const STATUS_KEYS = [
  'stylist.waiting.forecast',
  'stylist.waiting.wardrobe',
  'stylist.waiting.assembling',
] as const;

export const STATUS_INTERVAL_MS = 2000;

// The strip's own shape, four tiles across — a skeleton of the thing being
// built rather than a spinner, which is what §2.8 asks for and what makes the
// wait read as progress. It was five while the card grouped by layer and laid
// them out three to a row; the Ritual strip is four columns, so this is four.
// DECISIONS.md 220.
const SKELETON_TILES = [0, 1, 2, 3] as const;

// All three optionals are omitted rather than sent as null. Absent is already
// what the endpoint defaults them to — `include_outerwear: null` is "let the
// weather rule decide" — and an omitted key cannot collide with the schema's
// extra-field rejection. Same spread-conditional idiom as the wardrobe store's
// `normalise`, for the same reason: the object carries only what it means.
function toRequest(draft: LookDraft, anchor: Item | null): SuggestRequest {
  const notes = draft.notes.trim();
  return {
    occasion: draft.occasion,
    date: draft.date,
    ...(draft.include_outerwear !== null && { include_outerwear: draft.include_outerwear }),
    ...(notes !== '' && { notes }),
    // The UUID, which is the only id this client ever holds. The anchor is the
    // whole garment rather than the id because the pin has to name it.
    ...(anchor !== null && { anchor_item_id: anchor.id }),
  };
}

@Component({
  selector: 'app-stylist-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LookCard, LookRequestForm, Skeleton],
  template: `
    <main class="mx-auto flex w-full max-w-4xl flex-col gap-region px-6 pt-hero pb-region">
      <!-- The dateline that stood above this heading is gone with the branch
           chain. It printed "Today · 1 September" over a forecast line that now
           sits beside it and says the same word, and 211 built a formatter for
           nineteen English month and weekday names that reached the screen from
           outside the string table. The screen loses a fact the date picker two
           rows down already carries. DECISIONS.md 211, 220. -->
      <header
        class="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 border-b border-line pb-4"
      >
        <h1 class="font-display text-[40px] leading-none font-light tracking-[-0.02em] md:text-5xl">
          {{ i18n.t('stylist.title') }}
        </h1>
        <!-- The forecast, moved out of the form. It is context for the whole
             screen rather than the last thing read before pressing the button,
             and the form is now permanent, so a line inside it would sit above
             a look it had already been used to ask for.

             Two elements and one rule, the same as the wardrobe strip: the
             condition is a word out of our closed vocabulary and takes the
             authored face, the reading is a number and takes the mono one. The
             dot that joins them is in the string table with the degrees,
             because it is punctuation rather than a separator this template
             invented. DECISIONS.md 218, 220. -->
        @if (store.weather(); as forecast) {
          <p
            class="flex flex-wrap items-baseline gap-x-2 font-prose text-[15px] text-ink-muted italic"
          >
            <span>{{ conditionLine(forecast) }}</span>
            <span class="font-mono text-[13px] text-ink tabular-nums not-italic">
              {{ readingLine(forecast) }}
            </span>
          </p>
        }
      </header>

      <!-- Pinned above the form, where 05-FRONTEND-SPEC.md puts it. It is not
           one of the form's controls: the four in LookDraft are what the user
           sets here, and the anchor is what she arrived carrying.

           Grouped with the form rather than left a sibling of <main>: the pin
           states what the form below it will build around, and at region
           distance the two read as unrelated. DECISIONS.md 212. -->
      <div class="flex flex-col gap-group">
        @if (anchor(); as item) {
          <div class="flex items-center gap-3 rounded-sm border border-line p-3">
            <p class="font-prose text-base text-ink-muted italic">
              {{ i18n.t('stylist.anchor.pinned', { item: name(item) }) }}
            </p>
            <button
              type="button"
              (click)="clearAnchor()"
              [attr.aria-label]="i18n.t('stylist.anchor.clear')"
              class="ms-auto min-h-11 min-w-11 rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              ×
            </button>
          </div>
        }

        <!-- Always on screen, which is the whole of the Ritual direction and the
             one behaviour change in it: the form was swapped out for the
             skeleton and then for the look, so every reroll began by getting the
             controls back. It stays, and the label under it is what changes.
             DECISIONS.md 220. -->
        <app-look-request-form
          [draft]="draft()"
          [submitLabel]="submitLabel()"
          (draftChanged)="onDraftChanged($event)"
          (submitted)="suggest()"
        />
      </div>

      <!-- One error line for the whole screen, where there were two. Both
           stores are read. Until 3.3 this read StylistStore alone, which meant a
           failed heart tap rolled the control back and said nothing at all —
           found by the rollback test one task later. -->
      @if (cardError(); as key) {
        <p class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
      }

      @if (store.isSuggesting()) {
        <section class="flex flex-col gap-group">
          <div class="grid grid-cols-2 gap-x-3 gap-y-5 md:grid-cols-4" aria-hidden="true">
            @for (tile of tiles; track tile) {
              <app-skeleton class="aspect-4/5" radius="rounded-[2px]" />
            }
          </div>
          <!-- The status line is the accessible name of the wait: the tiles
               above it are decoration and say so. aria-live so the cycling is
               announced rather than silently replaced under a screen reader. -->
          <p class="font-prose text-base text-ink-muted italic" role="status" aria-live="polite">
            {{ i18n.t(statusKey()) }}
          </p>
        </section>
      } @else if (look(); as look) {
        <app-look-card
          [look]="look"
          [missingPieces]="missingPieces()"
          [message]="message()"
          [swappingItemId]="store.swappingItemId()"
          [busy]="looksStore.updatingId() === look.id"
          (tryAgain)="startOver()"
          (swap)="swapItem($event)"
          (save)="toggleSaved(look)"
          (rated)="rate(look, $event)"
        />
      } @else {
        <!-- The third state, and it is a sentence rather than an empty region.
             Nothing has been asked for yet, or the last look has just been
             cleared; either way the form above is the whole of what to do next,
             so this says so and gets out of the way. -->
        <p class="py-16 text-center font-prose text-[17px] text-ink-muted italic">
          {{ i18n.t('stylist.ready') }}
        </p>
      }
    </main>
  `,
})
export class StylistPage {
  protected readonly i18n = inject(I18nService);
  protected readonly store = inject(StylistStore);
  protected readonly looksStore = inject(LooksStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly items = inject(ItemsApi);
  private readonly wardrobe = inject(WardrobeStore);

  protected readonly tiles = SKELETON_TILES;

  // The garment "Style around this" arrived with, or null. Held here rather
  // than in the draft for the same reason the draft is held here rather than in
  // the form: it outlives the control that renders it, and the skeleton
  // unmounts that control on every submit.
  protected readonly anchor = signal<Item | null>(null);

  // Every garment rejected on this look, oldest first. Held beside the anchor
  // rather than in the draft for the same reason: it is not something the form
  // asks for, and it outlives the card that produced it by exactly one request.
  protected readonly excluded = signal<readonly string[]>([]);

  // Casual and today, which is the request a user who touches nothing else
  // sends. `include_outerwear: null` is Auto — the weather rule decides, which
  // is the whole point of having built one.
  protected readonly draft = signal<LookDraft>({
    occasion: 'casual',
    date: todayInLocalTime(),
    include_outerwear: null,
    notes: '',
  });

  private readonly statusIndex = signal(0);
  private timer: ReturnType<typeof setInterval> | null = null;

  protected readonly statusKey = computed(() => STATUS_KEYS[this.statusIndex()]);
  // The suggested look, unless the heart has since written to it. StylistStore
  // holds what the stylist answered and LooksStore holds what PATCH answered,
  // and neither can hand the other a look — so the newer of the two wins here,
  // matched by id. Without this the heart fills in and empties again on the
  // next change detection, because `result()` still says is_saved: false.
  protected readonly look = computed<Look | null>(() => {
    const suggested = this.store.result()?.looks[0] ?? null;
    const updated = this.looksStore.updated();
    if (suggested !== null && updated !== null && updated.id === suggested.id) {
      return updated;
    }
    return suggested;
  });
  // Whichever store failed. At most one is ever set: each clears its own at the
  // start of a request, and the two paths that do not — a swap or a new
  // suggestion, which cannot clear an error they know nothing about — call
  // `looksStore.clearError()` themselves. So the order here decides nothing,
  // which is the point: with both live it would be picking on no principle.
  protected readonly cardError = computed(() => this.store.error() ?? this.looksStore.error());
  protected readonly message = computed(() => this.store.result()?.message ?? '');

  // The form is permanent now, so the button under it has to say which of two
  // things it does. It is the same flow either way — a look on screen is not
  // invalidated by a field changing under it, and nothing re-requests until
  // this is pressed. DECISIONS.md 220.
  protected readonly submitLabel = computed(() =>
    this.look() === null ? 'stylist.submit' : 'stylist.submit.restyle',
  );
  protected readonly missingPieces = computed(() => this.store.result()?.missing_pieces ?? []);

  constructor() {
    // Reset first, then load: this store is providedIn: 'root' and a second
    // visit arrives holding the first visit's look and forecast.
    this.store.reset();
    this.looksStore.reset();
    this.store.loadWeather(this.draft().date);
    this.readAnchor();

    effect(() => {
      if (this.store.isSuggesting()) {
        this.startStatusCycle();
      } else {
        this.stopStatusCycle();
      }
    });

    // The interval has no owner otherwise. Leaving one running behind the next
    // screen is DECISIONS.md 107's failure with a cheaper timer in it.
    inject(DestroyRef).onDestroy(() => this.stopStatusCycle());
  }

  // The heart. It sends the opposite of what the row currently says rather
  // than a fixed `true`, because the same button unsaves — and it reads that
  // from `look`, which is the merged value above and not `result()`.
  protected toggleSaved(look: Look): void {
    this.looksStore.update(look, { is_saved: !look.is_saved });
  }

  // The card decided whether this is a rating or a withdrawal; the page only
  // has to name the look it belongs to.
  protected rate(look: Look, feedback: Feedback | null): void {
    this.looksStore.update(look, { feedback });
  }

  // One method sets the state and refreshes the forecast, in that order, so
  // there is no effect on the date to guard against firing on arrival — the
  // constructor already made that call. Same arrangement the wardrobe page uses
  // for the filters and the URL. DECISIONS.md 110.
  protected onDraftChanged(draft: LookDraft): void {
    const previous = this.draft();
    this.draft.set(draft);
    if (draft.date !== previous.date) {
      this.store.loadWeather(draft.date);
    }
  }

  protected suggest(): void {
    this.excluded.set([]);
    this.looksStore.clearError();
    this.store.suggest(toRequest(this.draft(), this.anchor()));
  }

  // "Swap the shoes" spelled out: lock everything else, name the role of the
  // tile that was tapped, and add that garment to the exclusions so the answer
  // cannot be the same one again.
  //
  // The exclusions accumulate across taps — 05-FRONTEND-SPEC.md says *adds* to
  // `exclude_item_ids` — so a second swap of the same role cannot hand back the
  // shoe rejected on the first. They are cleared with the look they belong to.
  //
  // No anchor. Every garment the anchor was protecting is locked here anyway,
  // and on the anchored tile itself the two fields would contradict: rule 7
  // requires the item and rule 8 forbids it, which is a 502 by construction.
  protected swapItem(item: Item): void {
    this.looksStore.clearError();
    const look = this.look();
    const role = roleOf(item.category);
    if (look === null || role === undefined) {
      return;
    }

    const excluded = [...this.excluded(), item.id];
    this.excluded.set(excluded);
    this.store.swap(
      {
        ...toRequest(this.draft(), null),
        locked_item_ids: look.items.filter((kept) => kept.id !== item.id).map((kept) => kept.id),
        replace_role: role,
        exclude_item_ids: excluded,
      },
      item.id,
    );
  }

  protected name(item: Item): string {
    return item.display_name ?? this.i18n.t('item.untitled');
  }

  // Split in two so the numbers can take the mono face without the sentence
  // being fragmented: the condition is one word out of a closed vocabulary
  // rather than a clause, so there is no sentence here to reorder and 218's
  // objection does not apply. Neither half names a day — the forecast is for
  // whatever date the picker holds, which is not always today.
  protected conditionLine(weather: Weather): string {
    return this.i18n.t(`vocabulary.condition.${weather.condition}`);
  }

  // Both temperatures, not one. `build_rule` reads the maximum (DECISIONS.md
  // 142) but a person dressing reads the span — 12 to 19 is a different day
  // from 18 to 19 under the same "partly cloudy".
  protected readingLine(weather: Weather): string {
    return this.i18n.t('stylist.weather.reading', {
      min: Math.round(weather.temp_min_c),
      max: Math.round(weather.temp_max_c),
    });
  }

  // The parameter goes with the pin. Left in the URL it would come back on a
  // reload of a screen the user has just told to stop building around it.
  // `replaceUrl` because clearing is not a step back arrives at — the anchored
  // visit and the cleared one are the same visit.
  protected clearAnchor(): void {
    this.anchor.set(null);
    void this.router.navigate(['/stylist'], { queryParams: {}, replaceUrl: true });
  }

  // Read from the snapshot, not a subscription, for item detail's reason: every
  // route into this screen carrying an anchor is a fresh navigation from the
  // item it names. The collection first and a fetch only when it misses — the
  // same fallback that screen uses, because a deep link into /stylist has no
  // wardrobe loaded behind it.
  //
  // A row that cannot be fetched clears the anchor rather than keeping it: the
  // pin would have no name to show, and the request would carry an id the
  // endpoint answers `anchor_unavailable` to.
  private readAnchor(): void {
    const id = this.route.snapshot.queryParamMap.get('anchor');
    if (id === null) {
      return;
    }

    const known = this.wardrobe.items().find((candidate) => candidate.id === id);
    if (known !== undefined) {
      this.anchor.set(known);
      return;
    }

    this.items.get(id).subscribe({
      next: (item) => this.anchor.set(item),
      error: () => this.anchor.set(null),
    });
  }

  // "Try again" goes back to the form rather than re-firing the last request:
  // the draft is still on screen behind the card, and the reroll a user wants
  // is usually the one with the notes field changed. reset() clears the
  // forecast along with the look, so the date is re-asked for in the same two
  // calls and the same order the constructor makes them.
  protected startOver(): void {
    this.excluded.set([]);
    this.store.reset();
    this.store.loadWeather(this.draft().date);
  }

  // Guarded rather than assumed idle: the effect above re-runs on every read
  // of `isSuggesting`, and a second interval started over a live one would be
  // an interval nothing holds a handle to. One place creates it, one destroys
  // it — the discipline the wardrobe store's PollRun is built on.
  private startStatusCycle(): void {
    if (this.timer !== null) {
      return;
    }
    this.statusIndex.set(0);
    this.timer = setInterval(() => {
      // Clamped, not wrapped. At six seconds "Reading the forecast…" is no
      // longer true, and a line that comes back round claims work that is
      // behind us — the wait is bounded, so the last line is where it rests.
      this.statusIndex.update((index) => Math.min(index + 1, STATUS_KEYS.length - 1));
    }, STATUS_INTERVAL_MS);
  }

  private stopStatusCycle(): void {
    if (this.timer === null) {
      return;
    }
    clearInterval(this.timer);
    this.timer = null;
  }
}

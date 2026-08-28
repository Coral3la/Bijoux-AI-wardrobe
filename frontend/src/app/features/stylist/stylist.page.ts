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
import { StylistStore } from '../../core/state/stylist.store';
import { WardrobeStore } from '../../core/state/wardrobe.store';
import { roleOf } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';
import { SuggestRequest } from '../../shared/models/look.model';
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

// The look card's own shape, five tiles in the 2 + 3 arrangement
// 05-FRONTEND-SPEC.md draws — a skeleton of the thing being built rather than
// a spinner, which is what §2.8 asks for and what makes the wait read as
// progress. Task 2.9 fills this outline in.
const SKELETON_TILES = [0, 1, 2, 3, 4] as const;

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
  imports: [LookCard, LookRequestForm],
  template: `
    <main class="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <header>
        <h1 class="font-display text-3xl">{{ i18n.t('stylist.title') }}</h1>
      </header>

      @if (store.isSuggesting()) {
        <section class="flex flex-col gap-4">
          <div class="grid grid-cols-3 gap-3" aria-hidden="true">
            @for (tile of tiles; track tile) {
              <div class="aspect-square animate-pulse rounded-lg bg-surface"></div>
            }
          </div>
          <!-- The status line is the accessible name of the wait: the tiles
               above it are decoration and say so. aria-live so the cycling is
               announced rather than silently replaced under a screen reader. -->
          <p class="text-sm" role="status" aria-live="polite">{{ i18n.t(statusKey()) }}</p>
        </section>
      } @else if (look(); as look) {
        <!-- Above the card, and only a swap can put it there: the card is on
             screen, so the error is about the piece that did not change rather
             than about a look that never arrived. -->
        @if (store.error(); as key) {
          <p class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
        }

        <app-look-card
          [look]="look"
          [missingPieces]="missingPieces()"
          [message]="message()"
          [swappingItemId]="store.swappingItemId()"
          (tryAgain)="startOver()"
          (swap)="swapItem($event)"
        />
      } @else {
        @if (store.error(); as key) {
          <p class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
        }

        <!-- Pinned above the form, where 05-FRONTEND-SPEC.md puts it. It is not
             one of the form's controls: the four in LookDraft are what the user
             sets here, and the anchor is what she arrived carrying. -->
        @if (anchor(); as item) {
          <div class="flex items-center gap-3 rounded-lg bg-surface p-3">
            <p class="text-sm">
              {{ i18n.t('stylist.anchor.pinned', { item: name(item) }) }}
            </p>
            <button
              type="button"
              (click)="clearAnchor()"
              [attr.aria-label]="i18n.t('stylist.anchor.clear')"
              class="ms-auto min-h-11 min-w-11 rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              ×
            </button>
          </div>
        }

        <app-look-request-form
          [draft]="draft()"
          [weather]="store.weather()"
          (draftChanged)="onDraftChanged($event)"
          (submitted)="suggest()"
        />
      }
    </main>
  `,
})
export class StylistPage {
  protected readonly i18n = inject(I18nService);
  protected readonly store = inject(StylistStore);
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
  protected readonly look = computed(() => this.store.result()?.looks[0] ?? null);
  protected readonly message = computed(() => this.store.result()?.message ?? '');
  protected readonly missingPieces = computed(() => this.store.result()?.missing_pieces ?? []);

  constructor() {
    // Reset first, then load: this store is providedIn: 'root' and a second
    // visit arrives holding the first visit's look and forecast.
    this.store.reset();
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

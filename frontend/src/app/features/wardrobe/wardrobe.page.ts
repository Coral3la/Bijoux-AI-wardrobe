import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { ActivatedRoute, Params, Router } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { ItemFilters, WardrobeStore } from '../../core/state/wardrobe.store';
import { CATEGORIES, COLORS, Category } from '../../shared/models/enums';
import { AuthoredLine } from '../../shared/ui/authored-line';
import { Button } from '../../shared/ui/button';
import { EmptyState } from '../../shared/ui/empty-state';
import { Skeleton } from '../../shared/ui/skeleton';
import { CategoryCounts, FilterBar } from './filter-bar';
import { ItemCard } from './item-card';
import { PendingStrip } from './pending-strip';
import { UploadSheet } from './upload-sheet';
import { WardrobeInsights } from './wardrobe-insights';
import { WeatherStrip } from './weather-strip';

// A URL is user input. A value outside the closed vocabulary is dropped rather
// than applied, so `?category=banana` shows an unfiltered wardrobe under a URL
// that claims a filter, until the first interaction rewrites it. Normalising
// the address bar on arrival was the alternative, and it writes the URL on
// load — which is the thing reading it once exists to prevent. 110.
function member<T extends string>(value: string | null, vocabulary: readonly T[]): T | undefined {
  return value !== null && (vocabulary as readonly string[]).includes(value)
    ? (value as T)
    : undefined;
}

// Six, not a screenful. A skeleton is a promise about what is coming, and
// filling the viewport promises a warehouse to an account with four garments —
// two rows on a phone and just over one on a desktop is enough to say "a grid".
const LOADING_TILES = [0, 1, 2, 3, 4, 5] as const;

// 05:00-11:59 morning, 12:00-17:59 afternoon, and the rest of the clock
// evening. Exported for the spec, which is the only way to pin the boundaries
// without three tests that each move the system clock. The hour is the
// browser's own, which is the same clock `todayInLocalTime` reads.
export function greetingSlot(now: Date): 'morning' | 'afternoon' | 'evening' {
  const hour = now.getHours();
  if (hour >= 5 && hour < 12) {
    return 'morning';
  }
  // Both bounds, not `hour < 18`: the small hours never reach the morning
  // branch, so a single upper bound calls 4am the afternoon. The spec's
  // boundary test is what found that.
  if (hour >= 12 && hour < 18) {
    return 'afternoon';
  }
  return 'evening';
}

// Loose on purpose: the store's setter is what rounds and clamps a scale point,
// so this only has to refuse what is not a number at all.
function scale(value: string | null): number | undefined {
  if (value === null) {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

@Component({
  selector: 'app-wardrobe-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    AuthoredLine,
    Button,
    EmptyState,
    FilterBar,
    ItemCard,
    PendingStrip,
    Skeleton,
    UploadSheet,
    WardrobeInsights,
    WeatherStrip,
  ],
  template: `
    <main
      class="mx-auto flex w-full max-w-[1100px] flex-col gap-region px-6 pt-hero pb-region md:px-14"
    >
      <header class="flex flex-col gap-group">
        <!-- The first line in the product addressed to the person using it, and
             the first caller of both the prose face and 213's split: the
             sentence is ours and the name is theirs, so the name renders in the
             content face inside it. Above the title row rather than inside it,
             so the count keeps the baseline it shares with the heading.
             Italic, because Atelier has one serif doing both authored roles
             and the italic is what tells prose from display. -->
        <app-authored-line
          class="block font-prose text-xl text-ink-muted italic"
          [key]="greeting().key"
          [content]="greeting().content"
        />

        <div class="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <!-- 96px at the widths that can hold it, and the weight is the
               point rather than the size: Cormorant at 300 is a hairline at
               this scale, which is what keeps a word this large quiet. -->
          <h1
            class="font-display text-[56px] leading-[0.95] font-light tracking-[-0.02em] md:text-[96px]"
          >
            {{ i18n.t('wardrobe.title') }}
          </h1>
          @if (!store.isLoading() && store.loadError() === null) {
            <p class="font-mono text-[13px] tracking-[0.02em] text-ink-muted tabular-nums">
              {{ countLabel() }}
            </p>
          }
        </div>
      </header>

      <!-- Above every branch below rather than inside one: an empty wardrobe, a
           failed load and a filter with no matches are all states this screen
           can be in, and none of them is a reason to lose the way to the
           stylist. It stopped being the *only* route there at 4.9 — the
           navigation bar carries one too — and it stays because Style me is an
           action on today's forecast rather than navigation, which §2.12
           requires in all three of the strip's states. -->
      <app-weather-strip />

      <!-- Under the strip and above the pending strip, because both of those
           are standing context about the wardrobe while the pending strip is
           transient feedback that belongs beside the grid it changes. Outside
           the branch chain below like the filter bar, and it needs nothing
           from that chain: it fetches for itself and renders nothing at all
           when there is no true sentence to print. DECISIONS.md 188. -->
      <app-wardrobe-insights />

      <!-- Above the whole chain below, deliberately. The grid lives in the
           final @else, and on a first-ever upload isEmpty() is still true
           until the 202 lands — so a strip rendered "above the grid" from
           inside that branch would not render at all during the one upload it
           matters most for. DECISIONS.md 097. -->
      <app-pending-strip [pending]="store.pending()" />

      <!-- Outside the chain for the same class of reason: it belongs to both
           the grid and the no-match state, and a bar that lived inside the
           branch it produces could not be cleared from there. -->
      @if (showFilters()) {
        <app-filter-bar
          [filters]="store.filters()"
          [counts]="categoryCounts()"
          (filtersChanged)="onFiltersChanged($event)"
        />
      }

      @if (store.isLoading()) {
        <!-- The grid's own shape, which is what makes this read as progress
             rather than as a spinner — the stylist's wait proved that at 2.8.
             The tiles need no aria-hidden of their own: Skeleton's host carries
             it, so what is announced here is the status line and nothing else.
             The shape is the grid's, so the two move together: four columns
             and a 4:5 plate, not the three squares this drew before.
             DECISIONS.md 217. -->
        <div class="animate-deferred flex flex-col gap-group">
          <div class="grid grid-cols-2 gap-x-3.5 gap-y-6 md:grid-cols-4 md:gap-x-7 md:gap-y-10">
            @for (tile of loadingTiles; track tile) {
              <app-skeleton class="aspect-4/5" radius="rounded-[2px]" />
            }
          </div>
          <p class="font-prose text-base text-ink-muted italic" role="status" aria-live="polite">
            {{ i18n.t('wardrobe.loading') }}
          </p>
        </div>
      } @else if (store.loadError(); as key) {
        <div class="flex flex-col items-start gap-2">
          <p class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
          <button appButton variant="ghost" type="button" (click)="store.load()">
            {{ i18n.t('wardrobe.retryLoad') }}
          </button>
        </div>
      } @else if (store.isEmpty() && store.pending().length === 0) {
        <!-- These two states still render EmptyState, which still carries the
             pre-Atelier faces and the pre-Atelier button: it is shared with
             /saved, and converting it belongs to the commit that converts that
             screen rather than to this one. It is the one part of this screen
             the mockup does not yet reach. -->
        <app-empty-state
          [title]="i18n.t('wardrobe.empty.title')"
          [description]="i18n.t('wardrobe.empty.body')"
        >
          <!-- Inert for exactly one task, which 090 accepted as the cost of
               shipping the empty state reviewable. Wired here, along with the
               FAB 090 declined to build because no task had required one. -->
          <button appButton type="button" (click)="openSheet()">
            {{ i18n.t('wardrobe.empty.cta') }}
          </button>
        </app-empty-state>
      } @else if (noMatches()) {
        <!-- A wardrobe with items in it and nothing on screen is not an empty
             wardrobe, and it must not offer the empty wardrobe's action: the
             way out of here is the filter, not the camera. Same component as
             the state above, different copy and a different slot — which is
             the whole of what keeps the two apart. DECISIONS.md 111. -->
        <app-empty-state
          [title]="i18n.t('wardrobe.filter.noMatch.title')"
          [description]="i18n.t('wardrobe.filter.noMatch.body')"
        >
          <button appButton variant="ghost" type="button" (click)="onFiltersChanged({})">
            {{ i18n.t('wardrobe.filter.clear') }}
          </button>
        </app-empty-state>
      } @else {
        <!-- Counts what the loop is still watching, not every row the server
             calls processing: after the hard stop those are two different
             numbers, and each abandoned tile says so for itself. It is not
             filtered either — the loop never was — and it does not need to be:
             a processing row has null tags, so no tag filter can hide one. -->
        <!-- Grouped rather than left as siblings of <main>: the tagging line
             is a label for the grid under it, and at region distance a label
             reads as an unrelated notice. This is the group rung's first
             caller. DECISIONS.md 212. -->
        <div class="flex flex-col gap-group">
          @if (store.awaitingTags().length > 0) {
            <p class="font-prose text-base text-ink-muted italic">{{ taggingLabel() }}</p>
          }
          <!-- Four columns and no shadow, with more air between the rows than
               between the columns: a caption sits under every tile now, and
               equal gaps would let a name read as a label for the plate below
               it as readily as for the one above. DECISIONS.md 219. -->
          <ul class="grid grid-cols-2 gap-x-3.5 gap-y-6 md:grid-cols-4 md:gap-x-7 md:gap-y-10">
            @for (item of store.visible(); track item.id) {
              <li>
                <app-item-card
                  [item]="item"
                  [retrying]="store.retrying().has(item.id)"
                  [errorKey]="store.retagErrors().get(item.id) ?? null"
                  [stoppedWaiting]="store.stoppedWaiting().has(item.id)"
                  (retry)="store.retag(item.id)"
                />
              </li>
            }
          </ul>
        </div>
      }
    </main>

    <!-- The second entry point, and the only one once a wardrobe has anything
         in it: the empty state's CTA lives inside the @else if above and goes
         away after the first upload. An outlined pill rather than a filled
         circle — a solid disc of ink over the grid is the one object on the
         screen that would outweigh a photograph, and the word is what makes it
         legible without an aria-label doing the work. Positioned with end-6
         rather than right-6 — logical properties only, so Hebrew moves it
         without a rewrite. -->
    @if (!sheetOpen()) {
      <button
        type="button"
        (click)="openSheet()"
        class="fixed bottom-6 end-6 z-30 inline-flex min-h-11 items-center rounded-full border border-ink bg-canvas px-6 text-[11px] font-medium tracking-[0.22em] text-ink uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent md:bottom-10 md:end-10"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="me-2.5 h-3 w-3"
          aria-hidden="true"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
        {{ i18n.t('wardrobe.upload.open') }}
      </button>
    }

    @if (sheetOpen()) {
      <app-upload-sheet
        [uploading]="store.isUploading()"
        [serverError]="store.uploadError()"
        (filesSelected)="store.upload($event)"
        (dismissed)="closeSheet()"
      />
    }
  `,
})
export class WardrobePage {
  protected readonly i18n = inject(I18nService);
  protected readonly store = inject(WardrobeStore);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly loadingTiles = LOADING_TILES;
  protected readonly sheetOpen = signal(false);

  // Read once, from the constructor's clock, for the stylist dateline's reason:
  // the part of the day a screen was opened in does not change under the reader.
  private readonly slot = greetingSlot(new Date());

  // Deliberately not `userLabel()`. That function falls back to the email
  // address, which is the right answer for a "signed in as" label and the wrong
  // one for a greeting — nobody is called coral@example.com. A blank name takes
  // the nameless key instead, so the line keeps its shape and loses only the
  // name; an absent parameter would not do, because `t` leaves an unsupplied
  // placeholder visible on purpose. DECISIONS.md 215.
  protected readonly greeting = computed(() => {
    const name = this.auth.currentUser()?.display_name?.trim();
    return name
      ? { key: `wardrobe.hello.${this.slot}`, content: { name } }
      : { key: `wardrobe.hello.nameless.${this.slot}`, content: undefined };
  });

  // There is nothing to filter while the wardrobe is loading, broken or empty,
  // and a bar over the empty state would offer to narrow nothing.
  protected readonly showFilters = computed(
    () => !this.store.isLoading() && this.store.loadError() === null && !this.store.isEmpty(),
  );

  // Not `visible().length === 0` alone: during the first upload into an empty
  // wardrobe that is true and the honest answer is the grid, not "no matches".
  protected readonly noMatches = computed(
    () => !this.store.isEmpty() && this.store.visible().length === 0,
  );

  // Counted off `items()` and never off `total()`, which is the same split the
  // header already lives with: `total` is the server's and knows about rows
  // past the page of 200, where a per-category number can only ever be a count
  // of what was loaded. So on a wardrobe above 200 garments the All chip and
  // the header disagree, and the chip is the one telling the truth about the
  // grid beneath it. `GET /items/stats` carries a `by_category` that would
  // agree with the header instead — it is the insights panel's request, fetched
  // for a different question, and a second consumer would tie this row to a
  // request it does not need.
  //
  // A null category is counted nowhere rather than into a tenth bucket: a
  // processing row has null tags, and a chip called "Untagged" would be a
  // filter dimension nobody specified. It is why the nine counts can sum to
  // less than All.
  protected readonly categoryCounts = computed<CategoryCounts>(() => {
    const byCategory = new Map<Category, number>();
    for (const item of this.store.items()) {
      if (item.category !== null) {
        byCategory.set(item.category, (byCategory.get(item.category) ?? 0) + 1);
      }
    }
    return { all: this.store.items().length, byCategory };
  });

  // A normalised filter object carries only its active keys, so the key count
  // is the whole question. Kept here rather than on the store because it is a
  // question about what to render.
  protected readonly isFiltered = computed(() => Object.keys(this.store.filters()).length > 0);

  // I18nService has no plural rule (DECISIONS.md 058), so the caller picks the
  // key. Two keys rather than "{{count}} items", which reads "1 items".
  //
  // Under a filter this is the only count on the screen and it states both
  // numbers: the matched rows against the wardrobe total. `total` is still the
  // server's, so it is still the one number that knows about rows past the
  // page of 200 — 094 and 100 both survive unchanged. DECISIONS.md 111.
  protected readonly countLabel = computed(() => {
    const total = this.store.total();
    if (this.isFiltered()) {
      const count = this.store.visible().length;
      return count === 1
        ? this.i18n.t('wardrobe.count.filtered.one', { total })
        : this.i18n.t('wardrobe.count.filtered.other', { count, total });
    }
    return total === 1
      ? this.i18n.t('wardrobe.count.one')
      : this.i18n.t('wardrobe.count.other', { count: total });
  });

  protected readonly taggingLabel = computed(() => {
    const count = this.store.awaitingTags().length;
    return count === 1
      ? this.i18n.t('wardrobe.tagging.one')
      : this.i18n.t('wardrobe.tagging.other', { count });
  });

  constructor() {
    // Read once, from the snapshot. A subscription to queryParamMap would
    // re-apply the URL this component has just written, and the filters are
    // the store's state rather than the route's. DECISIONS.md 110.
    this.store.setFilters(this.filtersFromUrl());
    this.store.load();
    // WardrobeStore is providedIn: 'root' and outlives this component, so the
    // loop has no owner unless one is given here. Without it a poll started on
    // this screen keeps running behind every screen after it.
    inject(DestroyRef).onDestroy(() => this.store.stopPolling());
  }

  // One method sets the state and writes the URL, in that order, so there is no
  // effect to guard against firing on arrival and no second writer to drift
  // from. The query string is built from the *normalised* filters rather than
  // from the emitted object, so the address bar carries what the grid is
  // actually filtered by. DECISIONS.md 110.
  protected onFiltersChanged(filters: ItemFilters): void {
    this.store.setFilters(filters);
    void this.router.navigate([], {
      queryParams: this.queryParams(),
      replaceUrl: true,
    });
  }

  // Cleared on open rather than on close, so a message about the last batch
  // cannot greet the user on top of an empty sheet the next time they open it.
  protected openSheet(): void {
    this.store.dismissUploadError();
    this.sheetOpen.set(true);
  }

  protected closeSheet(): void {
    this.sheetOpen.set(false);
  }

  private filtersFromUrl(): ItemFilters {
    const params = this.route.snapshot.queryParamMap;
    return {
      category: member(params.get('category'), CATEGORIES),
      color_primary: member(params.get('color_primary'), COLORS),
      formality_min: scale(params.get('formality_min')),
      formality_max: scale(params.get('formality_max')),
      warmth_min: scale(params.get('warmth_min')),
      warmth_max: scale(params.get('warmth_max')),
    };
  }

  // A loop over the object's own keys, which works because the filter object
  // and the query string share one vocabulary by construction (110). That is
  // the payoff of the field names and it is the same thing as the trap:
  // renaming a field here renames a public URL parameter, and somebody's
  // bookmark is holding the old one. There is nothing to keep in step — there
  // is one name — which is why the rename is silent.
  private queryParams(): Params {
    const params: Params = {};
    for (const [key, value] of Object.entries(this.store.filters())) {
      params[key] = String(value);
    }
    return params;
  }
}

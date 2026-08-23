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
import { CATEGORIES, COLORS } from '../../shared/models/enums';
import { userLabel } from '../../shared/models/user.model';
import { FilterBar } from './filter-bar';
import { ItemCard } from './item-card';
import { PendingStrip } from './pending-strip';
import { UploadSheet } from './upload-sheet';

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
  imports: [FilterBar, ItemCard, PendingStrip, UploadSheet],
  template: `
    <main class="mx-auto flex w-full max-w-5xl flex-col gap-6 p-6">
      <header class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h1 class="font-display text-3xl">{{ i18n.t('wardrobe.title') }}</h1>
        @if (!store.isLoading() && store.loadError() === null) {
          <p class="text-sm">{{ countLabel() }}</p>
        }
      </header>

      <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
        <!-- Body face, deliberately: display_name is user-entered and may be
             non-Latin, which Fraunces does not cover. DECISIONS.md 071. -->
        @if (auth.currentUser(); as user) {
          <p class="text-sm">{{ i18n.t('wardrobe.signedInAs', { name: label(user) }) }}</p>
        }
        <button
          type="button"
          (click)="signOut()"
          class="min-h-11 rounded-md px-3 text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {{ i18n.t('wardrobe.signOut') }}
        </button>
      </div>

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
        <app-filter-bar [filters]="store.filters()" (filtersChanged)="onFiltersChanged($event)" />
      }

      @if (store.isLoading()) {
        <p class="text-sm">{{ i18n.t('wardrobe.loading') }}</p>
      } @else if (store.loadError(); as key) {
        <div class="flex flex-col items-start gap-2">
          <p class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
          <button
            type="button"
            (click)="store.load()"
            class="min-h-11 rounded-md px-3 text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ i18n.t('wardrobe.retryLoad') }}
          </button>
        </div>
      } @else if (store.isEmpty() && store.pending().length === 0) {
        <section class="flex flex-col items-start gap-3 py-12">
          <h2 class="font-display text-2xl">{{ i18n.t('wardrobe.empty.title') }}</h2>
          <p class="max-w-prose text-sm">{{ i18n.t('wardrobe.empty.body') }}</p>
          <!-- Inert for exactly one task, which 090 accepted as the cost of
               shipping the empty state reviewable. Wired here, along with the
               FAB 090 declined to build because no task had required one. -->
          <button
            type="button"
            (click)="openSheet()"
            class="min-h-11 rounded-md bg-accent px-4 text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ i18n.t('wardrobe.empty.cta') }}
          </button>
        </section>
      } @else if (noMatches()) {
        <!-- A wardrobe with items in it and nothing on screen is not an empty
             wardrobe, and it must not offer the empty wardrobe's action: the
             way out of here is the filter, not the camera. DECISIONS.md 111. -->
        <section class="flex flex-col items-start gap-3 py-12">
          <h2 class="font-display text-2xl">{{ i18n.t('wardrobe.filter.noMatch.title') }}</h2>
          <p class="max-w-prose text-sm">{{ i18n.t('wardrobe.filter.noMatch.body') }}</p>
          <button
            type="button"
            (click)="onFiltersChanged({})"
            class="min-h-11 rounded-md bg-accent px-4 text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ i18n.t('wardrobe.filter.clear') }}
          </button>
        </section>
      } @else {
        <!-- Counts what the loop is still watching, not every row the server
             calls processing: after the hard stop those are two different
             numbers, and each abandoned tile says so for itself. It is not
             filtered either — the loop never was — and it does not need to be:
             a processing row has null tags, so no tag filter can hide one. -->
        @if (store.awaitingTags().length > 0) {
          <p class="text-sm">{{ taggingLabel() }}</p>
        }
        <ul class="grid grid-cols-3 gap-3 md:grid-cols-5">
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
      }
    </main>

    <!-- The second entry point, and the only one once a wardrobe has anything
         in it: the empty state's CTA lives inside the @else if above and goes
         away after the first upload. Positioned with end-6 rather than
         right-6 — logical properties only, so Hebrew moves it without a
         rewrite. -->
    @if (!sheetOpen()) {
      <button
        type="button"
        (click)="openSheet()"
        class="fixed bottom-6 end-6 z-30 flex min-h-11 items-center rounded-full bg-accent px-5 text-surface shadow-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
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
  protected readonly auth = inject(AuthService);
  protected readonly store = inject(WardrobeStore);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly label = userLabel;
  protected readonly sheetOpen = signal(false);

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

  // No guard re-runs on a route that is already active. DECISIONS.md 068.
  protected signOut(): void {
    this.auth.logout();
    void this.router.navigateByUrl('/login');
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

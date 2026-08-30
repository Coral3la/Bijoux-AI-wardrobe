import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { I18nService } from '../../core/i18n/i18n.service';
import { LooksStore } from '../../core/state/looks.store';
import { Look } from '../../shared/models/look.model';
import { todayInLocalTime } from '../stylist/look-request-form';
import { ItemCard } from '../wardrobe/item-card';

// Deliberately not LookCard. That component is the stylist's payoff — it groups
// by layer, carries a ↻ badge on every garment and ends in "Try again", none of
// which a saved look can do: there is no request behind it to re-run. What a
// list needs is the title, the garments in the model's own order, and the heart
// that takes it back out. Reusing the card would have meant two inputs whose
// only job is to switch its own features off. 05-FRONTEND-SPEC.md draws no
// screen for this at all — the amendment in the same commit is what adds it.
@Component({
  selector: 'app-saved-looks-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ItemCard, RouterLink],
  template: `
    <main class="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <header class="flex items-center gap-3">
        <a
          routerLink="/wardrobe"
          class="min-h-11 rounded-md py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {{ i18n.t('saved.back') }}
        </a>
        <h1 class="font-display text-3xl">{{ i18n.t('saved.title') }}</h1>
      </header>

      @if (store.error(); as key) {
        <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
      }

      @if (store.isLoading()) {
        <p class="text-sm" role="status" aria-live="polite">{{ i18n.t('saved.loading') }}</p>
      } @else if (store.looks().length === 0) {
        <section class="flex flex-col items-start gap-3 rounded-lg bg-surface p-6">
          <h2 class="text-xl">{{ i18n.t('saved.empty.title') }}</h2>
          <p class="text-sm">{{ i18n.t('saved.empty.body') }}</p>
          <a
            routerLink="/stylist"
            class="min-h-11 rounded-md bg-accent px-4 py-2 text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ i18n.t('saved.empty.cta') }}
          </a>
        </section>
      } @else {
        <ul class="flex flex-col gap-4">
          @for (look of store.looks(); track look.id) {
            <li class="flex flex-col gap-3 rounded-lg bg-surface p-4">
              <div class="flex items-start gap-3">
                <h2 class="text-xl">{{ look.title }}</h2>

                <!-- The same toggle as the look card's, with the same fixed
                     accessible name and the same aria-pressed. A row that has
                     just been unsaved stays here with an empty heart until the
                     next load, which is what makes the tap undoable. -->
                <button
                  type="button"
                  (click)="toggleSaved(look)"
                  [disabled]="store.updatingId() !== null"
                  [attr.aria-pressed]="look.is_saved"
                  [attr.aria-label]="i18n.t('stylist.look.save')"
                  class="ms-auto min-h-11 min-w-11 rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50"
                >
                  <span aria-hidden="true">{{ look.is_saved ? '♥' : '♡' }}</span>
                </button>
              </div>

              <p class="text-sm">{{ look.weather_note }}</p>

              <!-- In the order the server sent, which is look_items.position
                   and therefore the model's own. No layer grouping: a list is
                   scanned rather than read, and the headings that help on one
                   card are noise repeated down a page of them. -->
              <ul class="grid grid-cols-4 gap-2">
                @for (item of look.items; track item.id) {
                  <li><app-item-card [item]="item" /></li>
                }
              </ul>

              <!-- Below the garments rather than beside the heart: the heart is
                   about this list and this button is about today, and a text
                   label does not sit in a row built for a glyph.

                   It stays on screen after a successful tap, disabled and
                   relabelled, because the state is worth showing — and the
                   endpoint is idempotent for exactly this date anyway, so a
                   client that retries costs nothing. It does not become a
                   toggle: there is no way to un-wear a look. -->
              <button
                type="button"
                (click)="wear(look)"
                [disabled]="store.updatingId() !== null || wornToday(look)"
                class="min-h-11 self-start rounded-md bg-accent px-4 text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50"
              >
                {{ wornToday(look) ? i18n.t('saved.wear.done') : i18n.t('saved.wear') }}
              </button>
            </li>
          }
        </ul>
      }
    </main>
  `,
})
export class SavedLooksPage {
  protected readonly i18n = inject(I18nService);
  protected readonly store = inject(LooksStore);

  constructor() {
    // Reset before loading, for StylistPage's reason: the store is
    // providedIn: 'root' and a second visit arrives holding the first visit's
    // list, which would be on screen under the spinner.
    this.store.reset();
    this.store.loadSaved();
  }

  protected toggleSaved(look: Look): void {
    this.store.update(look, { is_saved: !look.is_saved });
  }

  // The browser's today, not the server's — imported from the stylist's form
  // rather than copied, which is the precedent `weather-strip.ts` set for the
  // same function and the same reason: two spellings of "today" in one
  // application would disagree for anyone not on UTC.
  protected wear(look: Look): void {
    this.store.wear(look, todayInLocalTime());
  }

  protected wornToday(look: Look): boolean {
    return look.worn_at === todayInLocalTime();
  }
}

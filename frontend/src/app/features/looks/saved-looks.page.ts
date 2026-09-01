import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { I18nService } from '../../core/i18n/i18n.service';
import { LooksStore } from '../../core/state/looks.store';
import { Look } from '../../shared/models/look.model';
import { Button } from '../../shared/ui/button';
import { EmptyState } from '../../shared/ui/empty-state';
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
  imports: [Button, EmptyState, ItemCard, RouterLink],
  template: `
    <main class="mx-auto flex w-full max-w-2xl flex-col gap-region px-6 pt-hero pb-region">
      <header>
        <h1 class="font-display text-4xl leading-tight tracking-tight">
          {{ i18n.t('saved.title') }}
        </h1>
      </header>

      @if (store.error(); as key) {
        <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
      }

      @if (store.isLoading()) {
        <p class="text-sm text-ink-muted" role="status" aria-live="polite">
          {{ i18n.t('saved.loading') }}
        </p>
      } @else if (store.looks().length === 0) {
        <!-- The same component the wardrobe's two empties use, which is what
             gives every empty state in the product one identity. The CTA is an
             anchor rather than a button because it navigates (208's line
             between the two), and it is projected because the copy and the way
             out differ per caller. -->
        <app-empty-state
          [title]="i18n.t('saved.empty.title')"
          [description]="i18n.t('saved.empty.body')"
        >
          <!-- Ghost, unlike the wardrobe's first-upload CTA: an empty saved list
               is a state a working account passes through, not the one action a
               new account must take. Per-caller weight is why the CTA is
               projected. DECISIONS.md 216. -->
          <a appButton variant="ghost" routerLink="/stylist">{{ i18n.t('saved.empty.cta') }}</a>
        </app-empty-state>
      } @else {
        <ul class="flex flex-col gap-4">
          @for (look of store.looks(); track look.id) {
            <li class="flex flex-col gap-3 rounded-2xl bg-surface p-4 shadow-sm">
              <div class="flex items-start gap-3">
                <h2 class="text-xl">{{ look.title }}</h2>

                <!-- The same toggle as the look card's, with the same fixed
                     accessible name and the same aria-pressed. A row that has
                     just been unsaved stays here with an empty heart until the
                     next load, which is what makes the tap undoable. -->
                <button
                  appButton
                  variant="secondary"
                  type="button"
                  (click)="toggleSaved(look)"
                  [disabled]="store.updatingId() !== null"
                  [attr.aria-pressed]="look.is_saved"
                  [attr.aria-label]="i18n.t('stylist.look.save')"
                  class="ms-auto disabled:opacity-50"
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
                appButton
                type="button"
                (click)="wear(look)"
                [disabled]="store.updatingId() !== null || wornToday(look)"
                class="self-start disabled:opacity-50"
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

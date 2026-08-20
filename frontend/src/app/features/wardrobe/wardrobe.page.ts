import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { WardrobeStore } from '../../core/state/wardrobe.store';
import { userLabel } from '../../shared/models/user.model';
import { ItemCard } from './item-card';

@Component({
  selector: 'app-wardrobe-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ItemCard],
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
      } @else if (store.isEmpty()) {
        <section class="flex flex-col items-start gap-3 py-12">
          <h2 class="font-display text-2xl">{{ i18n.t('wardrobe.empty.title') }}</h2>
          <p class="max-w-prose text-sm">{{ i18n.t('wardrobe.empty.body') }}</p>
          <!-- Inert until task 1.6 wires it to the upload sheet. It is here
               and the FAB is not because 1.5's acceptance line requires this
               CTA and no task requires a FAB at 1.5 — the test is ownership,
               not whether the control does something yet. DECISIONS.md 090. -->
          <button
            type="button"
            class="min-h-11 rounded-md bg-accent px-4 text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ i18n.t('wardrobe.empty.cta') }}
          </button>
        </section>
      } @else {
        <!-- Nothing refreshes this screen on its own until task 1.7 polls, so
             the line names the action that does. -->
        @if (store.processing().length > 0) {
          <p class="text-sm">{{ taggingLabel() }}</p>
        }
        <ul class="grid grid-cols-3 gap-3 md:grid-cols-5">
          @for (item of store.items(); track item.id) {
            <li>
              <app-item-card
                [item]="item"
                [retrying]="store.retrying().has(item.id)"
                [errorKey]="store.retagErrors().get(item.id) ?? null"
                (retry)="store.retag(item.id)"
              />
            </li>
          }
        </ul>
      }
    </main>
  `,
})
export class WardrobePage {
  protected readonly i18n = inject(I18nService);
  protected readonly auth = inject(AuthService);
  protected readonly store = inject(WardrobeStore);
  private readonly router = inject(Router);

  protected readonly label = userLabel;

  // I18nService has no plural rule (DECISIONS.md 058), so the caller picks the
  // key. Two keys rather than "{{count}} items", which reads "1 items".
  protected readonly countLabel = computed(() => {
    const total = this.store.total();
    return total === 1
      ? this.i18n.t('wardrobe.count.one')
      : this.i18n.t('wardrobe.count.other', { count: total });
  });

  protected readonly taggingLabel = computed(() => {
    const count = this.store.processing().length;
    return count === 1
      ? this.i18n.t('wardrobe.tagging.one')
      : this.i18n.t('wardrobe.tagging.other', { count });
  });

  constructor() {
    this.store.load();
  }

  // No guard re-runs on a route that is already active. DECISIONS.md 068.
  protected signOut(): void {
    this.auth.logout();
    void this.router.navigateByUrl('/login');
  }
}

import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { WardrobeStore } from '../../core/state/wardrobe.store';
import { userLabel } from '../../shared/models/user.model';
import { ItemCard } from './item-card';
import { PendingStrip } from './pending-strip';
import { UploadSheet } from './upload-sheet';

@Component({
  selector: 'app-wardrobe-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ItemCard, PendingStrip, UploadSheet],
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

  protected readonly label = userLabel;
  protected readonly sheetOpen = signal(false);

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
}

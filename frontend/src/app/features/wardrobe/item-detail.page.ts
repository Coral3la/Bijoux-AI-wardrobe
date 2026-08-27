import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ItemsApi } from '../../core/api/items.api';
import { I18nService } from '../../core/i18n/i18n.service';
import { WardrobeStore } from '../../core/state/wardrobe.store';
import { Item, ItemUpdate } from '../../shared/models/item.model';
import { CloudinaryUrlPipe } from '../../shared/pipes/cloudinary-url.pipe';
import { TagEditor } from './tag-editor';

@Component({
  selector: 'app-item-detail-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CloudinaryUrlPipe, RouterLink, TagEditor],
  template: `
    <main class="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <a
        routerLink="/wardrobe"
        class="min-h-11 self-start text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('item.back') }}
      </a>

      @if (item(); as row) {
        <!-- Body face, not display: display_name is user-entered and may be
             non-Latin, which Fraunces does not cover. 05's rule names this
             screen as one of four that must apply it deliberately (071). -->
        <h1 class="text-2xl">{{ row.display_name ?? i18n.t('item.untitled') }}</h1>

        <!-- The detail transform, built from image_public_id. The server sends
             image_url as a 300px padded thumbnail and nothing else, so this is
             the first screen in the project that cannot use it. O-10's pipe,
             at the first caller that needs it. -->
        <img
          [src]="row.image_public_id | cloudinaryUrl: 'detail'"
          [alt]="row.display_name ?? i18n.t('item.untitled')"
          class="w-full rounded-lg bg-surface object-contain"
        />

        <!-- The primary action on this screen, and 05-FRONTEND-SPEC.md's
             instruction is that it is not buried behind edit and delete — so it
             sits directly under the photograph, above the tags. Only on a ready
             row: the stylist is shown ready, unarchived items alone, so the
             button on any other row would navigate to a request the endpoint
             answers anchor_unavailable to. -->
        @if (row.status === 'ready') {
          <a
            routerLink="/stylist"
            [queryParams]="{ anchor: row.id }"
            class="inline-flex min-h-11 items-center self-start rounded-md bg-accent px-4 text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ i18n.t('item.styleAround') }}
          </a>
        }

        @if (row.user_edited) {
          <p class="text-sm">
            <span class="font-medium">{{ i18n.t('item.edited.badge') }}</span>
            — {{ i18n.t('item.edited.explain') }}
          </p>
        }

        <!-- 116 clears a failed status when a saved row carries every required tag, so
             a row still marked failed after a save is one that is genuinely
             short. The message is read off the status the response carried and
             never off a client-side copy of the required set — naming the
             missing field would need that copy, which is what B declined. -->
        @if (row.status === 'failed') {
          <p class="text-sm font-medium text-danger">{{ i18n.t('item.incomplete') }}</p>
        }

        @if (row.status === 'processing') {
          <p class="text-sm">{{ i18n.t('item.processing') }}</p>
        } @else {
          <section class="flex flex-col gap-3">
            <h2 class="font-display text-xl">{{ i18n.t('item.edit.title') }}</h2>
            <app-tag-editor
              [item]="row"
              [saving]="saving()"
              [errorKey]="saveError()"
              (save)="onSave($event)"
            />
          </section>
        }

        <section class="flex flex-col gap-2">
          <h2 class="font-display text-xl">{{ i18n.t('item.wear.title') }}</h2>
          <!-- Stage 3 adds wear_count and last_worn_at at migration 0003.
               There is nothing to read yet, so this says so rather than
               rendering a zero that would change meaning when the columns
               arrive — the same reasoning ItemStatsResponse already carries. -->
          <p class="text-sm">{{ i18n.t('item.wear.placeholder') }}</p>
        </section>

        <div class="flex flex-wrap items-center gap-3 border-t border-current/10 pt-4">
          <!-- One control, ungated. It sends the unforced retag; the 409 opens
               the second step. Gating it on user_edited and forcing straight
               away would mean the 409 is never produced from the UI, and
               acceptance criterion 6 would stay a route test. 122. -->
          <button
            type="button"
            (click)="retag()"
            [disabled]="retagging()"
            class="min-h-11 rounded-md px-3 text-sm underline disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ retagging() ? i18n.t('item.retag.working') : i18n.t('item.retag.action') }}
          </button>

          <!-- Two deliberate clicks, not window.confirm and not a modal. The
               gate's confirm() returns undefined, so a confirm-guarded delete
               would read as tested and never run — 098 with a sharper edge. A
               modal was declined on cost: a fourth hand-rolled focus trap,
               with inert unsupported, to guard a misclick two clicks already
               guard. DECISIONS.md 126. -->
          <button
            type="button"
            (click)="onDelete()"
            (blur)="disarm()"
            [disabled]="deleting()"
            class="min-h-11 rounded-md px-3 text-sm underline disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            [class.text-danger]="armed()"
            [class.font-medium]="armed()"
          >
            {{ deleteLabel() }}
          </button>
        </div>

        @if (armed()) {
          <p class="text-sm">{{ i18n.t('item.delete.arm') }}</p>
        }

        @if (retagConflict()) {
          <div class="flex flex-col items-start gap-2 rounded-lg bg-surface p-3">
            <p class="text-sm font-medium">{{ i18n.t('item.retag.confirm') }}</p>
            <div class="flex flex-wrap gap-3">
              <button
                type="button"
                (click)="retag(true)"
                class="min-h-11 rounded-md px-3 text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                {{ i18n.t('item.retag.confirmAction') }}
              </button>
              <button
                type="button"
                (click)="dismissConflict()"
                class="min-h-11 rounded-md px-3 text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                {{ i18n.t('item.retag.cancel') }}
              </button>
            </div>
          </div>
        }

        @if (actionError(); as key) {
          <p class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
        }
      } @else if (loadError()) {
        <p class="text-sm font-medium text-danger">{{ i18n.t('item.error.load') }}</p>
      }
    </main>
  `,
})
export class ItemDetailPage {
  protected readonly i18n = inject(I18nService);
  private readonly store = inject(WardrobeStore);
  private readonly api = inject(ItemsApi);
  private readonly router = inject(Router);

  // Read from the snapshot, not a subscription: nothing changes `:id` under
  // this component — every route into it is a fresh navigation from the grid.
  // 1.11 adding next/prev on this screen is what would break that, and it is
  // named here rather than left for whoever writes it. DECISIONS.md 127.
  private readonly id = inject(ActivatedRoute).snapshot.paramMap.get('id') ?? '';

  // The row fetched by id when the collection has none, kept beside `items()`
  // and never written into it. A deep-linked row therefore does not live-update
  // — the poll derives from `items()` — which is honest rather than accidental:
  // the poll is stopped on this route anyway, because WardrobePage's DestroyRef
  // stops it on navigation away. DECISIONS.md 127.
  private readonly fetched = signal<Item | null>(null);
  protected readonly loadError = signal(false);

  protected readonly saving = signal(false);
  protected readonly saveError = signal<string | null>(null);
  protected readonly retagging = signal(false);
  protected readonly retagConflict = signal(false);
  protected readonly deleting = signal(false);
  protected readonly armed = signal(false);
  protected readonly actionError = signal<string | null>(null);

  protected readonly item = computed(
    () => this.store.items().find((candidate) => candidate.id === this.id) ?? this.fetched(),
  );

  protected readonly deleteLabel = computed(() => {
    if (this.deleting()) {
      return this.i18n.t('item.delete.working');
    }
    return this.armed() ? this.i18n.t('item.delete.arm') : this.i18n.t('item.delete.action');
  });

  constructor() {
    if (this.item() === null) {
      this.api.get(this.id).subscribe({
        next: (item) => this.fetched.set(item),
        error: () => this.loadError.set(true),
      });
    }
  }

  protected onSave(changes: ItemUpdate): void {
    this.disarm();
    this.saving.set(true);
    this.saveError.set(null);

    this.store.edit(this.id, changes).subscribe({
      next: (item) => {
        // Written to the fallback too, so a deep-linked row shows its own save.
        if (this.fetched() !== null) {
          this.fetched.set(item);
        }
        this.saving.set(false);
      },
      // One string for every rejection. 04-API-SPEC.md names the offending
      // field inside `detail`, and CONVENTIONS.md forbids rendering a raw
      // error, so this cannot say which field — recorded as a limitation the
      // way 099 recorded the filename it cannot show. DECISIONS.md 128.
      error: () => {
        this.saveError.set('item.error.save');
        this.saving.set(false);
      },
    });
  }

  protected retag(force = false): void {
    this.disarm();
    this.retagging.set(true);
    this.retagConflict.set(false);
    this.actionError.set(null);

    this.api.retag(this.id, force).subscribe({
      next: () => {
        this.retagging.set(false);
        // The row is `processing` now and this editor must not be open on one
        // (STAGE-1 1.9). Leaving is the same rule the deep-link guard applies,
        // one second later.
        void this.router.navigate(['/wardrobe']);
      },
      error: (error: unknown) => {
        this.retagging.set(false);
        if (error instanceof HttpErrorResponse && this.code(error) === 'item_edited') {
          this.retagConflict.set(true);
          return;
        }
        this.actionError.set('item.retag.error');
      },
    });
  }

  protected dismissConflict(): void {
    this.retagConflict.set(false);
  }

  protected onDelete(): void {
    if (!this.armed()) {
      this.armed.set(true);
      return;
    }
    this.armed.set(false);
    this.deleting.set(true);
    this.actionError.set(null);

    this.store.archive(this.id).subscribe({
      next: () => {
        this.deleting.set(false);
        void this.router.navigate(['/wardrobe']);
      },
      error: () => {
        this.deleting.set(false);
        this.actionError.set('item.error.delete');
      },
    });
  }

  // Any other interaction disarms, not only blur: an armed delete that survives
  // a save or a retag is a second click landing on a control the user has
  // stopped thinking about.
  protected disarm(): void {
    this.armed.set(false);
  }

  private code(error: HttpErrorResponse): string | undefined {
    return (error.error as { code?: string } | null)?.code;
  }
}

import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { I18nService } from '../../core/i18n/i18n.service';
import { Item } from '../../shared/models/item.model';

@Component({
  selector: 'app-item-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <article class="relative aspect-square overflow-hidden rounded-lg bg-surface shadow-sm">
      <!-- The photograph is on the wire from the first response, so a
           processing tile dims it rather than replacing it with a blank
           skeleton: the user has just photographed this garment and it is the
           only thing on screen telling them the upload worked. This departs
           from 05-FRONTEND-SPEC.md's original grid legend, which the same
           commit amends. DECISIONS.md 091. -->
      <!-- The image is the link and the retry button is its sibling, never
           inside it: an anchor containing a button is nested interactive
           content, which no browser agrees on and no screen reader announces
           twice the same way. How a user reaches item detail was specified in
           no document — 05's grid legend gave the tile one behaviour, "tap to
           retry" — so this is a decision rather than an implementation.
           DECISIONS.md 129. -->
      <a
        [routerLink]="['/wardrobe', item().id]"
        [attr.aria-label]="openLabel()"
        class="block h-full w-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <img
          [src]="item().image_url"
          [alt]="alt()"
          loading="lazy"
          class="h-full w-full object-contain"
          [class.opacity-30]="item().status !== 'ready'"
        />
      </a>

      @if (item().status === 'processing' && !gaveUp()) {
        <p class="absolute inset-x-0 bottom-0 bg-surface/90 p-1 text-center text-xs">
          {{ i18n.t('wardrobe.item.processing') }}
        </p>
      }

      <!-- Branches on status alone and never on "the tags are null": a retag
           leaves the previous attempt's tags in place, so a failed item may
           arrive fully tagged or not tagged at all. DECISIONS.md 089.
           The second condition is not a status and does not pretend to be —
           the server still calls this row processing and may yet finish it. -->
      @if (item().status === 'failed' || gaveUp()) {
        <div
          class="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-surface/90 p-1 text-center"
        >
          <!-- No danger token on the second one. 057 reserves it for something
               being wrong, and nothing is: we stopped watching, which is not
               the same claim as tagging having failed. DECISIONS.md 105. -->
          @if (gaveUp()) {
            <p class="text-xs">{{ i18n.t('wardrobe.item.stoppedWaiting') }}</p>
          } @else {
            <p class="text-xs font-medium text-danger">
              <span aria-hidden="true">⚠</span> {{ i18n.t('wardrobe.item.failed') }}
            </p>
          }
          <!-- O-3's "Add manually", promised by 03 line 401 since it was
               written and built by no task until now. It is this editor,
               reached from the failed tile, and it works because 116 lets a
               completed edit clear the failed status. -->
          <a
            [routerLink]="['/wardrobe', item().id]"
            class="inline-flex min-h-11 items-center justify-center rounded-md px-2 text-xs underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ i18n.t('wardrobe.item.addManually') }}
          </a>
          <button
            type="button"
            (click)="retry.emit()"
            [disabled]="retrying()"
            [attr.aria-label]="retryLabel()"
            class="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md px-2 text-xs underline disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ retrying() ? i18n.t('wardrobe.item.retrying') : i18n.t('wardrobe.item.retry') }}
          </button>
          @if (errorKey(); as key) {
            <p class="text-xs font-medium text-danger">{{ i18n.t(key) }}</p>
          }
        </div>
      }
    </article>
  `,
})
export class ItemCard {
  protected readonly i18n = inject(I18nService);

  readonly item = input.required<Item>();
  readonly retrying = input(false);
  readonly errorKey = input<string | null>(null);
  readonly stoppedWaiting = input(false);

  readonly retry = output<void>();

  // Read with the status, never alone. A stopped-waiting id outlives its row
  // until the next load(), so on an item that has since come back `ready` the
  // flag is stale and must draw nothing — the same conjunction that makes
  // 093's leftover `retagErrors` keys harmless.
  protected readonly gaveUp = computed(
    () => this.item().status === 'processing' && this.stoppedWaiting(),
  );

  // Trimmed rather than ??: display_name is null while an item is processing
  // and stays null on one that never tagged successfully, and an empty alt on
  // a photograph is worse than a generic one. Same shape as userLabel (071).
  protected readonly alt = computed(() => {
    const name = this.item().display_name?.trim();
    return name ? name : this.i18n.t('wardrobe.item.untagged');
  });

  // The button's own text says only "Try again", which names no garment when a
  // screen reader lists the buttons on a full grid of failures.
  protected readonly retryLabel = computed(() =>
    this.i18n.t('wardrobe.item.retryLabel', { name: this.alt() }),
  );

  // Same problem one control over: the link's only content is an image, so
  // without this a screen reader announces the alt text as the link name and a
  // grid of untagged items reads as forty identical links.
  protected readonly openLabel = computed(() =>
    this.i18n.t('wardrobe.item.open', { name: this.alt() }),
  );
}

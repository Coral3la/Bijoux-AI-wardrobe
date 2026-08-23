import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';
import { PendingUpload } from '../../core/state/wardrobe.store';

@Component({
  selector: 'app-pending-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (pending().length > 0) {
      <section class="flex flex-col gap-2" aria-live="polite">
        <p class="text-sm">{{ label() }}</p>
        <!-- A strip above the grid rather than tiles inside it. These are files,
             not rows: they have no id, no status and no short_id, so faking an
             Item to place them in grid position would put invented values on the
             one model 059 says mirrors the wire field for field. The cost is
             that for a second or two the newest garments sit here instead of in
             the grid, and the swap is visual. DECISIONS.md 097. -->
        <ul class="flex gap-3 overflow-x-auto">
          @for (entry of pending(); track entry.key) {
            <li class="shrink-0">
              <img
                [src]="entry.url"
                [alt]="alt(entry.name)"
                class="h-24 w-24 rounded-lg object-contain opacity-60 shadow-sm"
              />
            </li>
          }
        </ul>
      </section>
    }
  `,
})
export class PendingStrip {
  protected readonly i18n = inject(I18nService);

  readonly pending = input.required<readonly PendingUpload[]>();

  // Two keys and a ternary, because I18nService has no plural rule and one
  // string reading "1 items" is a visible defect on the commonest upload
  // there is — a single photograph. DECISIONS.md 095.
  protected readonly label = computed(() => {
    const count = this.pending().length;
    return count === 1
      ? this.i18n.t('wardrobe.upload.pending.one')
      : this.i18n.t('wardrobe.upload.pending.other', { count });
  });

  // The filename is the only thing distinguishing one preview from another to
  // a screen reader, and it is user data, so it goes through the body face
  // rule the same way display_name does. DECISIONS.md 071.
  protected alt(name: string): string {
    return this.i18n.t('wardrobe.upload.preview', { name });
  }
}

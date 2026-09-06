import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';
import { CATEGORIES, Category } from '../../shared/models/enums';
import { Item } from '../../shared/models/item.model';
import { Button } from '../../shared/ui/button';
import { Chip } from '../../shared/ui/chip';

@Component({
  selector: 'app-set-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, Chip],
  template: `
    <!-- A plain element, not <dialog>, and upload-sheet.ts is where that was
         decided: jsdom implements neither showModal nor show nor close
         (measured at 1.6), so a dialog-based sheet could not be opened by any
         test in this project. DECISIONS.md 098. This is the second sheet, which
         is the condition AUDITS.md O-15 named for extracting a shared one — and
         the extraction is deliberately not done here, because it would edit
         upload-sheet.ts for no change in behaviour. -->
    <div class="fixed inset-0 z-40 flex flex-col justify-end">
      <button
        type="button"
        (click)="dismissed.emit()"
        [attr.aria-label]="i18n.t('item.set.pick.dismiss')"
        class="absolute inset-0 bg-ink/40"
      ></button>

      <section
        role="dialog"
        aria-modal="true"
        [attr.aria-label]="i18n.t('item.set.pick.title')"
        class="relative flex max-h-[80vh] flex-col gap-4 overflow-y-auto rounded-t-2xl bg-surface p-6 shadow-lg"
      >
        <h2 class="font-display text-2xl leading-tight">{{ i18n.t('item.set.pick.title') }}</h2>

        @if (errorKey(); as key) {
          <p class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
        }

        <!-- Every category, including the ones with nothing under them, which
             is filter-bar.ts's rule rather than a copy of its markup: the chips
             are the closed vocabulary and not a summary of what is in the
             wardrobe, so a row that grew and shrank as the user typed would
             move under their finger. appChip paints and announces from one
             input, and no aria-pressed is bound here — a template binding
             outranks a directive host binding, which is how the announced state
             drifts from the painted one. DECISIONS.md 219, 222. -->
        <div class="flex flex-wrap items-center gap-1.5">
          <button
            appChip
            type="button"
            class="shrink-0"
            [active]="category() === null"
            (click)="choose(null)"
          >
            {{ i18n.t('item.set.pick.all') }}
          </button>
          @for (option of categories; track option) {
            <button
              appChip
              type="button"
              class="shrink-0"
              [active]="category() === option"
              (click)="choose(option)"
            >
              {{ i18n.t('vocabulary.category.' + option) }}
            </button>
          }
        </div>

        @if (visible().length === 0) {
          <p class="max-w-prose text-sm text-ink-muted">{{ i18n.t('item.set.pick.empty') }}</p>
        } @else {
          <ul class="grid grid-cols-3 gap-x-3 gap-y-5 md:grid-cols-5">
            @for (candidate of visible(); track candidate.id) {
              <li>
                <!-- A button, not the anchor ItemCard draws: a tile here picks
                     a garment rather than navigating to it, and reusing that
                     component would put a link into a sheet whose whole purpose
                     is to be chosen from. The photograph's alt is empty because
                     the name is printed inside the same button — with alt text
                     it would be announced twice. -->
                <button
                  type="button"
                  (click)="picked.emit(candidate)"
                  [disabled]="saving()"
                  class="flex w-full flex-col gap-2 text-start disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  <img
                    [src]="candidate.image_url"
                    alt=""
                    loading="lazy"
                    class="aspect-4/5 w-full rounded-[2px] object-contain"
                  />
                  <span class="font-sans text-sm text-ink">{{ name(candidate) }}</span>
                </button>
              </li>
            }
          </ul>
        }

        <button
          appButton
          variant="ghost"
          type="button"
          (click)="dismissed.emit()"
          class="self-start"
        >
          {{ i18n.t('item.set.pick.dismiss') }}
        </button>
      </section>
    </div>
  `,
})
export class SetPicker {
  protected readonly i18n = inject(I18nService);
  protected readonly categories = CATEGORIES;

  // The whole loaded wardrobe, not a pre-filtered list: the three exclusions
  // below are what this component is for, and a caller that applied them would
  // leave them untested here and duplicated at the next caller.
  readonly items = input.required<readonly Item[]>();
  readonly currentItemId = input.required<string>();
  readonly saving = input(false);
  readonly errorKey = input<string | null>(null);

  readonly picked = output<Item>();
  // Not `close`: @angular-eslint/no-output-native refuses an output named after
  // a standard DOM event, because a native close event would fire the binding.
  readonly dismissed = output<void>();

  protected readonly category = signal<Category | null>(null);

  // Three exclusions, and each one is a request the server would refuse.
  // The garment on screen cannot be its own set-mate; a garment with a set_id
  // is 422 set_member_taken (this set included, where the answer would be a
  // 200 that changes nothing and a sheet that appears to have done nothing);
  // and a row that is not `ready` is 422 set_item_unavailable, which is the
  // gate item-detail.page.ts already puts on *Style around this* for the same
  // reason. What is deliberately **not** excluded is the category: the server's
  // excluded list is configuration (STYLIST_EXCLUDED_CATEGORIES, swimwear and
  // sleepwear by default), this client has no copy of it, and inventing one
  // would be a hand-mirrored constant with nothing watching it — so a swimsuit
  // is offered here and refused on the wire, with the refusal rendered.
  //
  // Order is the collection's, which GET /items returns created_at DESC:
  // filtering preserves it, so the newest garment is first without a sort.
  protected readonly candidates = computed(() =>
    this.items().filter(
      (candidate) =>
        candidate.id !== this.currentItemId() &&
        candidate.set_id === null &&
        candidate.status === 'ready',
    ),
  );

  protected readonly visible = computed(() => {
    const wanted = this.category();
    return wanted === null
      ? this.candidates()
      : this.candidates().filter((candidate) => candidate.category === wanted);
  });

  // Self-clearing like the filter bar's: pressing the pressed chip goes back to
  // All rather than leaving the row with no way out of a category.
  protected choose(option: Category | null): void {
    this.category.update((current) => (current === option ? null : option));
  }

  // Trimmed rather than ??, on item-card.ts's reasoning: display_name is null
  // on a garment that never tagged. Every candidate here is `ready` and so
  // carries one, which is why this is a fallback and not a branch anybody sees.
  protected name(candidate: Item): string {
    const name = candidate.display_name?.trim();
    return name ? name : this.i18n.t('item.untitled');
  }
}

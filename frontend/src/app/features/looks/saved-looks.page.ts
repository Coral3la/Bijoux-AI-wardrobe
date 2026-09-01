import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { I18nService } from '../../core/i18n/i18n.service';
import { LooksStore } from '../../core/state/looks.store';
import { OCCASIONS, Occasion } from '../../shared/models/enums';
import { Look } from '../../shared/models/look.model';
import { Button } from '../../shared/ui/button';
import { EmptyState } from '../../shared/ui/empty-state';
import { Skeleton } from '../../shared/ui/skeleton';
import { todayInLocalTime } from '../stylist/look-request-form';
import { ItemCard } from '../wardrobe/item-card';

// Two, not a guess at how many looks are saved: the skeleton promises the
// shape of the screen, and a stack of two says "a stack" without claiming a
// length the response has not arrived to confirm.
const LOADING_CARDS = [0, 1] as const;

// Four, which is the strip a row draws and not a guess either: every look this
// screen has ever rendered came back with four garments or close to it, and the
// promise a skeleton makes is about shape rather than count.
const LOADING_PLATES = [0, 1, 2, 3] as const;

// The second declaration of this string in the application — look-card.ts has
// the first, and the two are identical because the control is the same control
// on two screens. 220 called a third instance of a duplicated class string the
// point at which the shared directive should absorb it; this is the second, and
// it is recorded rather than fixed here because `appButton` has not had its own
// Atelier pass and converting it would reach every screen in the product.
const ICON_BUTTON =
  'inline-flex h-11 w-11 items-center justify-center rounded-full border text-base disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

// 44px and not the mockup's 40, which is the same floor the look card's
// controls took from the same picture. The type is the caps-letter-spaced
// treatment every authored control on a converted screen uses.
const WEAR_BUTTON =
  'inline-flex min-h-11 items-center rounded-full border px-5 text-[11px] font-medium tracking-[0.22em] uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

// `looks.occasion` is TEXT on the server and a plain string on the wire — the
// request schema is the only thing that has ever narrowed it (look.model.ts) —
// and `t()` renders a missing key as itself, so an unrecognised value would
// print `vocabulary.occasion.…` at the reader. Same guard the look card puts in
// front of a missing piece's category, for the same reason.
function isOccasion(value: string): value is Occasion {
  return (OCCASIONS as readonly string[]).includes(value);
}

// Deliberately not LookCard. That component is the stylist's payoff — it heads
// with the parameters the request carried, puts a ↻ badge on every garment and
// ends in "Try again", none of which a saved look can do: there is no request
// behind it to re-run. It grouped by layer too until DR.20 dropped the grouping,
// which retires one of the grounds and leaves the rest. What a list needs is the
// title, the garments in the model's own order, and the heart that takes it
// back out. Reusing the card would have meant two inputs whose
// only job is to switch its own features off. 05-FRONTEND-SPEC.md draws no
// screen for this at all — the amendment in the same commit is what adds it.
@Component({
  selector: 'app-saved-looks-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, EmptyState, ItemCard, RouterLink, Skeleton],
  template: `
    <!-- 980px rather than the 2xl this held before. The row is 320px of
         photographs plus a body plus a pair of controls, and at 672px the body
         had about 300px to live in — the width is what the layout costs, not a
         preference. DECISIONS.md 221. -->
    <main
      class="mx-auto flex w-full max-w-[980px] flex-col gap-region px-6 pt-hero pb-region md:px-14"
    >
      <header
        class="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 border-b border-line pb-4"
      >
        <h1 class="font-display text-[48px] leading-[0.95] font-light tracking-[-0.02em]">
          {{ i18n.t('saved.title') }}
        </h1>
        <!-- Present whenever there are rows, including the moment the last
             heart is emptied: the row stays on screen until the next load, and
             a count that read "1 saved" over a look nobody has saved would be
             the one thing on the header telling a lie. It says "0 saved" for
             exactly as long as that row is undoable. -->
        @if (store.looks().length > 0) {
          <p class="font-mono text-[13px] tracking-[0.02em] text-ink-muted tabular-nums">
            {{ countLabel() }}
          </p>
        }
      </header>

      @if (store.error(); as key) {
        <p class="text-sm font-medium text-danger" role="alert">{{ i18n.t(key) }}</p>
      }

      @if (store.isLoading()) {
        <!-- Two rows rather than a list-length guess, and the row's own shape
             rather than a block: a strip of four plates and the two lines of
             text beside them, which is what makes this read as progress instead
             of as a placeholder. The plates carry no aria-hidden of their own —
             Skeleton's host has it — so the status line is the whole of what is
             announced. DECISIONS.md 217, 221. -->
        <div class="animate-deferred flex flex-col gap-group">
          <div class="flex flex-col">
            @for (card of loadingCards; track card) {
              <div
                class="grid gap-5 border-b border-line py-5 last:border-b-0 md:grid-cols-[320px_1fr] md:items-center md:gap-8"
              >
                <div class="grid max-w-[320px] grid-cols-4 gap-1.5">
                  @for (plate of loadingPlates; track plate) {
                    <app-skeleton class="aspect-4/5" radius="rounded-[2px]" />
                  }
                </div>
                <div class="flex flex-col gap-2">
                  <app-skeleton class="h-5 w-2/3" radius="rounded-[2px]" />
                  <app-skeleton class="h-4 w-1/2" radius="rounded-[2px]" />
                </div>
              </div>
            }
          </div>
          <p class="font-prose text-base text-ink-muted italic" role="status" aria-live="polite">
            {{ i18n.t('saved.loading') }}
          </p>
        </div>
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
        <!-- One row per look, on the canvas, separated by a hairline and by
             nothing else. The card this screen used to draw was the only raised
             object on a page whose subject is photographs, and a stack of them
             put a border around every look to keep it apart from a look that is
             already 40px away. DECISIONS.md 221. -->
        <ul class="flex flex-col">
          @for (look of store.looks(); track look.id) {
            <li
              class="grid gap-5 border-b border-line py-5 last:border-b-0 md:grid-cols-[320px_1fr_auto] md:items-center md:gap-8"
            >
              <!-- In the order the server sent, which is look_items.position
                   and therefore the model's own. No layer grouping: a list is
                   scanned rather than read, and the headings that help on one
                   card are noise repeated down a page of them.

                   Captions off, which is what the input the stylist added
                   exists for: at a quarter of 320px a garment's name and its
                   colour are unreadable, and the row's own body already says
                   what this look is. The plates stay 4:5 rather than the
                   mockup's squares — the ratio is the wardrobe's and the look
                   card's, and a third crop for the same photograph is a
                   difference no reader could account for. -->
              <ul class="grid max-w-[320px] grid-cols-4 gap-1.5">
                @for (item of look.items; track item.id) {
                  <li><app-item-card [item]="item" [caption]="false" /></li>
                }
              </ul>

              <div class="flex min-w-0 flex-col gap-1">
                <!-- Where the mockup drew the day this look was saved. Nothing
                     on the wire carries one — LookResponse has worn_at and no
                     created_at — so the slot takes the fact the row does have
                     and the screen was otherwise missing: what the look was
                     asked for. It is our closed vocabulary, so it keeps the
                     authored mono treatment the mockup's date had. No backtick
                     in this comment, which lives inside a template literal.
                     DECISIONS.md 221. -->
                @if (occasionLabel(look); as occasion) {
                  <p class="font-mono text-[10px] tracking-[0.24em] text-ink-soft uppercase">
                    {{ occasion }}
                  </p>
                }
                <!-- The content face at a display size. The picked mockup draws
                     this in Cormorant and 071 wins, exactly as it won on the
                     look card's title and the wardrobe tile's caption: the
                     title was composed by the model, so what it gains in a
                     redesign is size and leading and never a face.
                     DECISIONS.md 071, 221. -->
                <h2 class="font-sans text-[22px] leading-tight">{{ look.title }}</h2>
                <p class="font-sans text-sm text-ink-muted italic">{{ look.weather_note }}</p>
              </div>

              <div class="flex items-center gap-2">
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
                  [class]="heartClass(look)"
                >
                  <span aria-hidden="true">{{ look.is_saved ? '♥' : '♡' }}</span>
                </button>

                <!-- Beside the heart rather than under the garments, which
                     reverses 05-FRONTEND-SPEC.md's placement and keeps its
                     reasoning: "a text label does not sit in a row built for a
                     glyph" was true of a column of cards and is not true of a
                     row whose third column is the controls. The heart is about
                     this list and this is about today; they are still two
                     controls, now adjacent.

                     It stays on screen after a successful tap, disabled and
                     relabelled, because the state is worth showing — and the
                     endpoint is idempotent for exactly this date anyway, so a
                     client that retries costs nothing. It does not become a
                     toggle: there is no way to un-wear a look. The worn state
                     is the only visible signal that a look was worn today; the
                     mockup also drew a badge beside the title, and one fact
                     stated twice on one row is what that badge was.

                     No dimming on the worn variant, unlike the filled one:
                     that state is permanent for the day and reads
                     as a completed thing rather than as a dead control, where
                     the filled button is only ever disabled while another row's
                     write is in flight. -->
                <button
                  type="button"
                  (click)="wear(look)"
                  [disabled]="store.updatingId() !== null || wornToday(look)"
                  [class]="wearClass(look)"
                >
                  @if (wornToday(look)) {
                    <span aria-hidden="true" class="me-2">✓</span>
                  }
                  {{ wornToday(look) ? i18n.t('saved.wear.done') : i18n.t('saved.wear') }}
                </button>
              </div>
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

  protected readonly loadingCards = LOADING_CARDS;
  protected readonly loadingPlates = LOADING_PLATES;

  // I18nService has no plural rule (DECISIONS.md 058), so the caller picks the
  // key. Counted off `is_saved` and not off the rows: the list keeps a look
  // that has just been unsaved, so counting rows would make the header claim a
  // save the empty heart under it denies.
  protected readonly countLabel = computed(() => {
    const count = this.store.looks().filter((look) => look.is_saved).length;
    return count === 1
      ? this.i18n.t('saved.count.one')
      : this.i18n.t('saved.count.other', { count });
  });

  constructor() {
    // Reset before loading, for StylistPage's reason: the store is
    // providedIn: 'root' and a second visit arrives holding the first visit's
    // list, which would be on screen under the spinner.
    this.store.reset();
    this.store.loadSaved();
  }

  protected occasionLabel(look: Look): string | null {
    return isOccasion(look.occasion) ? this.i18n.t(`vocabulary.occasion.${look.occasion}`) : null;
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

  // Written out rather than bound class by class, for the look card's reason:
  // the saved heart changes three properties at once and a chain of [class.x]
  // bindings for one state is harder to read than one string.
  protected heartClass(look: Look): string {
    return look.is_saved
      ? `${ICON_BUTTON} border-accent bg-accent text-canvas`
      : `${ICON_BUTTON} border-line text-ink`;
  }

  protected wearClass(look: Look): string {
    return this.wornToday(look)
      ? `${WEAR_BUTTON} border-line text-ink-muted`
      : `${WEAR_BUTTON} border-ink bg-ink text-canvas disabled:opacity-50`;
  }
}

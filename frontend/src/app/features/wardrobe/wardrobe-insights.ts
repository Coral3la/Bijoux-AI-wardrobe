import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ItemsApi } from '../../core/api/items.api';
import { I18nService } from '../../core/i18n/i18n.service';
import { ItemStatsResponse, MostWornItem } from '../../shared/models/item.model';

// Built rather than read off a signal per line, because "is there a panel" and
// "what does it say" are one question here: the panel exists exactly when
// there is a true sentence to put in it. One computed decides, so no branch
// can render a heading over nothing.
interface Insights {
  readonly line: string;
  // Whether that line leads anywhere. The all-worn sentence does not — there is
  // no list of never-worn garments behind it — so the branch is carried here
  // rather than re-derived in the template from a number it no longer holds.
  readonly neverWorn: boolean;
  readonly mostWorn: { readonly id: string; readonly line: string } | null;
}

// Atelier reaches this panel through the tokens and no further: the card is a
// warm paper on cream rather than a white slab because `--color-surface` moved,
// and the face, the size and the shadow are still 3.6's. The typographic pass
// belongs to this panel's own pitch. DECISIONS.md 219.
@Component({
  selector: 'app-wardrobe-insights',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    @if (insights(); as panel) {
      <section
        class="flex flex-col items-start gap-2 rounded-xl bg-surface p-4 shadow-sm"
        [attr.aria-label]="i18n.t('wardrobe.insights.region')"
      >
        <!-- The whole sentence takes the display face, not the two numbers
             inside it. Emphasising the numerals alone would mean splitting one
             i18n key into fragments, and a sentence assembled from pieces
             cannot be reordered for a language that words it differently. The
             line carries no user data, so Fraunces is legal across all of it —
             which the link below is not: it interpolates a garment name.

             That same rule is why the *sentence* is the anchor and not the
             number 3.6a asked for: the number cannot be linked without the
             fragmentation the paragraph above refuses, and the sentence is the
             smallest unit that can. It also leaves the accessible name equal to
             the visible text, where an aria-label naming the destination would
             not contain it. No queryParamsHandling, so a category already on is
             dropped rather than intersected — the count this line states is
             over the whole wardrobe, and landing filtered would show a subset
             of it under the number that promised the whole. DECISIONS.md 228. -->
        @if (panel.neverWorn) {
          <a
            routerLink="/wardrobe"
            [queryParams]="{ never_worn: 'true' }"
            class="font-display text-lg underline decoration-1 underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ panel.line }}
          </a>
        } @else {
          <p class="font-display text-lg">{{ panel.line }}</p>
        }
        <!-- The link the most_worn field was narrowed to three fields to
             carry: an id, because the one garment named on this panel is the
             one the user is most likely to want to look at. -->
        @if (panel.mostWorn; as garment) {
          <a
            [routerLink]="['/wardrobe', garment.id]"
            class="inline-flex min-h-11 items-center rounded-md text-sm text-ink-muted underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {{ garment.line }}
          </a>
        }
      </section>
    }
  `,
})
export class WardrobeInsights {
  protected readonly i18n = inject(I18nService);
  private readonly api = inject(ItemsApi);

  private readonly stats = signal<ItemStatsResponse | null>(null);

  protected readonly insights = computed<Insights | null>(() => {
    const stats = this.stats();
    // Nothing worn is not an insight. The only sentence available on a
    // brand-new wardrobe is "you have never worn any of these 40 items",
    // which the user knows and which is false about her life rather than
    // about the data — the application has not been told yet, that is all.
    // `most_worn` is null in exactly this case, so the link below needs no
    // second guard. DECISIONS.md 188.
    if (stats === null || stats.worn === 0) {
      return null;
    }
    // One test, where reading it in both places would be two: what the line
    // says and whether it leads anywhere are the same question about the same
    // number. Never printed as "0 pieces you have never worn", which reads as a
    // boast about a number rather than a fact about a wardrobe.
    const neverWorn = stats.never_worn > 0;
    return {
      line: neverWorn ? this.neverWornLine(stats) : this.i18n.t('wardrobe.insights.allWorn'),
      neverWorn,
      mostWorn:
        stats.most_worn === null
          ? null
          : { id: stats.most_worn.id, line: this.mostWornLine(stats.most_worn) },
    };
  });

  // Fails silently and takes the panel with it, which is WeatherStrip's rule
  // and the same reasoning: statistics are context on a screen that works
  // without them, and a red banner over a healthy wardrobe would report a
  // failure the user did not ask about and cannot act on. DECISIONS.md 180.
  //
  // Once, on construction. Angular re-creates this component on every entry to
  // /wardrobe, so coming back from a wearing recorded on /stylist refetches;
  // what it does not do is follow an archive made on the item screen behind it
  // within one visit. DECISIONS.md 188.
  constructor() {
    this.api.stats().subscribe({
      next: (stats) => this.stats.set(stats),
      error: () => this.stats.set(null),
    });
  }

  // The denominator is `worn + never_worn` and never `total`: the pair is
  // scoped to `ready` rows and `total` counts every status, so a wardrobe with
  // two failed uploads would put 136 on this line under a header saying 138.
  // "Tagged" is what makes that gap legible rather than arithmetic — it is the
  // word the grid already uses for the same population. DECISIONS.md 188.
  //
  // I18nService has no plural rule (DECISIONS.md 058), so the caller picks the
  // key. `ready` needs no singular of its own: this line renders only when both
  // counts are at least 1, so it is at least 2 by construction.
  private neverWornLine(stats: ItemStatsResponse): string {
    const ready = stats.worn + stats.never_worn;
    return stats.never_worn === 1
      ? this.i18n.t('wardrobe.insights.neverWorn.one', { ready })
      : this.i18n.t('wardrobe.insights.neverWorn.other', { count: stats.never_worn, ready });
  }

  private mostWornLine(garment: MostWornItem): string {
    const name = garment.display_name ?? this.i18n.t('item.untitled');
    return garment.wear_count === 1
      ? this.i18n.t('wardrobe.insights.mostWorn.one', { name })
      : this.i18n.t('wardrobe.insights.mostWorn.other', { name, count: garment.wear_count });
  }
}

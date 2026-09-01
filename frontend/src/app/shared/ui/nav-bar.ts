import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';

// The five top-level screens, in the order a session uses them: the wardrobe is
// where every session lands, the stylist and the trips are what it is for, and
// the last two are places you come back to rather than work from. `/wardrobe/:id`
// and `/trips/:id` are children of entries here and get no entry of their own.
export const NAV_ITEMS = [
  { path: '/wardrobe', key: 'nav.wardrobe' },
  { path: '/stylist', key: 'nav.stylist' },
  { path: '/trips', key: 'nav.trips' },
  { path: '/saved', key: 'nav.saved' },
  { path: '/profile', key: 'nav.profile' },
] as const;

@Component({
  selector: 'app-nav-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RouterLinkActive],
  template: `
    <nav
      class="sticky top-0 z-40 flex items-center gap-x-1 overflow-x-auto bg-canvas px-4 shadow-sm"
      [attr.aria-label]="i18n.t('nav.region')"
    >
      @for (entry of items; track entry.path) {
        <!-- routerLinkActive is left at its default matching, which is the whole
             of the active rule and the one line here that had to be decided.
             Non-exact compares the link's segments as a prefix and its query
             params as a subset, and these links carry none — so /wardrobe stays
             lit on /wardrobe/:id and under ?category=tops, which the grid writes
             on every filter change. An exact option compares query params
             exactly and would switch this off the first time anybody filters. -->
        <!-- The muted colour is a class binding off the directive's own
             isActive rather than a second class in the static list: text-accent
             and text-ink-muted set the same property, and two utilities for one
             property are settled by the order of the compiled stylesheet, not
             by the order they are written here. Bound, the inactive colour is
             simply absent whenever the active one is present. -->
        <a
          [routerLink]="entry.path"
          routerLinkActive="bg-accent-wash font-medium text-accent"
          #active="routerLinkActive"
          ariaCurrentWhenActive="page"
          [class.text-ink-muted]="!active.isActive"
          class="inline-flex min-h-11 shrink-0 items-center rounded-md px-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {{ i18n.t(entry.key) }}
        </a>
      }

      <!-- Last and pushed to the end, because it is the one control here that
           does not navigate between screens: it ends the session. It moved from
           the wardrobe's account row with the two links above it. -->
      <button
        type="button"
        (click)="signOut()"
        class="ms-auto inline-flex min-h-11 shrink-0 items-center rounded-md px-2 text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('nav.signOut') }}
      </button>
    </nav>
  `,
})
export class NavBar {
  protected readonly i18n = inject(I18nService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly items = NAV_ITEMS;

  // Lifted from wardrobe.page.ts unchanged, including the reason it navigates
  // rather than relying on the guard: no guard re-runs on a route that is
  // already active. DECISIONS.md 068.
  protected signOut(): void {
    this.auth.logout();
    void this.router.navigateByUrl('/login');
  }
}

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { NAV_ITEMS, NavBar } from './nav-bar';

let fixture: ComponentFixture<NavBar>;
let mock: HttpTestingController;
let router: Router;
const logout = vi.fn();

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function links(): HTMLAnchorElement[] {
  return [...element().querySelectorAll('a')];
}

function link(href: string): HTMLAnchorElement {
  const found = links().find((candidate) => candidate.getAttribute('href') === href);
  if (found === undefined) {
    throw new Error(`no link to ${href}`);
  }
  return found;
}

// The active state is read off aria-current rather than off the class, because
// aria-current is the half a screen reader gets and the half a Playwright
// locator can see. The class rides on the same directive input.
function current(): string[] {
  return links()
    .filter((candidate) => candidate.getAttribute('aria-current') === 'page')
    .map((candidate) => candidate.getAttribute('href') ?? '');
}

async function renderAt(url: string): Promise<void> {
  fixture = TestBed.createComponent(NavBar);
  await fixture.whenStable();
  await router.navigateByUrl(url);
  await fixture.whenStable();
}

describe('NavBar', () => {
  beforeEach(async () => {
    logout.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'wardrobe', children: [] },
          { path: 'wardrobe/:id', children: [] },
          { path: 'stylist', children: [] },
          { path: 'trips', children: [] },
          { path: 'trips/:id', children: [] },
          { path: 'saved', children: [] },
          { path: 'profile', children: [] },
          { path: 'login', children: [] },
        ]),
        { provide: AuthService, useValue: { logout } },
      ],
    });
    mock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    try {
      mock.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });

  it('carries one link per top-level screen, in order', async () => {
    await renderAt('/wardrobe');

    expect(links().map((candidate) => candidate.getAttribute('href'))).toEqual([
      '/wardrobe',
      '/stylist',
      '/trips',
      '/saved',
      '/profile',
    ]);
    expect(links().map((candidate) => candidate.textContent?.trim())).toEqual([
      en['nav.wardrobe'],
      en['nav.stylist'],
      en['nav.trips'],
      en['nav.saved'],
      en['nav.profile'],
    ]);
  });

  // The one thing O-29 was opened over: every screen is reachable from every
  // other one, rather than through the wardrobe or the address bar.
  it('reaches every route NAV_ITEMS names', async () => {
    await renderAt('/wardrobe');

    for (const entry of NAV_ITEMS) {
      expect(link(entry.path)).toBeDefined();
    }
  });

  it('names the landmark so a role locator can find it', async () => {
    await renderAt('/wardrobe');

    expect(element().querySelector('nav')?.getAttribute('aria-label')).toBe(en['nav.region']);
  });

  it('marks the current screen and only the current screen', async () => {
    await renderAt('/stylist');

    expect(current()).toEqual(['/stylist']);
  });

  // Decision 8, and the reason routerLinkActive is left at its default matching.
  // The grid writes ?category=tops on every filter change; under
  // `{ exact: true }` query params are compared exactly and the Wardrobe item
  // would go dark the first time anybody filters.
  it('stays on the wardrobe under a filter query parameter', async () => {
    await renderAt('/wardrobe?category=tops');

    expect(current()).toEqual(['/wardrobe']);
  });

  // The other half of the same rule: a child route lights its parent, so the
  // bar does not go blank on the two detail screens.
  it('marks the wardrobe on an item detail route', async () => {
    await renderAt('/wardrobe/item-1');

    expect(current()).toEqual(['/wardrobe']);
  });

  it('marks the trips entry on a packing view route', async () => {
    await renderAt('/trips/trip-1');

    expect(current()).toEqual(['/trips']);
  });

  // A prefix match must not spill sideways: /saved and /stylist share no
  // segment with /wardrobe, and nothing here should light two items at once.
  it('marks nothing else on a sibling route', async () => {
    await renderAt('/saved');

    expect(current()).toEqual(['/saved']);
  });

  it('signs out and leaves for the login screen', async () => {
    await renderAt('/wardrobe');

    const button = element().querySelector('button');
    expect(button?.textContent?.trim()).toBe(en['nav.signOut']);
    button?.click();
    await fixture.whenStable();

    expect(logout).toHaveBeenCalledOnce();
    expect(router.url).toBe('/login');
  });
});

import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { afterEach, describe, expect, it } from 'vitest';

import { routes } from './app.routes';
import { AuthService } from './core/auth/auth.service';

async function navigate(url: string): Promise<string> {
  TestBed.configureTestingModule({
    providers: [
      provideRouter(routes),
      { provide: AuthService, useValue: { isAuthenticated: () => true } },
    ],
  });
  const router = TestBed.inject(Router);
  await router.navigateByUrl(url);

  return router.url;
}

describe('routes', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('sends the empty path to the wardrobe', async () => {
    expect(await navigate('/')).toBe('/wardrobe');
  });

  // This exists to stop the tidy-up. `redirectTo: ''` removes the duplicated
  // destination below and does NOT chain through the empty-path route — it
  // lands on '/' with nothing rendered, for every mistyped or stale URL.
  // Measured at 0.9. DECISIONS.md 068.
  it('sends an unknown URL to the wardrobe rather than to a blank page', async () => {
    expect(await navigate('/does-not-exist')).toBe('/wardrobe');
  });

  // Above the wildcard like the three before it, and with the same failure if
  // it slips below: /saved would redirect to the grid and the screen would be
  // unreachable by any means at all, since nothing links to it either.
  it('resolves the saved-looks screen rather than falling through to the wildcard', async () => {
    expect(await navigate('/saved')).toBe('/saved');
  });

  // Declared above the wildcard. Below it, every item link would redirect to
  // the grid — which looks like a working app and silently loses the screen.
  it('resolves an item id rather than falling through to the wildcard', async () => {
    expect(await navigate('/wardrobe/item-1')).toBe('/wardrobe/item-1');
  });

  it('resolves the stylist rather than falling through to the wildcard', async () => {
    expect(await navigate('/stylist')).toBe('/stylist');
  });

  it('resolves the profile rather than falling through to the wildcard', async () => {
    expect(await navigate('/profile')).toBe('/profile');
  });

  // The one that matters most if it slips below the wildcard: nothing links to
  // /trips at all, so the URL is the only way in and a redirect would make the
  // screen unreachable by any means whatsoever.
  it('resolves the trip form rather than falling through to the wildcard', async () => {
    expect(await navigate('/trips')).toBe('/trips');
  });

  it('guards the profile route', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        { provide: AuthService, useValue: { isAuthenticated: () => false } },
      ],
    });
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/profile');

    expect(router.url).toBe('/login');
  });

  it('guards the stylist route', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        { provide: AuthService, useValue: { isAuthenticated: () => false } },
      ],
    });
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/stylist');

    expect(router.url).toBe('/login');
  });

  it('guards the trips route', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        { provide: AuthService, useValue: { isAuthenticated: () => false } },
      ],
    });
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/trips');

    expect(router.url).toBe('/login');
  });

  it('still guards the detail route', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        { provide: AuthService, useValue: { isAuthenticated: () => false } },
      ],
    });
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/wardrobe/item-1');

    expect(router.url).toBe('/login');
  });
});

import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  RouterStateSnapshot,
  UrlTree,
  provideRouter,
} from '@angular/router';
import { afterEach, describe, expect, it } from 'vitest';

import { AuthService } from './auth.service';
import { authGuard, guestGuard } from './auth.guard';

function run(guard: typeof authGuard, authenticated: boolean): boolean | UrlTree {
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: AuthService, useValue: { isAuthenticated: () => authenticated } },
    ],
  });

  return TestBed.runInInjectionContext(() =>
    guard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
  ) as boolean | UrlTree;
}

describe('authGuard', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('lets an authenticated user through', () => {
    expect(run(authGuard, true)).toBe(true);
  });

  it('redirects an anonymous user to /login', () => {
    const result = run(authGuard, false);

    expect(result).toBeInstanceOf(UrlTree);
    expect(String(result)).toBe('/login');
  });
});

describe('guestGuard', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('lets an anonymous user through', () => {
    expect(run(guestGuard, false)).toBe(true);
  });

  it('redirects an authenticated user to /wardrobe', () => {
    const result = run(guestGuard, true);

    expect(result).toBeInstanceOf(UrlTree);
    expect(String(result)).toBe('/wardrobe');
  });
});

import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  RouterStateSnapshot,
  UrlTree,
  provideRouter,
} from '@angular/router';
import { afterEach, describe, expect, it } from 'vitest';

import { AuthService } from './auth.service';
import { authGuard } from './auth.guard';

function runGuard(authenticated: boolean): boolean | UrlTree {
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: AuthService, useValue: { isAuthenticated: () => authenticated } },
    ],
  });

  return TestBed.runInInjectionContext(() =>
    authGuard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
  ) as boolean | UrlTree;
}

describe('authGuard', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('lets an authenticated user through', () => {
    expect(runGuard(true)).toBe(true);
  });

  it('redirects an anonymous user to /login', () => {
    const result = runGuard(false);

    expect(result).toBeInstanceOf(UrlTree);
    expect(String(result)).toBe('/login');
  });
});

import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { NavigationEnd, NavigationStart, Router, provideRouter } from '@angular/router';
import { filter, firstValueFrom, take } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import { jwtInterceptor } from './jwt.interceptor';

const TOKEN_KEY = 'bijoux.token';

let http: HttpClient;
let mock: HttpTestingController;

function configure(token: string | null): void {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(withInterceptors([jwtInterceptor])),
      provideHttpClientTesting(),
      provideRouter([]),
      { provide: AuthService, useValue: { token: () => token, rejectSession: () => undefined } },
    ],
  });
  http = TestBed.inject(HttpClient);
  mock = TestBed.inject(HttpTestingController);
}

describe('jwtInterceptor', () => {
  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  describe('with a token', () => {
    beforeEach(() => configure('a.b.c'));

    it('attaches the bearer header to an API request', () => {
      http.get(`${environment.apiUrl}/items`).subscribe();
      const request = mock.expectOne(`${environment.apiUrl}/items`);

      expect(request.request.headers.get('Authorization')).toBe('Bearer a.b.c');
      request.flush({});
    });

    it('attaches it to /auth/me, which is bearer-authenticated', () => {
      http.get(`${environment.apiUrl}/auth/me`).subscribe();
      const request = mock.expectOne(`${environment.apiUrl}/auth/me`);

      expect(request.request.headers.has('Authorization')).toBe(true);
      request.flush({});
    });

    it('skips /auth/login', () => {
      http.post(`${environment.apiUrl}/auth/login`, {}).subscribe();
      const request = mock.expectOne(`${environment.apiUrl}/auth/login`);

      expect(request.request.headers.has('Authorization')).toBe(false);
      request.flush({});
    });

    it('skips /auth/register', () => {
      http.post(`${environment.apiUrl}/auth/register`, {}).subscribe();
      const request = mock.expectOne(`${environment.apiUrl}/auth/register`);

      expect(request.request.headers.has('Authorization')).toBe(false);
      request.flush({});
    });

    it('skips a URL outside the API base, such as the i18n bundle', () => {
      http.get('/i18n/en.json').subscribe();
      const request = mock.expectOne('/i18n/en.json');

      expect(request.request.headers.has('Authorization')).toBe(false);
      request.flush({});
    });
  });

  describe('without a token', () => {
    beforeEach(() => configure(null));

    it('sends the API request unchanged', () => {
      http.get(`${environment.apiUrl}/items`).subscribe();
      const request = mock.expectOne(`${environment.apiUrl}/items`);

      expect(request.request.headers.has('Authorization')).toBe(false);
      request.flush({});
    });
  });

  describe('on a 401', () => {
    let auth: AuthService;
    let router: Router;

    beforeEach(() => {
      localStorage.clear();
      localStorage.setItem(TOKEN_KEY, 'expired.token');
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(withInterceptors([jwtInterceptor])),
          provideHttpClientTesting(),
          provideRouter([
            { path: 'wardrobe', children: [] },
            { path: 'login', children: [] },
          ]),
        ],
      });
      http = TestBed.inject(HttpClient);
      mock = TestBed.inject(HttpTestingController);
      auth = TestBed.inject(AuthService);
      router = TestBed.inject(Router);
    });

    function fail401(url: string): void {
      http.get(url).subscribe({ error: () => undefined });
      mock.expectOne(url).flush(null, { status: 401, statusText: 'Unauthorized' });
    }

    // The case the redirect exists for. A guard does not re-run on a route that
    // is already active, so without this navigate nothing moves the user at
    // all. Unreachable until 1.7 starts polling. DECISIONS.md 068.
    it('clears the session and redirects when the router has already navigated', async () => {
      await router.navigateByUrl('/wardrobe');
      expect(router.navigated).toBe(true);

      // The redirect is fired inside catchError and settles asynchronously, so
      // waiting on a microtask would read the pre-navigation URL.
      const redirected = firstValueFrom(
        router.events.pipe(
          filter((event) => event instanceof NavigationEnd),
          take(1),
        ),
      );
      fail401(`${environment.apiUrl}/items`);
      await redirected;

      expect(auth.token()).toBeNull();
      expect(auth.restoreNotice()).toBe('signed-out');
      expect(router.url).toBe('/login');
    });

    // Before the initial navigation, navigating would suppress it and discard
    // the URL the user actually asked for. authGuard lands them instead.
    it('clears the session but does not navigate during bootstrap', () => {
      expect(router.navigated).toBe(false);

      // Asserting router.url here would prove nothing: navigation is async, so
      // a started-but-unfinished redirect reads as '/' either way. Counting
      // NavigationStart is what actually says nothing was attempted.
      const started: NavigationStart[] = [];
      const sub = router.events.subscribe((event) => {
        if (event instanceof NavigationStart) {
          started.push(event);
        }
      });

      fail401(`${environment.apiUrl}/auth/me`);
      sub.unsubscribe();

      expect(auth.token()).toBeNull();
      expect(auth.restoreNotice()).toBe('signed-out');
      expect(started).toEqual([]);
    });

    // The one 401 in the application that must not sign anyone out. It is not
    // the skip list that guarantees this — the early return happens before
    // catchError is attached, so the request carries no response handler.
    it('leaves everything alone when it comes from /auth/login', () => {
      fail401(`${environment.apiUrl}/auth/login`);

      expect(auth.token()).toBe('expired.token');
      expect(localStorage.getItem(TOKEN_KEY)).toBe('expired.token');
      expect(auth.restoreNotice()).toBeNull();
      expect(router.url).toBe('/');
    });
  });
});

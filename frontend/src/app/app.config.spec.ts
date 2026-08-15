import {
  HttpBackend,
  HttpErrorResponse,
  HttpEvent,
  HttpRequest,
  HttpResponse,
} from '@angular/common/http';
import { ApplicationRef } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { Router } from '@angular/router';
import { Observable, delay, of, throwError } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../public/i18n/en.json';
import { environment } from '../environments/environment';
import { App } from './app';
import { appConfig } from './app.config';
import { AuthService } from './core/auth/auth.service';

const TOKEN_KEY = 'bijoux.token';

const USER = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'coral@example.com',
  display_name: 'Coral',
  height_cm: null,
  size_top: null,
  size_bottom: null,
  size_shoe: null,
  style_notes: null,
  home_city: null,
  home_lat: null,
  home_lon: null,
  created_at: '2026-08-11T09:00:00Z',
};

type Reply = HttpResponse<unknown> | HttpErrorResponse;

// HttpTestingController cannot be reached before bootstrap resolves, and the
// app initializers run inside it — so the backend is replaced outright rather
// than driven from outside.
//
// delay(0) is load-bearing, not decoration. A synchronous reply resolves
// restore() inside the same microtask chain as bootstrap, so every assertion
// below passes whether or not the initializer is awaited — verified by
// dropping the return from app.config.ts and watching all 69 tests stay green.
// Pushing the reply onto a macrotask is what makes these tests evidence that
// bootstrap waits. DECISIONS.md 067.
function backendReplying(meReply: Reply) {
  return {
    provide: HttpBackend,
    useValue: {
      handle(request: HttpRequest<unknown>): Observable<HttpEvent<unknown>> {
        const reply = request.url.endsWith('/i18n/en.json')
          ? new HttpResponse({ status: 200, body: en })
          : meReply;
        return (reply instanceof HttpErrorResponse ? throwError(() => reply) : of(reply)).pipe(
          delay(0),
        ) as Observable<HttpEvent<unknown>>;
      },
    },
  };
}

let app: ApplicationRef | null = null;

async function bootAt(url: string, meReply: Reply): Promise<ApplicationRef> {
  window.history.replaceState({}, '', url);
  document.body.innerHTML = '<app-root></app-root>';
  app = await bootstrapApplication(App, {
    providers: [...appConfig.providers, backendReplying(meReply)],
  });
  await app.whenStable();
  return app;
}

describe('bootstrap with a stored token', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(TOKEN_KEY, 'stored.token');
  });

  afterEach(() => {
    app?.destroy();
    app = null;
    localStorage.clear();
  });

  it('admits the route and populates the user when /auth/me answers', async () => {
    const ref = await bootAt('/wardrobe', new HttpResponse({ status: 200, body: USER }));
    const auth = ref.injector.get(AuthService);

    expect(auth.currentUser()?.email).toBe('coral@example.com');
    expect(auth.isAuthenticated()).toBe(true);
    expect(auth.restoreNotice()).toBeNull();
    expect(ref.injector.get(Router).url).toBe('/wardrobe');
  });

  it('clears the session and lands on /login when the token is rejected', async () => {
    const ref = await bootAt(
      '/wardrobe',
      new HttpErrorResponse({ status: 401, url: `${environment.apiUrl}/auth/me` }),
    );
    const auth = ref.injector.get(AuthService);

    expect(auth.token()).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(auth.restoreNotice()).toBe('signed-out');
    expect(ref.injector.get(Router).url).toBe('/login');
  });

  // A network failure is not evidence the token is bad, so it is kept — and the
  // user is told rather than dropped on a bare form. DECISIONS.md 067.
  it('keeps the token and reports unreachable when nothing answers', async () => {
    const ref = await bootAt(
      '/wardrobe',
      new HttpErrorResponse({ status: 0, url: `${environment.apiUrl}/auth/me` }),
    );
    const auth = ref.injector.get(AuthService);

    expect(auth.token()).toBe('stored.token');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('stored.token');
    expect(auth.isAuthenticated()).toBe(false);
    expect(auth.restoreNotice()).toBe('unreachable');
    expect(ref.injector.get(Router).url).toBe('/login');
  });

  // N6: the requested URL survives, because the interceptor does not navigate
  // before the initial navigation has run. DECISIONS.md 068.
  it('preserves a deep link to a public route when the token is rejected', async () => {
    const ref = await bootAt(
      '/register',
      new HttpErrorResponse({ status: 401, url: `${environment.apiUrl}/auth/me` }),
    );

    expect(ref.injector.get(AuthService).token()).toBeNull();
    expect(ref.injector.get(Router).url).toBe('/register');
  });
});

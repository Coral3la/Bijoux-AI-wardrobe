import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { environment } from '../../../environments/environment';
import { TokenResponse } from '../../shared/models/user.model';
import { AuthService } from './auth.service';

const TOKEN_KEY = 'bijoux.token';

const response: TokenResponse = {
  access_token: 'a.b.c',
  token_type: 'bearer',
  user: {
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
  },
};

let service: AuthService;
let mock: HttpTestingController;

// Constructing the service is what reads localStorage, so a test that cares
// about the stored token has to seed it before calling this.
function construct(): void {
  TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  service = TestBed.inject(AuthService);
  mock = TestBed.inject(HttpTestingController);
}

describe('AuthService', () => {
  beforeEach(() => localStorage.clear());

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  it('starts unauthenticated when localStorage is empty', () => {
    construct();

    expect(service.token()).toBeNull();
    expect(service.isAuthenticated()).toBe(false);
  });

  it('hydrates the token from localStorage on construction', () => {
    localStorage.setItem(TOKEN_KEY, 'stored.token');
    construct();

    expect(service.token()).toBe('stored.token');
  });

  // The other half of the split above. A stored token is a credential we hold,
  // not a session the server has confirmed. DECISIONS.md 067.
  it('is not authenticated on a stored token alone', () => {
    localStorage.setItem(TOKEN_KEY, 'stored.token');
    construct();

    expect(service.isAuthenticated()).toBe(false);
  });

  it('does not hydrate the user, only the token', () => {
    localStorage.setItem(TOKEN_KEY, 'stored.token');
    construct();

    expect(service.currentUser()).toBeNull();
  });

  it('stores the token and the user on login', () => {
    construct();
    service.login('coral@example.com', 'hunter2hunter2').subscribe();
    mock.expectOne(`${environment.apiUrl}/auth/login`).flush(response);

    expect(service.token()).toBe('a.b.c');
    expect(service.currentUser()?.email).toBe('coral@example.com');
    expect(service.isAuthenticated()).toBe(true);
    expect(localStorage.getItem(TOKEN_KEY)).toBe('a.b.c');
  });

  it('clears the token, the user and localStorage on logout', () => {
    localStorage.setItem(TOKEN_KEY, 'stored.token');
    construct();
    service.logout();

    expect(service.token()).toBeNull();
    expect(service.currentUser()).toBeNull();
    expect(service.isAuthenticated()).toBe(false);
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  describe('restore', () => {
    it('makes no request and clears the notice when there is no token', async () => {
      construct();
      await service.restore();

      expect(service.currentUser()).toBeNull();
      expect(service.restoreNotice()).toBeNull();
    });

    it('populates the user and clears the notice on 200', async () => {
      localStorage.setItem(TOKEN_KEY, 'stored.token');
      construct();

      const done = service.restore();
      mock.expectOne(`${environment.apiUrl}/auth/me`).flush(response.user);
      await done;

      expect(service.currentUser()?.email).toBe('coral@example.com');
      expect(service.isAuthenticated()).toBe(true);
      expect(service.restoreNotice()).toBeNull();
    });

    it('keeps the token and reports unreachable when the request fails', async () => {
      localStorage.setItem(TOKEN_KEY, 'stored.token');
      construct();

      const done = service.restore();
      mock.expectOne(`${environment.apiUrl}/auth/me`).error(new ProgressEvent('error'));
      await done;

      expect(service.token()).toBe('stored.token');
      expect(service.isAuthenticated()).toBe(false);
      expect(service.restoreNotice()).toBe('unreachable');
    });

    // A 401 belongs to the interceptor. If restore() also wrote here, the
    // notice would depend on which of the two ran last. DECISIONS.md 067.
    it('leaves the notice alone on a 401', async () => {
      localStorage.setItem(TOKEN_KEY, 'stored.token');
      construct();

      const done = service.restore();
      mock
        .expectOne(`${environment.apiUrl}/auth/me`)
        .flush(null, { status: 401, statusText: 'Unauthorized' });
      await done;

      expect(service.restoreNotice()).toBeNull();
    });

    it('ignores a second call while one is in flight', async () => {
      localStorage.setItem(TOKEN_KEY, 'stored.token');
      construct();

      const first = service.restore();
      const second = service.restore();
      mock.expectOne(`${environment.apiUrl}/auth/me`).flush(response.user);
      await Promise.all([first, second]);

      expect(service.restoring()).toBe(false);
    });
  });

  describe('rejectSession', () => {
    it('clears the session and records that the server said no', () => {
      localStorage.setItem(TOKEN_KEY, 'stored.token');
      construct();
      service.rejectSession();

      expect(service.token()).toBeNull();
      expect(service.currentUser()).toBeNull();
      expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
      expect(service.restoreNotice()).toBe('signed-out');
    });

    // logout() must not touch the notice, or the 401 path would depend on
    // which of the two ran first. DECISIONS.md 067.
    it('is not undone by a later logout', () => {
      construct();
      service.rejectSession();
      service.logout();

      expect(service.restoreNotice()).toBe('signed-out');
    });
  });
});

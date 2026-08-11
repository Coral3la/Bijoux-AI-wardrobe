import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import { jwtInterceptor } from './jwt.interceptor';

let http: HttpClient;
let mock: HttpTestingController;

function configure(token: string | null): void {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(withInterceptors([jwtInterceptor])),
      provideHttpClientTesting(),
      { provide: AuthService, useValue: { token: () => token } },
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
});

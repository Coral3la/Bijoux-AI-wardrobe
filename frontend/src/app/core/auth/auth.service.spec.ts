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
    expect(service.isAuthenticated()).toBe(true);
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
    expect(localStorage.getItem(TOKEN_KEY)).toBe('a.b.c');
  });

  it('sends display_name on register even when it is null', () => {
    construct();
    service.register('coral@example.com', 'hunter2hunter2', null).subscribe();
    const request = mock.expectOne(`${environment.apiUrl}/auth/register`);

    expect(request.request.body).toEqual({
      email: 'coral@example.com',
      password: 'hunter2hunter2',
      display_name: null,
    });
    request.flush(response);
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
});

import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { environment } from '../../../environments/environment';
import { AuthService } from '../../core/auth/auth.service';
import { jwtInterceptor } from '../../core/auth/jwt.interceptor';
import { I18nService } from '../../core/i18n/i18n.service';
import { RegisterPage } from './register.page';

const TOKEN_RESPONSE = {
  access_token: 'a.b.c',
  token_type: 'bearer' as const,
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

let fixture: ComponentFixture<RegisterPage>;
let mock: HttpTestingController;
let auth: AuthService;
let router: Router;

function text(): string {
  return (fixture.nativeElement as HTMLElement).textContent ?? '';
}

function fill(selector: string, value: string): void {
  const input = (fixture.nativeElement as HTMLElement).querySelector(selector) as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new Event('input'));
}

function fillValid(): void {
  fill('#displayName', 'Coral');
  fill('#email', 'coral@example.com');
  fill('#password', 'hunter2hunter2');
}

function submit(): void {
  (fixture.nativeElement as HTMLElement).querySelector('form')!.dispatchEvent(new Event('submit'));
}

describe('RegisterPage', () => {
  beforeEach(async () => {
    localStorage.clear();
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
    mock = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
    router = TestBed.inject(Router);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;

    fixture = TestBed.createComponent(RegisterPage);
    await fixture.whenStable();
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  it('renders its labels from the string file', () => {
    expect(text()).toContain('Begin a wardrobe.');
    expect(text()).toContain('Your name');
    expect(text()).toContain('Create account');
  });

  it('requires every field and sends nothing on an empty submit', async () => {
    submit();
    await fixture.whenStable();

    expect(text()).toContain('This field is required.');
    mock.expectNone(() => true);
  });

  // Validators.required accepts "   " and so does the API, so a blank name
  // would otherwise reach the column. DECISIONS.md 070.
  it('treats a whitespace-only display name as missing', async () => {
    fill('#displayName', '   ');
    fill('#email', 'coral@example.com');
    fill('#password', 'hunter2hunter2');
    submit();
    await fixture.whenStable();

    expect(text()).toContain('This field is required.');
    mock.expectNone(() => true);
  });

  it('names the character minimum on a short password', async () => {
    fill('#displayName', 'Coral');
    fill('#email', 'coral@example.com');
    fill('#password', 'short');
    submit();
    await fixture.whenStable();

    expect(text()).toContain('Use at least 8 characters.');
    mock.expectNone(() => true);
  });

  // The limit is bcrypt's and it is counted in bytes, so the message names
  // bytes rather than characters. DECISIONS.md 036.
  it('names bytes when a multi-byte password exceeds the bcrypt limit', async () => {
    fill('#displayName', 'Coral');
    fill('#email', 'coral@example.com');
    fill('#password', 'é'.repeat(37));
    submit();
    await fixture.whenStable();

    expect(text()).toContain('Use at most 72 bytes');
    mock.expectNone(() => true);
  });

  it('accepts a 72-byte password made of multi-byte characters', async () => {
    fill('#displayName', 'Coral');
    fill('#email', 'coral@example.com');
    fill('#password', 'é'.repeat(36));
    submit();
    await fixture.whenStable();

    mock.expectOne(`${environment.apiUrl}/auth/register`).flush(TOKEN_RESPONSE);
  });

  it('posts the trimmed display name with the other two fields', async () => {
    fill('#displayName', '  Coral  ');
    fill('#email', 'coral@example.com');
    fill('#password', 'hunter2hunter2');
    submit();
    await fixture.whenStable();

    const request = mock.expectOne(`${environment.apiUrl}/auth/register`);
    expect(request.request.body).toEqual({
      email: 'coral@example.com',
      password: 'hunter2hunter2',
      display_name: 'Coral',
    });
    request.flush(TOKEN_RESPONSE);
  });

  // expectOne is the assertion, not setup: it throws when more than one
  // request matches, which is the whole test. There is nothing else to add.
  it('sends one request when submitted twice in a row', async () => {
    fillValid();
    submit();
    submit();
    await fixture.whenStable();

    mock.expectOne(`${environment.apiUrl}/auth/register`).flush(TOKEN_RESPONSE);
  });

  it('lands on /wardrobe once registered', async () => {
    fillValid();
    submit();
    await fixture.whenStable();
    mock.expectOne(`${environment.apiUrl}/auth/register`).flush(TOKEN_RESPONSE);
    await fixture.whenStable();

    expect(auth.isAuthenticated()).toBe(true);
    expect(router.url).toBe('/wardrobe');
  });

  // Confirmed against the route rather than the spec: auth.py raises
  // ApiError(409, "email_exists") on the uq_users_email violation.
  it('explains a taken email', async () => {
    fillValid();
    submit();
    await fixture.whenStable();
    mock
      .expectOne(`${environment.apiUrl}/auth/register`)
      .flush({ detail: 'x', code: 'email_exists' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();

    expect(text()).toContain('That email is already registered.');
  });

  // The neighbouring branch in auth.py re-raises any other IntegrityError,
  // which reaches the client as a bare 500 with no code.
  it('falls back to the generic message on any other failure', async () => {
    fillValid();
    submit();
    await fixture.whenStable();
    mock
      .expectOne(`${environment.apiUrl}/auth/register`)
      .flush(null, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(text()).toContain('Something went wrong. Please try again.');
  });
});

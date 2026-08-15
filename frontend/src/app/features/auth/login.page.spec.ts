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
import { LoginPage } from './login.page';

const TOKEN_KEY = 'bijoux.token';

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

let fixture: ComponentFixture<LoginPage>;
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

function submit(): void {
  (fixture.nativeElement as HTMLElement).querySelector('form')!.dispatchEvent(new Event('submit'));
}

describe('LoginPage', () => {
  beforeEach(async () => {
    localStorage.clear();
    // Seeded before AuthService is constructed, because the token signal is
    // read once at construction. The notice tests need it; for the rest a
    // stale unverified token changes nothing, which is itself the point.
    localStorage.setItem(TOKEN_KEY, 'stored.token');
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([jwtInterceptor])),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'wardrobe', children: [] },
          { path: 'register', children: [] },
        ]),
      ],
    });
    mock = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
    router = TestBed.inject(Router);

    // The real string file, so a key missing from it fails here rather than
    // rendering as itself on screen.
    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;

    fixture = TestBed.createComponent(LoginPage);
    await fixture.whenStable();
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  it('renders its labels from the string file', () => {
    expect(text()).toContain('Sign in');
    expect(text()).toContain('Email');
    expect(text()).toContain('Password');
  });

  it('shows validation messages and sends nothing on an empty submit', async () => {
    submit();
    await fixture.whenStable();

    expect(text()).toContain('This field is required.');
    mock.expectNone(() => true);
  });

  it('rejects a malformed email without sending it', async () => {
    fill('#email', 'not-an-email');
    fill('#password', 'hunter2hunter2');
    submit();
    await fixture.whenStable();

    expect(text()).toContain('Enter a valid email address.');
    mock.expectNone(() => true);
  });

  it('posts exactly the two fields the API expects', async () => {
    fill('#email', 'coral@example.com');
    fill('#password', 'hunter2hunter2');
    submit();
    await fixture.whenStable();

    const request = mock.expectOne(`${environment.apiUrl}/auth/login`);
    expect(request.request.body).toEqual({
      email: 'coral@example.com',
      password: 'hunter2hunter2',
    });
    request.flush(TOKEN_RESPONSE);
  });

  // Two fast submits used to produce two POSTs. expectOne is the assertion:
  // it throws when more than one request matches.
  it('sends one request when submitted twice in a row', async () => {
    fill('#email', 'coral@example.com');
    fill('#password', 'hunter2hunter2');
    submit();
    submit();
    await fixture.whenStable();

    mock.expectOne(`${environment.apiUrl}/auth/login`).flush(TOKEN_RESPONSE);
  });

  it('lands on /wardrobe once signed in', async () => {
    fill('#email', 'coral@example.com');
    fill('#password', 'hunter2hunter2');
    submit();
    await fixture.whenStable();
    mock.expectOne(`${environment.apiUrl}/auth/login`).flush(TOKEN_RESPONSE);
    await fixture.whenStable();

    expect(auth.isAuthenticated()).toBe(true);
    expect(router.url).toBe('/wardrobe');
  });

  it('explains a rejected password without clearing anything', async () => {
    fill('#email', 'coral@example.com');
    fill('#password', 'wrong-password');
    submit();
    await fixture.whenStable();
    mock
      .expectOne(`${environment.apiUrl}/auth/login`)
      .flush({ detail: 'x', code: 'invalid_credentials' }, { status: 401, statusText: 'x' });
    await fixture.whenStable();

    expect(text()).toContain('Incorrect email or password.');
    expect(auth.restoreNotice()).toBeNull();
  });

  it('falls back to the generic message on any other failure', async () => {
    fill('#email', 'coral@example.com');
    fill('#password', 'hunter2hunter2');
    submit();
    await fixture.whenStable();
    mock
      .expectOne(`${environment.apiUrl}/auth/login`)
      .flush(null, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(text()).toContain('Something went wrong. Please try again.');
  });

  it('re-enables submitting after a failure', async () => {
    fill('#email', 'coral@example.com');
    fill('#password', 'wrong-password');
    submit();
    await fixture.whenStable();
    mock
      .expectOne(`${environment.apiUrl}/auth/login`)
      .flush(null, { status: 401, statusText: 'x' });
    await fixture.whenStable();

    submit();
    await fixture.whenStable();
    mock.expectOne(`${environment.apiUrl}/auth/login`).flush(TOKEN_RESPONSE);
  });

  describe('the bootstrap notice', () => {
    it('explains a rejected session', async () => {
      auth.rejectSession();
      await fixture.whenStable();

      expect(text()).toContain('Please sign in again.');
      expect(text()).not.toContain('Try again');
    });

    it('offers a retry when the server could not be reached', async () => {
      const done = auth.restore();
      mock.expectOne(`${environment.apiUrl}/auth/me`).error(new ProgressEvent('error'));
      await done;
      await fixture.whenStable();

      expect(text()).toContain("We couldn't reach Bijoux. You may still be signed in.");
      expect(text()).toContain('Try again');
    });

    // No guard re-runs on an already-active route, so the page has to move the
    // user itself. DECISIONS.md 068.
    it('navigates to /wardrobe when the retry succeeds', async () => {
      const failed = auth.restore();
      mock.expectOne(`${environment.apiUrl}/auth/me`).error(new ProgressEvent('error'));
      await failed;
      await fixture.whenStable();

      const button = [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].find(
        (element) => element.textContent?.includes('Try again'),
      )!;
      button.click();
      mock.expectOne(`${environment.apiUrl}/auth/me`).flush(TOKEN_RESPONSE.user);
      await fixture.whenStable();

      expect(auth.isAuthenticated()).toBe(true);
      expect(router.url).toBe('/wardrobe');
    });
  });
});

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../public/i18n/en.json';
import { App } from './app';
import { AuthService } from './core/auth/auth.service';
import { I18nService } from './core/i18n/i18n.service';

let fixture: ComponentFixture<App>;
let mock: HttpTestingController;
let authenticated: boolean;

function element(): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function nav(): HTMLElement | null {
  return element().querySelector('nav');
}

async function render(): Promise<void> {
  fixture = TestBed.createComponent(App);
  await fixture.whenStable();
}

describe('App', () => {
  beforeEach(async () => {
    authenticated = true;
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'wardrobe', children: [] },
          { path: 'login', children: [] },
        ]),
        {
          provide: AuthService,
          useValue: { isAuthenticated: () => authenticated, logout: () => undefined },
        },
      ],
    });
    mock = TestBed.inject(HttpTestingController);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    try {
      mock.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });

  it('renders the navigation for a signed-in user', async () => {
    await render();

    expect(nav()).not.toBeNull();
    expect(nav()?.getAttribute('aria-label')).toBe(en['nav.region']);
  });

  // Decision 7. The gate is the user signal rather than the route, so /login,
  // /register and a restore still in flight all get no bar without any of them
  // being named here — and a screen this component has never heard of cannot
  // acquire one by being added to app.routes.ts.
  it('renders no navigation when nobody is signed in', async () => {
    authenticated = false;
    await render();

    expect(nav()).toBeNull();
  });

  // The bar is a sibling of the outlet and never a wrapper around it: a signed
  // out shell still renders its screen.
  it('renders the outlet with nobody signed in', async () => {
    authenticated = false;
    await render();

    expect(element().querySelector('router-outlet')).not.toBeNull();
  });
});

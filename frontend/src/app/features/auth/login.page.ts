import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import {
  AbstractControl,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';

// Published rather than secret, and the same two strings live in
// `backend/scripts/seed_demo.py`, which is what creates the account. Nothing
// compares them: drift here is a demo button that answers 401 against a
// correctly seeded database, and only signing in catches it. `DECISIONS.md`
// 136 and 137; `07-DEPLOYMENT.md` documents the credential as published so
// that finding it in this file is not read as a leak.
const DEMO_EMAIL = 'demo@bijoux.app';
const DEMO_PASSWORD = 'bijoux-demo-wardrobe';

// The five class strings the auth pair is drawn with, declared here and again
// in `register.page.ts`. The two screens are twins by design, so neither owns
// the treatment and importing it from the other would make one of them the
// definition of the other. DECISIONS.md 223.
const LABEL = 'font-mono text-[10px] font-medium tracking-[0.24em] text-ink-soft uppercase';

// A hairline under the field and nothing else — no box, no fill. The colour is
// `ink-soft` rather than `line-strong`, which the palette table names as an
// input's border: a single rule has to carry on its own the contrast a boxed
// field gets from four sides, and at `line-strong` it reads as a smudge on
// cream. `ink` has drawn borders since the first Atelier chip; this is the
// first call for one of the softer ink tokens. DECISIONS.md 223.
const FIELD =
  'min-h-11 border-b border-ink-soft bg-transparent py-2 font-sans text-[15px] focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

const PILL =
  'inline-flex min-h-11 items-center justify-center gap-x-2 rounded-full border border-ink bg-ink px-6 text-[11px] font-medium tracking-[0.22em] text-canvas uppercase disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

const GHOST_PILL =
  'inline-flex min-h-11 items-center justify-center rounded-full border border-line-strong px-6 text-[11px] font-medium tracking-[0.22em] uppercase disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

// Upright inside an italic line, and the one accent colour on the screen.
const SWAP_LINK =
  'ms-2 border-b border-accent pb-0.5 font-sans text-[11px] font-medium tracking-[0.22em] text-accent uppercase not-italic focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

@Component({
  selector: 'app-login-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <!-- No navigation bar reaches this screen — app.html gates it on a
         confirmed user — so the wordmark is the only chrome, and the page is
         built as a full-height canvas with the whole composition centred in it
         rather than as a column inside a shell. DECISIONS.md 223. -->
    <main class="flex min-h-dvh flex-col">
      <p
        class="px-6 pt-10 font-display text-[22px] font-light tracking-[0.28em] uppercase md:px-12"
      >
        {{ i18n.t('auth.wordmark') }}
      </p>

      <div class="flex flex-1 flex-col items-center justify-center gap-10 px-6 py-12">
        <header class="flex max-w-[440px] flex-col items-center gap-2 text-center">
          <h1
            class="font-display text-[36px] leading-[1.05] font-light tracking-[-0.015em] text-balance md:text-[48px]"
          >
            {{ i18n.t('login.title') }}
          </h1>
          <p class="font-prose text-[17px] text-ink-muted italic">{{ i18n.t('auth.tagline') }}</p>
        </header>

        <div class="flex w-full max-w-[400px] flex-col gap-6">
          <!-- The panel carries no colour of its own, and that is load-bearing:
               the paragraph inside it does. One of these notices is danger and the
               other deliberately is not (DECISIONS.md 057), and a tinted wrapper
               would blur an asymmetry the spec asserts. -->
          @if (auth.restoreNotice() === 'signed-out') {
            <div class="rounded-sm bg-surface-elevated p-4 text-sm">
              <p class="font-medium text-danger">{{ i18n.t('login.notice.signedOut') }}</p>
            </div>
          }
          @if (auth.restoreNotice() === 'unreachable') {
            <div class="flex flex-col items-start gap-3 rounded-sm bg-surface-elevated p-4 text-sm">
              <p class="font-medium">{{ i18n.t('login.notice.unreachable') }}</p>
              <button type="button" (click)="retry()" [disabled]="auth.restoring()" [class]="ghost">
                {{ i18n.t('login.notice.retry') }}
              </button>
            </div>
          }

          <!-- novalidate, and no native 'required' on any field: both would hand
               submission back to the browser's constraint validation, which blocks
               it and shows an untranslatable bubble before our messages render.
               The unit suite cannot catch either being added back — its submits
               bypass constraint validation — so task 5.3 asserts this in a browser.
               'autocomplete="username"' on the email field is also deliberate:
               password managers pair that token with current-password to offer
               save and fill. DECISIONS.md 070. -->
          <form [formGroup]="form" (ngSubmit)="submit()" novalidate class="flex flex-col gap-6">
            @let emailError = messageFor(form.controls.email);
            <div class="flex flex-col gap-1.5">
              <label for="email" [class]="label">{{ i18n.t('login.email.label') }}</label>
              <input
                id="email"
                type="email"
                formControlName="email"
                autocomplete="username"
                autocapitalize="none"
                spellcheck="false"
                aria-required="true"
                [attr.aria-invalid]="emailError ? 'true' : null"
                [attr.aria-describedby]="emailError ? 'email-error' : null"
                [class]="field"
              />
              @if (emailError) {
                <p id="email-error" class="text-sm font-medium text-danger">{{ emailError }}</p>
              }
            </div>

            @let passwordError = messageFor(form.controls.password);
            <div class="flex flex-col gap-1.5">
              <label for="password" [class]="label">{{ i18n.t('login.password.label') }}</label>
              <input
                id="password"
                type="password"
                formControlName="password"
                autocomplete="current-password"
                aria-required="true"
                [attr.aria-invalid]="passwordError ? 'true' : null"
                [attr.aria-describedby]="passwordError ? 'password-error' : null"
                [class]="field"
              />
              @if (passwordError) {
                <p id="password-error" class="text-sm font-medium text-danger">
                  {{ passwordError }}
                </p>
              }
            </div>

            @if (serverError(); as message) {
              <p class="text-sm font-medium text-danger">{{ message }}</p>
            }

            <button type="submit" [disabled]="submitting()" [class]="pill">
              {{ submitting() ? i18n.t('login.submitting') : i18n.t('login.submit') }}
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
                class="h-3 w-3"
                aria-hidden="true"
              >
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </button>

            <!-- Two keys rather than one sentence with a link inside it: the
                 question is ours and the word after it is a control's label, so
                 213's rule about splitting a sentence does not reach them. -->
            <p class="text-center font-prose text-[15px] text-ink-muted italic">
              {{ i18n.t('auth.swap.newHere') }}
              <a routerLink="/register" [class]="swap">{{ i18n.t('login.toRegister') }}</a>
            </p>
          </form>

          <!-- Outside the <form> deliberately: inside it, a <button> defaults to
               type=submit, and a demo button that also submits an empty form is one
               misreading away. This is O-12's affordance, and it is a button rather
               than the prefilled credentials that audit item specified — a value in
               an input carrying autocomplete="current-password" invites a browser
               to save the demo account over somebody's stored login. DECISIONS.md 136. -->
          <div class="flex flex-col items-center gap-2 border-t border-line pt-6">
            <button type="button" (click)="viewDemo()" [disabled]="submitting()" [class]="ghost">
              {{ i18n.t('login.demo.action') }}
            </button>
            <p class="text-center font-prose text-sm text-ink-muted italic">
              {{ i18n.t('login.demo.hint') }}
            </p>
          </div>
        </div>
      </div>
    </main>
  `,
})
export class LoginPage {
  protected readonly i18n = inject(I18nService);
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly label = LABEL;
  protected readonly field = FIELD;
  protected readonly pill = PILL;
  protected readonly ghost = GHOST_PILL;
  protected readonly swap = SWAP_LINK;

  protected readonly submitting = signal(false);
  protected readonly serverError = signal<string | null>(null);

  // No length rules here: LoginRequest has none, and telling someone their
  // existing password is too short at sign-in explains nothing.
  protected readonly form = this.fb.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]],
  });

  protected submit(): void {
    if (this.submitting()) {
      return;
    }
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const { email, password } = this.form.getRawValue();
    this.signIn(email, password);
  }

  // The demo account, on the same call and the same token as any other sign-in.
  // 04-API-SPEC.md lists no endpoint for switching accounts and forbids adding
  // one, which is why this is a login rather than a mechanism of its own.
  protected viewDemo(): void {
    this.signIn(DEMO_EMAIL, DEMO_PASSWORD);
  }

  private signIn(email: string, password: string): void {
    this.submitting.set(true);
    this.serverError.set(null);

    this.auth
      .login(email, password)
      .pipe(finalize(() => this.submitting.set(false)))
      .subscribe({
        next: () => void this.router.navigateByUrl('/wardrobe'),
        error: (error: unknown) => this.serverError.set(this.serverMessageFor(error)),
      });
  }

  // No guard re-runs on a route that is already active, so this page has to
  // move the user itself once the session is back. DECISIONS.md 068.
  protected async retry(): Promise<void> {
    await this.auth.restore();
    if (this.auth.isAuthenticated()) {
      await this.router.navigateByUrl('/wardrobe');
    }
  }

  protected messageFor(control: AbstractControl): string | null {
    if (!control.touched || control.valid) {
      return null;
    }
    return this.i18n.t(control.hasError('required') ? 'validation.required' : 'validation.email');
  }

  private serverMessageFor(error: unknown): string {
    const invalid = error instanceof HttpErrorResponse && error.status === 401;
    return this.i18n.t(invalid ? 'login.error.invalidCredentials' : 'error.unexpected');
  }
}

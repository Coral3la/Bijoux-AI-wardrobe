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
import { Button } from '../../shared/ui/button';

// Published rather than secret, and the same two strings live in
// `backend/scripts/seed_demo.py`, which is what creates the account. Nothing
// compares them: drift here is a demo button that answers 401 against a
// correctly seeded database, and only signing in catches it. `DECISIONS.md`
// 136 and 137; `07-DEPLOYMENT.md` documents the credential as published so
// that finding it in this file is not read as a leak.
const DEMO_EMAIL = 'demo@bijoux.app';
const DEMO_PASSWORD = 'bijoux-demo-wardrobe';

@Component({
  selector: 'app-login-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, ReactiveFormsModule, RouterLink],
  template: `
    <main class="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-6 px-6 py-16">
      <h1 class="font-display text-4xl leading-tight tracking-tight">
        {{ i18n.t('login.title') }}
      </h1>

      <!-- The panel carries no colour of its own, and that is load-bearing:
           the paragraph inside it does. One of these notices is danger and the
           other deliberately is not (DECISIONS.md 057), and a tinted wrapper
           would blur an asymmetry the spec asserts. -->
      @if (auth.restoreNotice() === 'signed-out') {
        <div class="rounded-md bg-surface-elevated p-3 text-sm">
          <p class="font-medium text-danger">{{ i18n.t('login.notice.signedOut') }}</p>
        </div>
      }
      @if (auth.restoreNotice() === 'unreachable') {
        <div class="flex flex-col items-start gap-2 rounded-md bg-surface-elevated p-3 text-sm">
          <p class="font-medium">{{ i18n.t('login.notice.unreachable') }}</p>
          <button
            appButton
            variant="ghost"
            type="button"
            (click)="retry()"
            [disabled]="auth.restoring()"
            class="disabled:opacity-50"
          >
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
      <form [formGroup]="form" (ngSubmit)="submit()" novalidate class="flex flex-col gap-4">
        @let emailError = messageFor(form.controls.email);
        <div class="flex flex-col gap-1">
          <label for="email" class="text-sm">{{ i18n.t('login.email.label') }}</label>
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
            class="min-h-11 rounded-md border border-line-strong bg-surface px-3 text-sm focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          />
          @if (emailError) {
            <p id="email-error" class="text-sm font-medium text-danger">{{ emailError }}</p>
          }
        </div>

        @let passwordError = messageFor(form.controls.password);
        <div class="flex flex-col gap-1">
          <label for="password" class="text-sm">{{ i18n.t('login.password.label') }}</label>
          <input
            id="password"
            type="password"
            formControlName="password"
            autocomplete="current-password"
            aria-required="true"
            [attr.aria-invalid]="passwordError ? 'true' : null"
            [attr.aria-describedby]="passwordError ? 'password-error' : null"
            class="min-h-11 rounded-md border border-line-strong bg-surface px-3 text-sm focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          />
          @if (passwordError) {
            <p id="password-error" class="text-sm font-medium text-danger">{{ passwordError }}</p>
          }
        </div>

        @if (serverError(); as message) {
          <p class="text-sm font-medium text-danger">{{ message }}</p>
        }

        <button appButton type="submit" [disabled]="submitting()" class="disabled:opacity-50">
          {{ submitting() ? i18n.t('login.submitting') : i18n.t('login.submit') }}
        </button>
      </form>

      <!-- Outside the <form> deliberately: inside it, a <button> defaults to
           type=submit, and a demo button that also submits an empty form is one
           misreading away. This is O-12's affordance, and it is a button rather
           than the prefilled credentials that audit item specified — a value in
           an input carrying autocomplete="current-password" invites a browser
           to save the demo account over somebody's stored login. DECISIONS.md 136. -->
      <div class="flex flex-col gap-1">
        <button
          appButton
          variant="secondary"
          type="button"
          (click)="viewDemo()"
          [disabled]="submitting()"
          class="disabled:opacity-50"
        >
          {{ i18n.t('login.demo.action') }}
        </button>
        <p class="text-sm text-ink-muted">{{ i18n.t('login.demo.hint') }}</p>
      </div>

      <a
        routerLink="/register"
        class="text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('login.toRegister') }}
      </a>
    </main>
  `,
})
export class LoginPage {
  protected readonly i18n = inject(I18nService);
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(NonNullableFormBuilder);

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

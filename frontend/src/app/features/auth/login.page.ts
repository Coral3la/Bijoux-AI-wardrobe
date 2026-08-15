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

@Component({
  selector: 'app-login-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <main class="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-6 p-6">
      <h1 class="font-display text-3xl">{{ i18n.t('login.title') }}</h1>

      @if (auth.restoreNotice() === 'signed-out') {
        <p class="text-sm font-medium text-danger">{{ i18n.t('login.notice.signedOut') }}</p>
      }
      @if (auth.restoreNotice() === 'unreachable') {
        <div class="flex flex-col items-start gap-2">
          <p class="text-sm font-medium">{{ i18n.t('login.notice.unreachable') }}</p>
          <button
            type="button"
            (click)="retry()"
            [disabled]="auth.restoring()"
            class="min-h-11 rounded-md px-3 text-sm underline disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
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
            class="min-h-11 rounded-md border border-ink/15 bg-surface px-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
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
            class="min-h-11 rounded-md border border-ink/15 bg-surface px-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          />
          @if (passwordError) {
            <p id="password-error" class="text-sm font-medium text-danger">{{ passwordError }}</p>
          }
        </div>

        @if (serverError(); as message) {
          <p class="text-sm font-medium text-danger">{{ message }}</p>
        }

        <button
          type="submit"
          [disabled]="submitting()"
          class="min-h-11 rounded-md bg-accent px-4 text-surface disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {{ submitting() ? i18n.t('login.submitting') : i18n.t('login.submit') }}
        </button>
      </form>

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

    this.submitting.set(true);
    this.serverError.set(null);
    const { email, password } = this.form.getRawValue();

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

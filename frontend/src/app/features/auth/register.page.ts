import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import {
  AbstractControl,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { Button } from '../../shared/ui/button';

// Hand-copied from the backend: MIN_PASSWORD_LENGTH in app/schemas/auth.py and
// MAX_PASSWORD_BYTES in app/core/security.py. Nothing compares the two, and the
// drift is invisible until a user is rejected by a rule the form allowed —
// the same shape as CONVENTIONS.md's upload limits. DECISIONS.md 070.
const MIN_PASSWORD_LENGTH = 8;
const MAX_PASSWORD_BYTES = 72;

const ENCODER = new TextEncoder();

function withinBcryptLimit(control: AbstractControl): ValidationErrors | null {
  return ENCODER.encode(String(control.value)).length > MAX_PASSWORD_BYTES
    ? { maxBytes: true }
    : null;
}

// Validators.required treats "   " as present, and the API accepts it, so a
// blank name would reach the column and render as an empty label. DECISIONS.md 070.
function requiredText(control: AbstractControl): ValidationErrors | null {
  return String(control.value).trim() === '' ? { required: true } : null;
}

@Component({
  selector: 'app-register-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, ReactiveFormsModule, RouterLink],
  template: `
    <main class="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-6 px-6 py-16">
      <h1 class="font-display text-4xl leading-tight tracking-tight">
        {{ i18n.t('register.title') }}
      </h1>

      <!-- novalidate, and no native 'required' on any field: both would hand
           submission back to the browser's constraint validation, which blocks
           it and shows an untranslatable bubble before our messages render.
           The unit suite cannot catch either being added back — its submits
           bypass constraint validation — so task 5.3 asserts this in a browser.
           'autocomplete="username"' on email and 'nickname' on the display name
           are deliberate token choices, not guesses. DECISIONS.md 070. -->
      <form [formGroup]="form" (ngSubmit)="submit()" novalidate class="flex flex-col gap-4">
        @let nameError = messageFor(form.controls.displayName);
        <div class="flex flex-col gap-1">
          <label for="displayName" class="text-sm">{{
            i18n.t('register.displayName.label')
          }}</label>
          <input
            id="displayName"
            type="text"
            formControlName="displayName"
            autocomplete="nickname"
            aria-required="true"
            [attr.aria-invalid]="nameError ? 'true' : null"
            [attr.aria-describedby]="nameError ? 'displayName-error' : null"
            class="min-h-11 rounded-md border border-line-strong bg-surface px-3 text-sm focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          />
          @if (nameError) {
            <p id="displayName-error" class="text-sm font-medium text-danger">{{ nameError }}</p>
          }
        </div>

        @let emailError = messageFor(form.controls.email);
        <div class="flex flex-col gap-1">
          <label for="email" class="text-sm">{{ i18n.t('register.email.label') }}</label>
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
          <label for="password" class="text-sm">{{ i18n.t('register.password.label') }}</label>
          <input
            id="password"
            type="password"
            formControlName="password"
            autocomplete="new-password"
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
          {{ submitting() ? i18n.t('register.submitting') : i18n.t('register.submit') }}
        </button>
      </form>

      <a
        routerLink="/login"
        class="text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('register.toLogin') }}
      </a>
    </main>
  `,
})
export class RegisterPage {
  protected readonly i18n = inject(I18nService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly submitting = signal(false);
  protected readonly serverError = signal<string | null>(null);

  protected readonly form = this.fb.group({
    displayName: ['', [requiredText]],
    email: ['', [Validators.required, Validators.email]],
    password: [
      '',
      [Validators.required, Validators.minLength(MIN_PASSWORD_LENGTH), withinBcryptLimit],
    ],
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
    const { displayName, email, password } = this.form.getRawValue();

    this.auth
      .register(email, password, displayName.trim())
      .pipe(finalize(() => this.submitting.set(false)))
      .subscribe({
        next: () => void this.router.navigateByUrl('/wardrobe'),
        error: (error: unknown) => this.serverError.set(this.serverMessageFor(error)),
      });
  }

  protected messageFor(control: AbstractControl): string | null {
    if (!control.touched || control.valid) {
      return null;
    }
    if (control.hasError('required')) {
      return this.i18n.t('validation.required');
    }
    if (control.hasError('email')) {
      return this.i18n.t('validation.email');
    }
    if (control.hasError('minlength')) {
      return this.i18n.t('validation.password.tooShort', { min: MIN_PASSWORD_LENGTH });
    }
    return this.i18n.t('validation.password.tooLong', { max: MAX_PASSWORD_BYTES });
  }

  private serverMessageFor(error: unknown): string {
    const taken = error instanceof HttpErrorResponse && error.status === 409;
    return this.i18n.t(taken ? 'register.error.emailExists' : 'error.unexpected');
  }
}

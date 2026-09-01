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

// Hand-copied from the backend: MIN_PASSWORD_LENGTH in app/schemas/auth.py and
// MAX_PASSWORD_BYTES in app/core/security.py. Nothing compares the two, and the
// drift is invisible until a user is rejected by a rule the form allowed —
// the same shape as CONVENTIONS.md's upload limits. DECISIONS.md 070.
const MIN_PASSWORD_LENGTH = 8;
const MAX_PASSWORD_BYTES = 72;

const ENCODER = new TextEncoder();

// Four of the five strings `login.page.ts` declares — this screen has no
// ghost control — for the reason recorded there: the two are twins, and
// neither is the definition of the other. DECISIONS.md 223.
const LABEL = 'font-mono text-[10px] font-medium tracking-[0.24em] text-ink-soft uppercase';

const FIELD =
  'min-h-11 border-b border-ink-soft bg-transparent py-2 font-sans text-[15px] focus:border-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

const PILL =
  'inline-flex min-h-11 items-center justify-center gap-x-2 rounded-full border border-ink bg-ink px-6 text-[11px] font-medium tracking-[0.22em] text-canvas uppercase disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

const SWAP_LINK =
  'ms-2 border-b border-accent pb-0.5 font-sans text-[11px] font-medium tracking-[0.22em] text-accent uppercase not-italic focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

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
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <!-- The login screen's frame, one field longer. Same wordmark, same
         tagline, same pill: what changes between the two is the title, the swap
         line and the number of rows. DECISIONS.md 223. -->
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
            {{ i18n.t('register.title') }}
          </h1>
          <p class="font-prose text-[17px] text-ink-muted italic">{{ i18n.t('auth.tagline') }}</p>
        </header>

        <!-- novalidate, and no native 'required' on any field: both would hand
             submission back to the browser's constraint validation, which blocks
             it and shows an untranslatable bubble before our messages render.
             The unit suite cannot catch either being added back — its submits
             bypass constraint validation — so task 5.3 asserts this in a browser.
             'autocomplete="username"' on email and 'nickname' on the display name
             are deliberate token choices, not guesses. DECISIONS.md 070. -->
        <form
          [formGroup]="form"
          (ngSubmit)="submit()"
          novalidate
          class="flex w-full max-w-[400px] flex-col gap-6"
        >
          @let nameError = messageFor(form.controls.displayName);
          <div class="flex flex-col gap-1.5">
            <label for="displayName" [class]="label">
              {{ i18n.t('register.displayName.label') }}
            </label>
            <input
              id="displayName"
              type="text"
              formControlName="displayName"
              autocomplete="nickname"
              aria-required="true"
              [attr.aria-invalid]="nameError ? 'true' : null"
              [attr.aria-describedby]="nameError ? 'displayName-error' : null"
              [class]="field"
            />
            @if (nameError) {
              <p id="displayName-error" class="text-sm font-medium text-danger">{{ nameError }}</p>
            }
          </div>

          @let emailError = messageFor(form.controls.email);
          <div class="flex flex-col gap-1.5">
            <label for="email" [class]="label">{{ i18n.t('register.email.label') }}</label>
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
            <label for="password" [class]="label">{{ i18n.t('register.password.label') }}</label>
            <input
              id="password"
              type="password"
              formControlName="password"
              autocomplete="new-password"
              aria-required="true"
              [attr.aria-invalid]="passwordError ? 'true' : null"
              [attr.aria-describedby]="passwordError ? 'password-error' : null"
              [class]="field"
            />
            @if (passwordError) {
              <p id="password-error" class="text-sm font-medium text-danger">{{ passwordError }}</p>
            }
          </div>

          @if (serverError(); as message) {
            <p class="text-sm font-medium text-danger">{{ message }}</p>
          }

          <button type="submit" [disabled]="submitting()" [class]="pill">
            {{ submitting() ? i18n.t('register.submitting') : i18n.t('register.submit') }}
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

          <p class="text-center font-prose text-[15px] text-ink-muted italic">
            {{ i18n.t('auth.swap.haveAccount') }}
            <a routerLink="/login" [class]="swap">{{ i18n.t('register.toLogin') }}</a>
          </p>
        </form>
      </div>
    </main>
  `,
})
export class RegisterPage {
  protected readonly i18n = inject(I18nService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly label = LABEL;
  protected readonly field = FIELD;
  protected readonly pill = PILL;
  protected readonly swap = SWAP_LINK;

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

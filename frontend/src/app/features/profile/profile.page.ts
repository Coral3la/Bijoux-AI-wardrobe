import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { MeApi } from '../../core/api/me.api';
import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { LocationResult } from '../../shared/models/location.model';
import { UserUpdate } from '../../shared/models/user.model';

// Mirrored from `02-DATA-MODEL.md`'s own `CHECK (height_cm BETWEEN 120 AND
// 230)`, which the request schema refuses rather than Postgres. Another of the
// mirrors CONVENTIONS.md records, here for the forecast horizon's reason in
// look-request-form.ts: the bound is the documented contract, and saying it on
// screen is cheaper than explaining the 422 it would otherwise produce.
export const MIN_HEIGHT_CM = 120;
export const MAX_HEIGHT_CM = 230;

// The provider's own floor, transcribed from 04-API-SPEC.md: one character
// matches nothing and two match only exactly. Shorter is a 422, so no request
// leaves the browser for it.
const MIN_QUERY_LENGTH = 2;

export const SEARCH_DEBOUNCE_MS = 300;

// What the three home columns hold, which is not what the picker offers:
// `country` is in a result to tell two Berlins apart (DECISIONS.md 153) and
// there is no column for it, so it is display text on the way in and is gone by
// the time anything is saved.
interface HomeLocation {
  readonly city: string;
  readonly lat: number;
  readonly lon: number;
}

function toWire(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

@Component({
  selector: 'app-profile-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <main class="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <a
        routerLink="/wardrobe"
        class="min-h-11 self-start text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('profile.back') }}
      </a>

      <h1 class="font-display text-3xl">{{ i18n.t('profile.title') }}</h1>

      <form [formGroup]="form" (ngSubmit)="submit()" novalidate class="flex flex-col gap-6">
        <label class="flex flex-col gap-1 text-sm">
          {{ i18n.t('profile.displayName.label') }}
          <input
            type="text"
            id="display_name"
            formControlName="display_name"
            [class]="fieldClass"
          />
        </label>

        <!-- Not a form control, unlike every other field here. The range
             message is a computed, a computed over a plain form control never
             recomputes because nothing tells it the value moved, and the number
             value accessor would then be a second place the string becomes a
             number. One signal, one coercion, one source for the wire. -->
        <div class="flex flex-col gap-1">
          <label for="height_cm" class="text-sm">{{ i18n.t('profile.height.label') }}</label>
          <input
            type="number"
            id="height_cm"
            [value]="height() ?? ''"
            (input)="onHeight($event)"
            [min]="MIN_HEIGHT_CM"
            [max]="MAX_HEIGHT_CM"
            [attr.aria-invalid]="heightOutOfRange() ? 'true' : null"
            [attr.aria-describedby]="heightOutOfRange() ? 'height-error' : null"
            [class]="fieldClass"
          />
          @if (heightOutOfRange()) {
            <p id="height-error" class="text-sm font-medium text-danger">
              {{ i18n.t('profile.height.range', { min: MIN_HEIGHT_CM, max: MAX_HEIGHT_CM }) }}
            </p>
          }
        </div>

        <!-- Free text, all three. The size columns are TEXT with no vocabulary
             anywhere — 02-DATA-MODEL.md gives them no CHECK and enums.py no
             members — so a select here would be this screen inventing a
             vocabulary the database does not have. -->
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
          @for (size of sizes; track size.name) {
            <label class="flex flex-col gap-1 text-sm">
              {{ i18n.t(size.label) }}
              <input
                type="text"
                [id]="size.name"
                [formControlName]="size.name"
                [placeholder]="i18n.t(size.placeholder)"
                [class]="fieldClass"
              />
            </label>
          }
        </div>

        <!-- The placeholder teaches by example, which is 05-FRONTEND-SPEC.md §8
             in as many words. This is the whole of the personalisation the
             brief sells: the string reaches the model verbatim, never matched
             or filtered, so an empty one is a USER PROFILE block that does not
             render at all. -->
        <label class="flex flex-col gap-1 text-sm">
          {{ i18n.t('profile.styleNotes.label') }}
          <textarea
            id="style_notes"
            rows="3"
            formControlName="style_notes"
            [placeholder]="i18n.t('profile.styleNotes.placeholder')"
            class="rounded-md border border-current/20 bg-surface p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          ></textarea>
        </label>

        <section class="flex flex-col gap-2">
          <h2 class="text-sm font-medium">{{ i18n.t('profile.home.label') }}</h2>
          <p class="text-sm opacity-70">{{ i18n.t('profile.home.hint') }}</p>

          @if (home(); as chosen) {
            <div class="flex items-center gap-3 rounded-lg bg-surface p-3">
              <p class="text-sm">{{ chosen.city }}</p>
              <button
                type="button"
                (click)="clearHome()"
                [attr.aria-label]="i18n.t('profile.home.clear')"
                class="ms-auto min-h-11 min-w-11 rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                ×
              </button>
            </div>
          } @else {
            <!-- Enter here searches; it does not save. A text input inside a
                 form submits it on Enter, and the one thing a half-typed city
                 name must not do is save the rest of the profile without it. -->
            <input
              type="text"
              id="home_query"
              [value]="query()"
              (input)="onQuery($event)"
              (keydown.enter)="$event.preventDefault()"
              [placeholder]="i18n.t('profile.home.searchPlaceholder')"
              autocapitalize="words"
              spellcheck="false"
              [class]="fieldClass"
            />

            @if (searching()) {
              <p class="text-sm" role="status" aria-live="polite">
                {{ i18n.t('profile.home.searching') }}
              </p>
            }
            @if (searchError()) {
              <p class="text-sm font-medium text-danger">{{ i18n.t('profile.home.error') }}</p>
            }
            @if (noMatches()) {
              <p class="text-sm">{{ i18n.t('profile.home.noResults') }}</p>
            }

            <ul class="flex flex-col gap-1">
              @for (result of results(); track result.lat + ':' + result.lon) {
                <li>
                  <button
                    type="button"
                    (click)="chooseHome(result)"
                    class="min-h-11 w-full rounded-md bg-surface px-3 text-start text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  >
                    {{
                      i18n.t('profile.home.result', {
                        name: result.name,
                        country: result.country,
                      })
                    }}
                  </button>
                </li>
              }
            </ul>
          }
        </section>

        @if (saveError()) {
          <p class="text-sm font-medium text-danger">{{ i18n.t('profile.error.save') }}</p>
        }
        @if (saved()) {
          <p class="text-sm" role="status" aria-live="polite">{{ i18n.t('profile.saved') }}</p>
        }

        <button
          type="submit"
          [disabled]="saving()"
          class="min-h-11 self-start rounded-md bg-accent px-4 text-surface disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {{ saving() ? i18n.t('profile.saving') : i18n.t('profile.save') }}
        </button>
      </form>
    </main>
  `,
})
export class ProfilePage {
  protected readonly i18n = inject(I18nService);
  private readonly auth = inject(AuthService);
  private readonly api = inject(MeApi);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly MIN_HEIGHT_CM = MIN_HEIGHT_CM;
  protected readonly MAX_HEIGHT_CM = MAX_HEIGHT_CM;
  protected readonly fieldClass =
    'min-h-11 rounded-md border border-current/20 bg-surface px-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

  protected readonly sizes = [
    {
      name: 'size_top',
      label: 'profile.sizeTop.label',
      placeholder: 'profile.sizeTop.placeholder',
    },
    {
      name: 'size_bottom',
      label: 'profile.sizeBottom.label',
      placeholder: 'profile.sizeBottom.placeholder',
    },
    {
      name: 'size_shoe',
      label: 'profile.sizeShoe.label',
      placeholder: 'profile.sizeShoe.placeholder',
    },
  ] as const;

  // Seeded once, from the session rather than from a request. There is no
  // `GET /me` — the profile the browser holds arrives as `GET /auth/me` at
  // bootstrap and is cached on AuthService, and authGuard has confirmed it
  // before this route renders. Seeded once for the tag editor's reason: the
  // save answers with the whole user, and re-seeding on that would throw away
  // anything typed since the request went out.
  protected readonly form = this.fb.group({
    display_name: '',
    size_top: '',
    size_bottom: '',
    size_shoe: '',
    style_notes: '',
  });

  protected readonly height = signal<number | null>(null);
  protected readonly home = signal<HomeLocation | null>(null);
  protected readonly query = signal('');
  protected readonly results = signal<readonly LocationResult[]>([]);
  protected readonly searching = signal(false);
  protected readonly searchError = signal(false);
  protected readonly saving = signal(false);
  protected readonly saveError = signal(false);
  protected readonly saved = signal(false);

  protected readonly heightOutOfRange = computed(() => {
    const value = this.height();
    return value !== null && (value < MIN_HEIGHT_CM || value > MAX_HEIGHT_CM);
  });

  // Distinct from "nothing searched yet": an empty list is only worth a
  // sentence once a search has come back with one.
  private readonly searched = signal(false);
  protected readonly noMatches = computed(
    () => this.searched() && !this.searching() && this.results().length === 0,
  );

  private timer: ReturnType<typeof setTimeout> | null = null;

  // Every search carries the number it was issued with, and an answer whose
  // number is stale is dropped. Debouncing makes two in flight uncommon rather
  // than impossible, and the failure that prevents is the ugly one: a slow
  // "ber" landing on top of a fast "berlin" and offering the wrong five cities.
  private issued = 0;

  constructor() {
    this.seed();
    // The timer has no owner otherwise, and one left running behind the next
    // screen fires a search into a destroyed component.
    inject(DestroyRef).onDestroy(() => this.stopTimer());
  }

  // The coercion is ours rather than the number input's, which is the tag
  // editor's rule about ranges applied one field over: an empty field is no
  // height, and anything else is whatever `Number` makes of it.
  protected onHeight(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.height.set(value.trim() === '' ? null : Number(value));
    this.saved.set(false);
  }

  protected onQuery(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.query.set(value);
    this.searchError.set(false);
    this.stopTimer();

    const trimmed = value.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      // Bumped so a search already in flight cannot answer into an input the
      // user has since emptied.
      this.issued += 1;
      this.searching.set(false);
      this.searched.set(false);
      this.results.set([]);
      return;
    }

    this.timer = setTimeout(() => this.search(trimmed), SEARCH_DEBOUNCE_MS);
  }

  protected chooseHome(result: LocationResult): void {
    // `country` is dropped rather than stored: there is no column for it, so
    // Berlin, Germany and Berlin, United States are both saved as "Berlin".
    // DECISIONS.md 153 recorded that limitation from the API's end; this is the
    // line where it bites.
    this.home.set({ city: result.name, lat: result.lat, lon: result.lon });
    this.query.set('');
    this.results.set([]);
    this.searched.set(false);
    this.saved.set(false);
  }

  protected clearHome(): void {
    this.home.set(null);
    this.saved.set(false);
  }

  protected submit(): void {
    // A height outside the bounds is refused here rather than sent: the message
    // is already on screen, and the 422 it would earn says the same thing one
    // round trip later.
    if (this.saving() || this.heightOutOfRange()) {
      return;
    }

    this.saving.set(true);
    this.saveError.set(false);
    this.saved.set(false);

    this.api
      .update(this.changes())
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (user) => {
          // The whole point of the task. The stylist reads home_lat and
          // home_lon off exactly this signal, so without it a look asked for on
          // the next screen still answers `home_location_missing` until the
          // page is reloaded.
          this.auth.acceptProfile(user);
          this.saved.set(true);
        },
        // One string for every rejection, on item detail's precedent: 04 names
        // the offending field inside `detail`, CONVENTIONS.md forbids rendering
        // a raw error, so this cannot say which field. DECISIONS.md 128.
        error: () => this.saveError.set(true),
      });
  }

  // All nine fields on every save, which is what makes the home trio safe to
  // send. `UserUpdate._home_is_one_field` refuses two of the three, an
  // unchanged home re-sent as the same three values is indistinguishable from
  // one that was never touched, and a cleared home leaves as three explicit
  // nulls — which is the documented way to clear it.
  private changes(): UserUpdate {
    const value = this.form.getRawValue();
    const home = this.home();
    return {
      display_name: toWire(value.display_name),
      height_cm: this.height(),
      size_top: toWire(value.size_top),
      size_bottom: toWire(value.size_bottom),
      size_shoe: toWire(value.size_shoe),
      style_notes: toWire(value.style_notes),
      home_city: home?.city ?? null,
      home_lat: home?.lat ?? null,
      home_lon: home?.lon ?? null,
    };
  }

  private search(q: string): void {
    this.issued += 1;
    const mine = this.issued;
    this.searching.set(true);

    this.api.searchLocations(q).subscribe({
      next: (response) => {
        if (mine !== this.issued) {
          return;
        }
        this.results.set(response.results);
        this.searched.set(true);
        this.searching.set(false);
      },
      error: () => {
        if (mine !== this.issued) {
          return;
        }
        this.results.set([]);
        this.searched.set(false);
        this.searching.set(false);
        this.searchError.set(true);
      },
    });
  }

  private seed(): void {
    const user = this.auth.currentUser();
    if (user === null) {
      return;
    }

    this.height.set(user.height_cm);
    this.form.setValue({
      display_name: user.display_name ?? '',
      size_top: user.size_top ?? '',
      size_bottom: user.size_bottom ?? '',
      size_shoe: user.size_shoe ?? '',
      style_notes: user.style_notes ?? '',
    });

    // One question, not three. The three columns are one field (DECISIONS.md
    // 151) and no request can leave two of them set, so a row that answers yes
    // to one answers yes to all.
    if (user.home_city !== null && user.home_lat !== null && user.home_lon !== null) {
      this.home.set({ city: user.home_city, lat: user.home_lat, lon: user.home_lon });
    }
  }

  private stopTimer(): void {
    if (this.timer === null) {
      return;
    }
    clearTimeout(this.timer);
    this.timer = null;
  }
}

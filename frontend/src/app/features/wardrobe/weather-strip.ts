import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { WeatherApi } from '../../core/api/weather.api';
import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { Weather } from '../../shared/models/weather.model';
import { todayInLocalTime } from '../stylist/look-request-form';

@Component({
  selector: 'app-weather-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <section
      class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg bg-surface px-4 py-3"
      [attr.aria-label]="i18n.t('wardrobe.weather.region')"
    >
      <!-- Body face, deliberately: the city is a name the user chose off the
           geocoder and may be non-Latin, which Fraunces does not cover — the
           rule 05-FRONTEND-SPEC.md line 292 names this strip in.
           DECISIONS.md 071. -->
      @if (summary(); as line) {
        <p class="text-sm">{{ line }}</p>
      } @else if (!hasHome()) {
        <!-- The degraded state §2.12 specifies, and the only place it points is
             the screen that fixes it. It replaces the temperature; it never
             replaces the strip, because the strip carries the way into the
             stylist. -->
        <a
          routerLink="/profile"
          class="inline-flex min-h-11 items-center rounded-md text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {{ i18n.t('wardrobe.weather.setHome') }}
        </a>
      }
      <!-- Third state, rendered as nothing: a home city is set and the forecast
           has not arrived, or did not. Silence rather than an apology, which is
           StylistStore.loadWeather's judgement one screen over — the forecast is
           context here, not the thing anybody asked for. What must not vanish
           with it is the link below. -->

      <!-- Present in every state, which is the whole of "the tap target does not
           depend on the forecast". A labelled link rather than the whole strip
           being tappable, because the degraded state puts a second link inside
           it and an anchor inside an anchor is not a document — 05 is annotated
           where it draws the strip itself as the target. -->
      <a
        routerLink="/stylist"
        class="ms-auto inline-flex min-h-11 items-center rounded-md bg-accent px-4 text-sm text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('wardrobe.weather.styleMe') }}
      </a>
    </section>
  `,
})
export class WeatherStrip {
  protected readonly i18n = inject(I18nService);
  private readonly auth = inject(AuthService);
  private readonly weatherApi = inject(WeatherApi);

  private readonly weather = signal<Weather | null>(null);

  // Both coordinates or neither: the three home columns are one field
  // (DECISIONS.md 151), so this is one question about the account rather than
  // two about the row.
  protected readonly hasHome = computed(() => {
    const user = this.auth.currentUser();
    return user !== null && user.home_lat !== null && user.home_lon !== null;
  });

  // The city comes off the account and the numbers off the forecast, so the
  // line exists only when both do. 151 makes that one condition rather than
  // two: an account with coordinates has a city name.
  protected readonly summary = computed(() => {
    const forecast = this.weather();
    const city = this.auth.currentUser()?.home_city ?? null;
    if (forecast === null || city === null) {
      return null;
    }
    return this.i18n.t('wardrobe.weather.line', {
      // The day's high, which is the number this project already means by "the
      // temperature": `summarize_forecast` prints `temp_max_c` to the model and
      // DECISIONS.md 142 settled it there. A strip and a prompt disagreeing
      // about today would be visible on one screen.
      temp: Math.round(forecast.temp_max_c),
      condition: this.i18n.t(`vocabulary.condition.${forecast.condition}`),
      city,
    });
  });

  // Fails silently, on the reasoning StylistStore.loadWeather records: the
  // forecast is context on a screen that works without it, and a red banner
  // over a wardrobe would report a failure the user cannot act on and did not
  // ask about. `todayInLocalTime` is imported rather than copied so this strip
  // and the stylist's date picker cannot disagree about which day "today" is.
  constructor() {
    const user = this.auth.currentUser();
    if (user === null || user.home_lat === null || user.home_lon === null) {
      return;
    }

    this.weatherApi.get(user.home_lat, user.home_lon, todayInLocalTime()).subscribe({
      next: (weather) => this.weather.set(weather),
      error: () => this.weather.set(null),
    });
  }
}

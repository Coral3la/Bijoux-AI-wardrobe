import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { WeatherApi } from '../../core/api/weather.api';
import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { Weather } from '../../shared/models/weather.model';
import { Button } from '../../shared/ui/button';
import { todayInLocalTime } from '../stylist/look-request-form';

@Component({
  selector: 'app-weather-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, RouterLink],
  template: `
    <section
      class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-surface p-4 shadow-sm"
      [attr.aria-label]="i18n.t('wardrobe.weather.region')"
    >
      <!-- Two lines rather than one sentence, and the split is what makes the
           display face legal here. The reading is a rounded number and a word
           from our own vocabulary, so Fraunces may have it; the city is a name
           the user chose off the geocoder and content rather than chrome — the
           rule 05-FRONTEND-SPEC.md's "The display face is for chrome we author"
           names this strip in. It stays in the body face at any size, and it
           would even if Fraunces covered Hebrew. DECISIONS.md 071. -->
      @if (forecastLines(); as lines) {
        <div class="flex flex-col gap-1">
          <p class="font-display text-2xl leading-tight">{{ lines.reading }}</p>
          <p class="text-xs font-medium tracking-widest text-ink-soft uppercase">
            {{ lines.place }}
          </p>
        </div>
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
      <a appButton routerLink="/stylist" class="ms-auto">
        {{ i18n.t('wardrobe.weather.styleMe') }}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="ms-2 h-4 w-4"
          aria-hidden="true"
        >
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
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
  // lines exist only when both do. 151 makes that one condition rather than
  // two: an account with coordinates has a city name.
  protected readonly forecastLines = computed(() => {
    const forecast = this.weather();
    const city = this.auth.currentUser()?.home_city ?? null;
    if (forecast === null || city === null) {
      return null;
    }
    return {
      // Each line is one whole key, never assembled from fragments: a sentence
      // broken up so that half of it can be styled cannot be reordered for a
      // language that puts it the other way round.
      //
      // The temperature is the day's high, which is the number this project
      // already means by "the temperature": `summarize_forecast` prints
      // `temp_max_c` to the model and DECISIONS.md 142 settled it there. A
      // strip and a prompt disagreeing about today would be visible on one
      // screen.
      reading: this.i18n.t('wardrobe.weather.reading', {
        temp: Math.round(forecast.temp_max_c),
        condition: this.i18n.t(`vocabulary.condition.${forecast.condition}`),
      }),
      place: this.i18n.t('wardrobe.weather.place', { city }),
    };
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

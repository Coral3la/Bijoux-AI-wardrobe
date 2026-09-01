import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { WeatherApi } from '../../core/api/weather.api';
import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { Weather } from '../../shared/models/weather.model';
import { AuthoredLine } from '../../shared/ui/authored-line';
import { todayInLocalTime } from '../stylist/look-request-form';

@Component({
  selector: 'app-weather-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [AuthoredLine, RouterLink],
  template: `
    <!-- One line and a rule under it, where DR.12 left a card. The card was
         deferred at DR.12 on the grounds that DR.15 would decide the ground
         first, and the picked mockup decides both at once: on the cream ground
         a white panel with a shadow is the only raised object on the screen,
         and the forecast is the least important thing on it. What is left is
         the sentence, the reading, and the way into the stylist — which is
         everything the card ever carried. DECISIONS.md 219. -->
    <section
      class="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3 border-b border-line pb-6"
      [attr.aria-label]="i18n.t('wardrobe.weather.region')"
    >
      <!-- One sentence, and the city inside it is content while the sentence
           around it is ours — so the city alone leaves the prose face. Until
           DR.12 this strip was two separate keys, and that split was a
           workaround rather than a design: 071 had no way to put a geocoded
           name inside an authored line, so the line was cut in half to keep
           the display face away from it. AuthoredLine is the answer the split
           was standing in for, and the key is whole again — a translator can
           put the city placeholder first and only the city moves.

           The condition leads the sentence because the condition vocabulary is
           capitalised for chip use: "Clear in Tel Aviv-Yafo today" is right
           where "It's Clear in …" is not. The vocabulary's existing shape
           decided the word order rather than the other way round. This strip is
           the canonical instance 05-FRONTEND-SPEC.md's "The display face is for
           chrome we author" names. DECISIONS.md 218.

           No backtick and no interpolation braces in this comment: it lives
           inside the component's template literal, so a backtick would end the
           string. DECISIONS.md 218. -->
      @if (forecast(); as today) {
        <p
          class="flex flex-wrap items-baseline gap-x-2 font-prose text-[17px] text-ink-muted italic"
        >
          <app-authored-line
            key="wardrobe.weather.sentence"
            [params]="today.params"
            [content]="today.content"
          />
          <!-- The reading leaves the italic and takes the mono face, which is
               the one rule this screen applies to every number on it: the piece
               count in the header and the counts on the chips are drawn the
               same way. It is still chrome — a number this project rounded and
               formatted — so 071 is unbroken; what changed is which authored
               face a numeral takes. The middle dot in front of it is in the
               string table with the degree sign, because it is punctuation
               joining two clauses of one line rather than a separator this
               template invented. -->
          <span class="font-mono text-[15px] text-ink tabular-nums not-italic">{{
            today.reading
          }}</span>
        </p>
      } @else if (!hasHome()) {
        <!-- The degraded state §2.12 specifies, and the only place it points is
             the screen that fixes it. It replaces the temperature; it never
             replaces the strip, because the strip carries the way into the
             stylist. -->
        <a
          routerLink="/profile"
          class="inline-flex min-h-11 items-center font-prose text-[17px] text-ink-muted italic underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
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
           where it draws the strip itself as the target.

           No appButton any more: the directive paints the accent-filled pill
           the pre-Atelier language uses, and a filled button is the loudest
           object on a screen whose loudest object is meant to be a photograph.
           The 44px floor is kept by min-h-11 rather than by the directive. -->
      <a
        routerLink="/stylist"
        class="ms-auto inline-flex min-h-11 items-center gap-x-2 border-b border-accent text-[11px] font-medium tracking-[0.22em] text-accent uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('wardrobe.weather.styleMe') }}
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

  // The city comes off the account and the numbers off the forecast, so this
  // exists only when both do. 151 makes that one condition rather than two: an
  // account with coordinates has a city name.
  protected readonly forecast = computed(() => {
    const weather = this.weather();
    const city = this.auth.currentUser()?.home_city ?? null;
    if (weather === null || city === null) {
      return null;
    }
    return {
      // The temperature is the day's high, which is the number this project
      // already means by "the temperature": `summarize_forecast` prints
      // `temp_max_c` to the model and DECISIONS.md 142 settled it there. A
      // strip and a prompt disagreeing about today would be visible on one
      // screen. The unit is gone with the card: the line reads "· 27°" now,
      // because a screen that shows one temperature a day in one city does not
      // have to say which scale it is on, and the C was the only Latin letter
      // in a run of digits set in the mono face.
      reading: this.i18n.t('wardrobe.weather.reading', {
        temp: Math.round(weather.temp_max_c),
      }),
      // Two dictionaries, and the split is the whole point: the condition is a
      // word out of our own closed vocabulary and stays in the authored face,
      // the city came off a geocoder and does not. A single dictionary with a
      // list of content names would let a forgotten entry render a city in the
      // wrong face with nothing to catch it. DECISIONS.md 213.
      params: { condition: this.i18n.t(`vocabulary.condition.${weather.condition}`) },
      content: { city },
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

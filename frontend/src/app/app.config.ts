import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { AuthService } from './core/auth/auth.service';
import { jwtInterceptor } from './core/auth/jwt.interceptor';
import { I18nService } from './core/i18n/i18n.service';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([jwtInterceptor])),
    provideAppInitializer(() => inject(I18nService).load()),
    // The promise is returned, so bootstrap waits for it: authGuard reads
    // currentUser, and admitting a route on a token the server has not
    // confirmed is the inconsistency this closes. DECISIONS.md 067.
    provideAppInitializer(() => inject(AuthService).restore()),
  ],
};

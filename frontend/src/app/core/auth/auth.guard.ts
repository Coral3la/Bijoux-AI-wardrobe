import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  return auth.isAuthenticated() ? true : router.createUrlTree(['/login']);
};

// The mirror image, kept in this file rather than a fourth under core/auth/:
// 05-FRONTEND-SPEC.md names three files there, and the two rules document each
// other better adjacent than apart. Only ever consulted against a token the
// bootstrap restore has already confirmed. DECISIONS.md 069.
export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  return auth.isAuthenticated() ? router.createUrlTree(['/wardrobe']) : true;
};

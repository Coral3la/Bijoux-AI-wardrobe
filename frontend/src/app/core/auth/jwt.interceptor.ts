import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';

// /auth/me is bearer-authenticated on the server, so the skip list names the
// two endpoints that are genuinely anonymous rather than the whole prefix.
// Both halves use it: a 401 from /auth/login means the password was wrong,
// not that a session ended. DECISIONS.md 060.
const ANONYMOUS_PATHS = ['/auth/login', '/auth/register'];

export const jwtInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith(environment.apiUrl)) {
    return next(request);
  }

  const path = request.url.slice(environment.apiUrl.length);
  if (ANONYMOUS_PATHS.some((anonymous) => path.startsWith(anonymous))) {
    return next(request);
  }

  // Both injections happen here rather than inside catchError, which runs
  // outside the injection context and would throw at runtime.
  const auth = inject(AuthService);
  const router = inject(Router);

  const token = auth.token();
  const authorized =
    token === null ? request : request.clone({ setHeaders: { Authorization: `Bearer ${token}` } });

  return next(authorized).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 401) {
        auth.rejectSession();
        // DECISIONS.md 068
        if (router.navigated) {
          router.navigateByUrl('/login');
        }
      }
      return throwError(() => error);
    }),
  );
};

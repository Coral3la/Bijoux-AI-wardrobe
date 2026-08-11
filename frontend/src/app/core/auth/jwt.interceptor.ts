// frontend/src/app/core/auth/jwt.interceptor.ts
import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';

// /auth/me is bearer-authenticated on the server, so the skip list names the
// two endpoints that are genuinely anonymous rather than the whole prefix.
const ANONYMOUS_PATHS = ['/auth/login', '/auth/register'];

export const jwtInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith(environment.apiUrl)) {
    return next(request);
  }

  const path = request.url.slice(environment.apiUrl.length);
  if (ANONYMOUS_PATHS.some((anonymous) => path.startsWith(anonymous))) {
    return next(request);
  }

  const token = inject(AuthService).token();
  if (token === null) {
    return next(request);
  }

  return next(request.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};

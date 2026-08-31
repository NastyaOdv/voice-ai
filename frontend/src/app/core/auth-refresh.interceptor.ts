import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Observable, catchError, finalize, shareReplay, switchMap, throwError } from 'rxjs';

/**
 * Transparent access-token refresh.
 *
 * The access cookie is short-lived (15 min); the refresh cookie lasts 7 days. When any
 * API call comes back 401, we POST `/api/auth/refresh` once (which sets fresh cookies)
 * and replay the original request. Concurrent 401s share a single in-flight refresh, so
 * a burst of requests triggers only one refresh. If the refresh itself fails (refresh
 * cookie gone/expired), the original 401 propagates and the guard bounces to /login.
 */

// Endpoints where a 401 is terminal (bad credentials / already refreshing) — never retry.
const NO_REFRESH = [
  '/api/auth/login',
  '/api/auth/register',
  '/api/auth/refresh',
  '/api/auth/logout',
];

// Module-level so all requests share one in-flight refresh.
let refresh$: Observable<unknown> | null = null;

export const authRefreshInterceptor: HttpInterceptorFn = (req, next) => {
  const http = inject(HttpClient);

  return next(req).pipe(
    catchError((error: unknown) => {
      const is401 = error instanceof HttpErrorResponse && error.status === 401;
      if (!is401 || NO_REFRESH.some((path) => req.url.startsWith(path))) {
        return throwError(() => error);
      }

      if (!refresh$) {
        refresh$ = http.post('/api/auth/refresh', {}).pipe(
          shareReplay(1),
          finalize(() => {
            refresh$ = null;
          }),
        );
      }

      return refresh$.pipe(
        switchMap(() => next(req)), // refreshed — replay the original request
        catchError(() => throwError(() => error)), // refresh failed — surface the 401
      );
    }),
  );
};

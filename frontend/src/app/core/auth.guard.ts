import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { AuthService } from './auth.service';

/**
 * Protects routes that require a logged-in user. On a fresh page load the user
 * signal is empty, so we probe `/auth/me` (which relies on the access cookie);
 * a 401 there means "not logged in" and we bounce to /login.
 */
export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.isAuthenticated()) {
    return true;
  }

  return auth.loadUser().pipe(
    map(() => true),
    catchError(() => of(router.createUrlTree(['/login']))),
  );
};

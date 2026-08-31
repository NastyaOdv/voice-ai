import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, switchMap, tap } from 'rxjs';

import { User } from './models';

interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

/**
 * Auth is cookie-based: the backend sets httponly access/refresh cookies, so the
 * SPA never stores tokens. We only track the current user, resolved via `/auth/me`.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  private readonly currentUser = signal<User | null>(null);
  readonly user = this.currentUser.asReadonly();
  readonly isAuthenticated = computed(() => this.currentUser() !== null);

  register(email: string, password: string): Observable<User> {
    return this.http
      .post<TokenPair>('/api/auth/register', { email, password })
      .pipe(switchMap(() => this.loadUser()));
  }

  login(email: string, password: string): Observable<User> {
    return this.http
      .post<TokenPair>('/api/auth/login', { email, password })
      .pipe(switchMap(() => this.loadUser()));
  }

  /**
   * Start the Google OAuth flow. This is a full-page navigation (not an XHR): the
   * backend redirects to Google, and its callback redirects back to the SPA with the
   * auth cookies already set. Works for both sign-in and sign-up (accounts are linked
   * or created on the backend by Google `sub`/email).
   */
  loginWithGoogle(): void {
    window.location.href = '/api/auth/google/login';
  }

  logout(): Observable<void> {
    return this.http
      .post<void>('/api/auth/logout', {})
      .pipe(tap(() => this.currentUser.set(null)));
  }

  /** Resolve the current user from the access cookie; clears state on 401. */
  loadUser(): Observable<User> {
    return this.http
      .get<User>('/api/auth/me')
      .pipe(tap((user) => this.currentUser.set(user)));
  }
}

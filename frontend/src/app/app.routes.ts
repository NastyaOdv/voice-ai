import { Routes } from '@angular/router';

import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'sessions' },
  {
    path: 'login',
    loadComponent: () => import('./pages/login/login').then((m) => m.Login),
  },
  {
    path: 'signup',
    loadComponent: () => import('./pages/signup/signup').then((m) => m.Signup),
  },
  {
    path: 'sessions',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/sessions/sessions').then((m) => m.Sessions),
  },
  {
    path: 'sessions/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/session-detail/session-detail').then((m) => m.SessionDetailPage),
  },
  {
    path: 'notes',
    canActivate: [authGuard],
    loadComponent: () => import('./notes/notes').then((m) => m.Notes),
  },
  { path: '**', redirectTo: 'sessions' },
];

import { Routes } from '@angular/router';

import { authGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login.page').then((m) => m.LoginPage),
  },
  {
    path: 'register',
    loadComponent: () => import('./features/auth/register.page').then((m) => m.RegisterPage),
  },
  {
    path: 'wardrobe',
    canActivate: [authGuard],
    loadComponent: () => import('./features/wardrobe/wardrobe.page').then((m) => m.WardrobePage),
  },
  { path: '', pathMatch: 'full', redirectTo: 'wardrobe' },
  { path: '**', redirectTo: 'wardrobe' },
];

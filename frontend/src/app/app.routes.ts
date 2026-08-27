import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login.page').then((m) => m.LoginPage),
  },
  {
    path: 'register',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/register.page').then((m) => m.RegisterPage),
  },
  {
    path: 'wardrobe',
    canActivate: [authGuard],
    loadComponent: () => import('./features/wardrobe/wardrobe.page').then((m) => m.WardrobePage),
  },
  // Declared before the wildcard below, which would otherwise swallow it and
  // send every item link back to the grid. Its own guard rather than a child of
  // /wardrobe: the grid is not kept alive underneath, so nesting would buy a
  // shared layout this screen does not have. DECISIONS.md 127.
  {
    path: 'wardrobe/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/wardrobe/item-detail.page').then((m) => m.ItemDetailPage),
  },
  // Above the wildcard for the reason wardrobe/:id is: everything below it
  // redirects. No entry point links here yet — the weather strip at 2.12 is
  // the one 05-FRONTEND-SPEC.md draws, and it is not this task's to build.
  {
    path: 'stylist',
    canActivate: [authGuard],
    loadComponent: () => import('./features/stylist/stylist.page').then((m) => m.StylistPage),
  },
  { path: '', pathMatch: 'full', redirectTo: 'wardrobe' },
  { path: '**', redirectTo: 'wardrobe' },
];

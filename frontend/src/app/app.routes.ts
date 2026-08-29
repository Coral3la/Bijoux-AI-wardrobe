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
  // Above the wildcard for the same reason, and with no link into it: `app.html`
  // is a bare router-outlet, and STAGE-2 2.10a specifies the screen without
  // saying how it is reached. The wardrobe header is where 05-FRONTEND-SPEC.md
  // §2 would put it; that is not this task's to decide.
  {
    path: 'profile',
    canActivate: [authGuard],
    loadComponent: () => import('./features/profile/profile.page').then((m) => m.ProfilePage),
  },
  // Above the wildcard, and with nothing linking to it — the third screen in
  // this project built without an entry point, after /profile and /stylist
  // before 2.12. STAGE-3 3.2 specifies the screen and not the way in, and a
  // nav bar is nobody's task yet. AUDITS.md O-29.
  {
    path: 'saved',
    canActivate: [authGuard],
    loadComponent: () => import('./features/looks/saved-looks.page').then((m) => m.SavedLooksPage),
  },
  { path: '', pathMatch: 'full', redirectTo: 'wardrobe' },
  { path: '**', redirectTo: 'wardrobe' },
];

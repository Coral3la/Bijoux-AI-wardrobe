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
  // Reached from the wardrobe's account row, beside /profile. It
  // shipped at 3.2 with nothing linking to it — the third screen in this
  // project built without an entry point, after /profile and /stylist before
  // 2.12 — and the link that fixed that is the fifth bespoke one, not the nav
  // bar AUDITS.md O-29 asks for. That item is still open.
  {
    path: 'saved',
    canActivate: [authGuard],
    loadComponent: () => import('./features/looks/saved-looks.page').then((m) => m.SavedLooksPage),
  },
  // The list at 4.10, and the form until then. The comment that stood here said
  // the screen was reached by typing the URL until something claimed AUDITS.md
  // O-29; 4.9 claimed it, and this is where that sentence finally goes. The
  // navigation bar's Trips item points at this path, and because
  // routerLinkActive matches a link's segments as a prefix, it stays lit on
  // both of the routes below as well.
  {
    path: 'trips',
    canActivate: [authGuard],
    loadComponent: () => import('./features/trips/trip-list.page').then((m) => m.TripListPage),
  },
  // Above trips/:id, and the order is load-bearing rather than tidy: below it,
  // 'new' matches the :id segment, the Itinerary asks GET /trips/new for a trip
  // that does not exist and the form is unreachable at any URL. The spec
  // asserts the route that matched rather than the resulting address, because a
  // URL that resolves the wrong screen still looks exactly right in the bar.
  {
    path: 'trips/new',
    canActivate: [authGuard],
    loadComponent: () => import('./features/trips/trips.page').then((m) => m.TripsPage),
  },
  // Declared under both of the routes above and before the wildcard, exactly as
  // wardrobe/:id sits after /wardrobe. It has had a way in since it shipped —
  // the form navigates here the instant a pack succeeds, which is what closes
  // the dead end DECISIONS.md 205 accepted — and 4.10 gives it a second one
  // that survives a lost URL, which is the whole point of the list.
  {
    path: 'trips/:id',
    canActivate: [authGuard],
    loadComponent: () => import('./features/trips/trip-detail.page').then((m) => m.TripDetailPage),
  },
  { path: '', pathMatch: 'full', redirectTo: 'wardrobe' },
  { path: '**', redirectTo: 'wardrobe' },
];

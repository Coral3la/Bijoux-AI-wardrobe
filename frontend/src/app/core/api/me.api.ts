import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { LocationSearchResponse } from '../../shared/models/location.model';
import { User, UserUpdate } from '../../shared/models/user.model';

@Injectable({ providedIn: 'root' })
export class MeApi {
  private readonly http = inject(HttpClient);

  // No trailing slash, for items.api.ts's reason: the route is declared as
  // patch("") under prefix "/me", so /me/ is a different path and answers with
  // a redirect.
  //
  // The body goes out as the caller built it. An unknown key is a 422 rather
  // than being dropped, and an empty body is a 422 too, so there is nothing
  // this method should add for convenience.
  update(changes: UserUpdate): Observable<User> {
    return this.http.patch<User>(`${environment.apiUrl}/me`, changes);
  }

  // The caller trims and measures before calling: `q` shorter than two
  // characters is a 422, and a type-ahead should not spend a request finding
  // that out on the first keystroke.
  searchLocations(q: string): Observable<LocationSearchResponse> {
    return this.http.get<LocationSearchResponse>(`${environment.apiUrl}/me/locations/search`, {
      params: { q },
    });
  }
}

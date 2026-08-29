import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  Look,
  LookListResponse,
  LookUpdate,
  SuggestRequest,
  SuggestResponse,
} from '../../shared/models/look.model';

@Injectable({ providedIn: 'root' })
export class LooksApi {
  private readonly http = inject(HttpClient);

  // The body goes out exactly as the caller built it. The schema rejects an
  // unknown field with a 422 rather than dropping it, so a key added here by
  // convenience would break the request instead of being ignored — which is
  // the behaviour 04-API-SPEC.md asks for and the reason SuggestRequest
  // carries no field this stage cannot send.
  suggest(request: SuggestRequest): Observable<SuggestResponse> {
    return this.http.post<SuggestResponse>(`${environment.apiUrl}/looks/suggest`, request);
  }

  // No trailing slash, for items.api.ts's reason: the route is get("") under
  // prefix "/looks", so /looks/ is a different path and answers a redirect.
  //
  // `is_saved` is the only filter any caller sends. The endpoint also takes
  // `from_date` and `to_date`, and `04-API-SPEC.md` names a `trip_id` the
  // server does not implement until migration 0005 — none of the three has a
  // screen, so none of them is a parameter here.
  listSaved(): Observable<LookListResponse> {
    return this.http.get<LookListResponse>(`${environment.apiUrl}/looks`, {
      params: { is_saved: true },
    });
  }

  // PATCH, not PUT: the endpoint merges, and a key left out of the body is a
  // field left alone. Sending `{ is_saved: false }` is how a look is unsaved —
  // there is no DELETE for the flag.
  update(id: string, changes: LookUpdate): Observable<Look> {
    return this.http.patch<Look>(`${environment.apiUrl}/looks/${id}`, changes);
  }
}

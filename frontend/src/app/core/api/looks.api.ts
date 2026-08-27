import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { SuggestRequest, SuggestResponse } from '../../shared/models/look.model';

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
}

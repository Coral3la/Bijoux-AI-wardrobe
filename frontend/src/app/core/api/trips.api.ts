import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { PackRequest, PackResponse } from '../../shared/models/trip.model';

@Injectable({ providedIn: 'root' })
export class TripsApi {
  private readonly http = inject(HttpClient);

  // One method for five endpoints, on `looks.api.ts`'s rule: a parameter with
  // no screen is not written. `GET /trips` has no planned caller at all and
  // 04-API-SPEC.md records that deliberately; `GET /trips/{id}`,
  // `POST /trips/{id}/repack` and `DELETE /trips/{id}` are 4.6's and 4.7's.
  //
  // The body goes out exactly as the caller built it. The request schema
  // rejects an unknown key with a 422 rather than dropping it, so a field added
  // here for convenience would break the request instead of being ignored.
  pack(request: PackRequest): Observable<PackResponse> {
    return this.http.post<PackResponse>(`${environment.apiUrl}/trips/pack`, request);
  }
}

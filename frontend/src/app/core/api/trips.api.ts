import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { PackRequest, PackResponse, TripDetail } from '../../shared/models/trip.model';

@Injectable({ providedIn: 'root' })
export class TripsApi {
  private readonly http = inject(HttpClient);

  // Two methods for five endpoints, on `looks.api.ts`'s rule: a parameter with
  // no screen is not written. `GET /trips` has no planned caller at all and
  // 04-API-SPEC.md records that deliberately; `POST /trips/{id}/repack` and
  // `DELETE /trips/{id}` have no owning task in Stage 4 at all, which
  // AUDITS.md O-33 records rather than answering here.
  //
  // The body goes out exactly as the caller built it. The request schema
  // rejects an unknown key with a 422 rather than dropping it, so a field added
  // here for convenience would break the request instead of being ignored.
  pack(request: PackRequest): Observable<PackResponse> {
    return this.http.post<PackResponse>(`${environment.apiUrl}/trips/pack`, request);
  }

  // `TripDetail` rather than `PackResponse`: this endpoint answers everything
  // that one does except `missing_pieces`, which described the run rather than
  // the trip and was never stored.
  get(id: string): Observable<TripDetail> {
    return this.http.get<TripDetail>(`${environment.apiUrl}/trips/${id}`);
  }
}

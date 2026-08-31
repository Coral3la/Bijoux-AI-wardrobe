import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { PackRequest, PackResponse, TripDetail } from '../../shared/models/trip.model';

@Injectable({ providedIn: 'root' })
export class TripsApi {
  private readonly http = inject(HttpClient);

  // Four methods for five endpoints, on `looks.api.ts`'s rule: a parameter with
  // no screen is not written. `GET /trips` is the one left out, and it has no
  // planned caller at all — 04-API-SPEC.md records that deliberately. The other
  // two arrive at task 4.6b with the controls that call them, which closes
  // AUDITS.md O-33.
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

  // `null` rather than `{}`, which is what "takes no request body" means on the
  // wire: an empty object is a body, and it would set a `Content-Type` on a
  // request the endpoint declares no schema for. The trip's destination, dates,
  // occasions and notes are re-read from the stored row (DECISIONS.md 202), so
  // there is nothing for a caller to send.
  repack(id: string): Observable<PackResponse> {
    return this.http.post<PackResponse>(`${environment.apiUrl}/trips/${id}/repack`, null);
  }

  // `remove`, not `delete`: `items.api.ts` names its method for what the call
  // does rather than for its verb, and there the two differ — a DELETE that
  // archives is `archive`. This one really does destroy the row and its looks
  // with it, and `204` is the whole of the answer.
  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiUrl}/trips/${id}`);
  }
}

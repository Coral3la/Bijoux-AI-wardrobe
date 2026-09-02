import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  PackRequest,
  PackResponse,
  TripDetail,
  TripList,
  TripSwapRequest,
} from '../../shared/models/trip.model';

@Injectable({ providedIn: 'root' })
export class TripsApi {
  private readonly http = inject(HttpClient);

  // Six methods for six endpoints, on `looks.api.ts`'s rule: a parameter with
  // no screen is not written — which is the whole of why `list` sends neither
  // `limit` nor `offset`. *The previous version of this sentence said `GET
  // /trips` "has no planned caller at all"; task 4.10 is the caller, and
  // 04-API-SPEC.md's paragraph promising it would never have one is amended in
  // the same commit rather than left to contradict this file.*
  //
  // The body goes out exactly as the caller built it. The request schema
  // rejects an unknown key with a 422 rather than dropping it, so a field added
  // here for convenience would break the request instead of being ignored.
  pack(request: PackRequest): Observable<PackResponse> {
    return this.http.post<PackResponse>(`${environment.apiUrl}/trips/pack`, request);
  }

  // Ahead of `get` because that is 04-API-SPEC.md's order, and it is the order
  // a reader meets these in. No `limit` and no `offset`: one page is what the
  // screen renders, the server's default is 100, and a parameter a caller would
  // only ever send the default for is a parameter with no screen. Pagination
  // arrives with the control that asks for it.
  list(): Observable<TripList> {
    return this.http.get<TripList>(`${environment.apiUrl}/trips`);
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

  // `TripDetail`, the same shape `get` answers, because a swap edits one day and
  // replies with the whole trip: `packing_list` has moved, so `days[]`, the reuse
  // summary and every look are re-read together (DECISIONS.md 209). The `id` is
  // separated from the body because the trip is in the path and the day is not —
  // `days[]` is a computed view, so there is no `/days/{day}` to post to.
  swap(id: string, request: TripSwapRequest): Observable<TripDetail> {
    return this.http.post<TripDetail>(`${environment.apiUrl}/trips/${id}/swap`, request);
  }
}

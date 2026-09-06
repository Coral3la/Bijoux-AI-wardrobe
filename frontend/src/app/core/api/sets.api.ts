import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  ItemSet,
  ItemSetCreateRequest,
  ItemSetMemberRequest,
} from '../../shared/models/item-set.model';

@Injectable({ providedIn: 'root' })
export class SetsApi {
  private readonly http = inject(HttpClient);

  // Five methods for the five endpoints, and four of them have a caller. The
  // exception is `remove`: STAGE-4A gives the set row two controls, *add* and
  // *remove this garment*, and no control that throws a whole set away — a set
  // of two is ended by removing one member, which is `removeItem`'s 204, and
  // the server deletes the row rather than this client. It is written anyway
  // because 4A.2's brief is the five endpoints, which is a deliberate departure
  // from looks.api.ts's standing rule that a call with no screen is not
  // written. Whoever gives it a screen should know it is the only method here
  // that no test in this project drives through a component.
  //
  // No trailing slash, for items.api.ts's reason: the route is declared as
  // post("") under prefix "/sets", so /sets/ is a different path and answers
  // with a redirect — which works in a browser and fails a CORS preflight.
  create(request: ItemSetCreateRequest): Observable<ItemSet> {
    return this.http.post<ItemSet>(`${environment.apiUrl}/sets`, request);
  }

  get(id: string): Observable<ItemSet> {
    return this.http.get<ItemSet>(`${environment.apiUrl}/sets/${id}`);
  }

  // `remove`, not `archive`: trips.api.ts's rule that a method is named for
  // what the call does rather than for its verb, and here the two differ from
  // items.api.ts — a DELETE that soft-deletes is `archive`, and this one really
  // destroys the row. It destroys no garment: ON DELETE SET NULL clears set_id
  // on every member and the items keep their tags, their wear counts and their
  // place in every look, which is why 204 is the whole of the answer.
  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiUrl}/sets/${id}`);
  }

  addItem(setId: string, request: ItemSetMemberRequest): Observable<ItemSet> {
    return this.http.post<ItemSet>(`${environment.apiUrl}/sets/${setId}/items`, request);
  }

  // Two status codes on one path, and the null is the second of them. 200
  // answers with the set that survived; 204 means the removal left one member
  // behind, so the set is gone and there is nothing to answer with. Angular
  // hands an empty body to a subscriber as `null`, so the branch the API spec
  // says the client has to make anyway is a value here rather than an
  // HttpResponse to unwrap — absorbed in this layer because the status code is
  // the wire's business and "did the set survive" is the call site's.
  removeItem(setId: string, itemId: string): Observable<ItemSet | null> {
    return this.http.delete<ItemSet | null>(`${environment.apiUrl}/sets/${setId}/items/${itemId}`);
  }
}

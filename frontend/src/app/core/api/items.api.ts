import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Item, ItemListResponse } from '../../shared/models/item.model';

@Injectable({ providedIn: 'root' })
export class ItemsApi {
  private readonly http = inject(HttpClient);

  // No trailing slash. The route is declared as get("") under prefix
  // "/items", so /items/ is a different path and answers with a redirect.
  list(limit: number): Observable<ItemListResponse> {
    return this.http.get<ItemListResponse>(`${environment.apiUrl}/items`, { params: { limit } });
  }

  // No `force` parameter: overwriting a hand-corrected item needs a
  // confirmation, and that belongs beside the "You edited this" badge on item
  // detail (task 1.9). Sending force=true from a grid tile would defeat the
  // only thing the 409 exists to do.
  retag(id: string): Observable<Item> {
    return this.http.post<Item>(`${environment.apiUrl}/items/${id}/retag`, null);
  }
}

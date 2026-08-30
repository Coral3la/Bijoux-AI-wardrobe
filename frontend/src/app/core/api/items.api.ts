import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { ItemStatus } from '../../shared/models/enums';
import {
  Item,
  ItemListResponse,
  ItemStatsResponse,
  ItemUpdate,
  ItemUploadResponse,
} from '../../shared/models/item.model';

@Injectable({ providedIn: 'root' })
export class ItemsApi {
  private readonly http = inject(HttpClient);

  // No trailing slash. The route is declared as get("") under prefix
  // "/items", so /items/ is a different path and answers with a redirect.
  //
  // One method with an optional status rather than a second `listProcessing`:
  // the poll and the reload are two requests on purpose (DECISIONS.md 102) and
  // the call site is where that should be legible. A vocabulary value in a
  // method name would hide it, and nothing else in this project does that.
  list(limit: number, status?: ItemStatus): Observable<ItemListResponse> {
    const params: Record<string, string | number> = { limit };
    if (status !== undefined) {
      params['status'] = status;
    }
    return this.http.get<ItemListResponse>(`${environment.apiUrl}/items`, { params });
  }

  // A GET on a fixed path that could be read as an id, which is why the route
  // is declared above GET /{item_id} on the server — below it, `stats` is
  // parsed as a UUID and answers 422. Nothing here can go wrong on the client
  // side of that: there is no parameter to get wrong and no trailing slash.
  stats(): Observable<ItemStatsResponse> {
    return this.http.get<ItemStatsResponse>(`${environment.apiUrl}/items/stats`);
  }

  // Every file goes under the field name `files`, which is the route's
  // parameter name and therefore the multipart field the server reads. No
  // Content-Type is set: the browser has to write its own multipart boundary,
  // and setting the header by hand removes it.
  upload(files: readonly File[]): Observable<ItemUploadResponse> {
    const body = new FormData();
    for (const file of files) {
      body.append('files', file);
    }
    return this.http.post<ItemUploadResponse>(`${environment.apiUrl}/items/upload`, body);
  }

  // `force` is off by default and every caller sends the unforced request
  // first. The grid tile cannot pass it at all; item detail sends it only after
  // a 409 has come back and the user has been told, by name, what it discards.
  // Defaulting it to true whenever `user_edited` is set would be the obvious
  // shortcut and would mean the 409 is never produced from the UI — which is
  // the whole of acceptance criterion 6. DECISIONS.md 122.
  retag(id: string, force = false): Observable<Item> {
    const url = `${environment.apiUrl}/items/${id}/retag`;
    return this.http.post<Item>(force ? `${url}?force=true` : url, null);
  }

  get(id: string): Observable<Item> {
    return this.http.get<Item>(`${environment.apiUrl}/items/${id}`);
  }

  // PATCH, not PUT: the endpoint merges over the stored row. The body is still
  // every field the form holds (119) — that is the client's choice, not the
  // wire's, and it is what keeps the server's category-clearing branch from
  // firing behind a form that has already cleared those fields on screen.
  update(id: string, changes: ItemUpdate): Observable<Item> {
    return this.http.patch<Item>(`${environment.apiUrl}/items/${id}`, changes);
  }

  // DELETE is a soft archive and answers with the whole row, so the caller can
  // see `is_archived` rather than infer it from a 204. 04-API-SPEC.md, O-1.
  archive(id: string): Observable<Item> {
    return this.http.delete<Item>(`${environment.apiUrl}/items/${id}`);
  }
}

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { environment } from '../../../environments/environment';
import { ItemsApi } from './items.api';

let api: ItemsApi;
let mock: HttpTestingController;

describe('ItemsApi', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(ItemsApi);
    mock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  // The route is declared as get("") under prefix "/items". A trailing slash
  // is a different path and answers with a redirect, which is the kind of
  // thing that works in a browser and fails a CORS preflight.
  it('lists from /items with no trailing slash', () => {
    api.list(200).subscribe();

    const request = mock.expectOne((candidate) => candidate.method === 'GET');
    expect(request.request.url).toBe(`${environment.apiUrl}/items`);
    request.flush({ items: [], total: 0 });
  });

  it('sends the limit it was given as a query parameter', () => {
    api.list(200).subscribe();

    const request = mock.expectOne((candidate) => candidate.method === 'GET');
    expect(request.request.params.get('limit')).toBe('200');
    request.flush({ items: [], total: 0 });
  });

  it('posts a retag to the item and sends no body', () => {
    api.retag('abc').subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/items/abc/retag`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toBeNull();
    request.flush({});
  });
});

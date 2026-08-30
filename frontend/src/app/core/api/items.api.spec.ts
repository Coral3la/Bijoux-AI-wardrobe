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

  // Its own path segment rather than a query parameter on /items, and the
  // server declares it above GET /{item_id} so that `stats` is not read as a
  // UUID. A trailing slash here would redirect for the same reason as above.
  it('reads the stats from /items/stats', () => {
    api.stats().subscribe();

    const request = mock.expectOne((candidate) => candidate.method === 'GET');
    expect(request.request.url).toBe(`${environment.apiUrl}/items/stats`);
    request.flush({
      total: 0,
      by_category: {},
      by_color: {},
      processing: 0,
      failed: 0,
      worn: 0,
      never_worn: 0,
      most_worn: null,
    });
  });

  it('sends the limit it was given as a query parameter', () => {
    api.list(200).subscribe();

    const request = mock.expectOne((candidate) => candidate.method === 'GET');
    expect(request.request.params.get('limit')).toBe('200');
    request.flush({ items: [], total: 0 });
  });

  it('sends the status filter only when one was asked for', () => {
    api.list(200, 'processing').subscribe();

    const filtered = mock.expectOne((candidate) => candidate.method === 'GET');
    expect(filtered.request.params.get('status')).toBe('processing');
    filtered.flush({ items: [], total: 0 });

    api.list(200).subscribe();

    // Both halves, because "processing is on the wire" alone would also pass on
    // a method that always sent it — and an unfiltered list that quietly
    // filtered would show a wardrobe of nothing but the items still tagging.
    const unfiltered = mock.expectOne((candidate) => candidate.method === 'GET');
    expect(unfiltered.request.params.has('status')).toBe(false);
    unfiltered.flush({ items: [], total: 0 });
  });

  it('posts a retag to the item and sends no body', () => {
    api.retag('abc').subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/items/abc/retag`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toBeNull();
    request.flush({});
  });

  // The field name is the route's parameter name, so it is the one thing here
  // that a rename on either side breaks silently: the request still posts, and
  // FastAPI answers 422 for a field it never received.
  it('posts every file under the field name files', () => {
    const a = new File([new Uint8Array(4)], 'a.jpg', { type: 'image/jpeg' });
    const b = new File([new Uint8Array(4)], 'b.jpg', { type: 'image/jpeg' });

    api.upload([a, b]).subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/items/upload`);
    const body = request.request.body as FormData;
    expect((body.getAll('files') as File[]).map((file) => file.name)).toEqual(['a.jpg', 'b.jpg']);
    request.flush({ items: [] });
  });

  it('uploads with POST to /items/upload', () => {
    api.upload([new File([new Uint8Array(4)], 'a.jpg', { type: 'image/jpeg' })]).subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/items/upload`);
    expect(request.request.method).toBe('POST');
    request.flush({ items: [] });
  });

  // Setting Content-Type by hand removes the multipart boundary the browser
  // writes, and the request arrives at the server unparseable.
  it('sets no content type of its own on the upload', () => {
    api.upload([new File([new Uint8Array(4)], 'a.jpg', { type: 'image/jpeg' })]).subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/items/upload`);
    expect(request.request.headers.get('Content-Type')).toBeNull();
    request.flush({ items: [] });
  });

  it('sends a FormData body rather than a json array', () => {
    api.upload([new File([new Uint8Array(4)], 'a.jpg', { type: 'image/jpeg' })]).subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/items/upload`);
    expect(request.request.body).toBeInstanceOf(FormData);
    request.flush({ items: [] });
  });

  // --- task 1.9 -----------------------------------------------------------

  it('reads one item by id', () => {
    api.get('item-1').subscribe();

    mock.expectOne(`${environment.apiUrl}/items/item-1`).flush({});
  });

  it('patches rather than puts, and sends the body as given', () => {
    api.update('item-1', { category: 'top', fit: null }).subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/items/item-1`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ category: 'top', fit: null });
    request.flush({});
  });

  // An explicit null is a supplied value on this endpoint — the server merges
  // with exclude_unset — so it has to survive serialisation rather than being
  // dropped the way an undefined would be.
  it('keeps an explicit null in the body', () => {
    api.update('item-1', { color_primary: null }).subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/items/item-1`);
    expect(JSON.stringify(request.request.body)).toBe('{"color_primary":null}');
    request.flush({});
  });

  it('deletes by id', () => {
    api.archive('item-1').subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/items/item-1`);
    expect(request.request.method).toBe('DELETE');
    request.flush({});
  });

  // The default matters more than the parameter: every caller that does not
  // ask for force must not send it, or the 409 is never produced. 122.
  it('sends no force parameter unless asked', () => {
    api.retag('item-1').subscribe();

    mock.expectOne(`${environment.apiUrl}/items/item-1/retag`).flush({});
  });

  it('sends force=true when asked', () => {
    api.retag('item-1', true).subscribe();

    mock.expectOne(`${environment.apiUrl}/items/item-1/retag?force=true`).flush({});
  });
});

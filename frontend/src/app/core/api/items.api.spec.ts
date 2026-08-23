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
});

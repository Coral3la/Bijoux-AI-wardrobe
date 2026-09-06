import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { environment } from '../../../environments/environment';
import { SetsApi } from './sets.api';

let api: SetsApi;
let mock: HttpTestingController;

describe('SetsApi', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(SetsApi);
    mock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  // The route is declared as post("") under prefix "/sets". A trailing slash is
  // a different path and answers with a redirect, which works in a browser and
  // fails a CORS preflight — items.api.spec.ts asserts the same thing one
  // resource over, and it is asserted here rather than inherited from there.
  it('declares a set at /sets with no trailing slash', () => {
    api.create({ item_ids: ['a', 'b'] }).subscribe();

    const request = mock.expectOne((candidate) => candidate.method === 'POST');
    expect(request.request.url).toBe(`${environment.apiUrl}/sets`);
    request.flush({});
  });

  // The body goes out as the caller built it. The request schema forbids an
  // unknown key rather than dropping it, so a field added here for convenience
  // would answer 422 instead of being ignored.
  it('sends the ids as item_ids and nothing else', () => {
    api.create({ item_ids: ['a', 'b'] }).subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/sets`);
    expect(request.request.body).toEqual({ item_ids: ['a', 'b'] });
    request.flush({});
  });

  // No control writes a name, but the field is on the wire and the shape has to
  // survive being given one: `name` is a string beside the ids, not a second
  // request and not a query parameter.
  it('carries a name when it is given one', () => {
    api.create({ name: 'the linen suit', item_ids: ['a', 'b'] }).subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/sets`);
    expect(request.request.body).toEqual({ name: 'the linen suit', item_ids: ['a', 'b'] });
    request.flush({});
  });

  it('reads one set by id', () => {
    api.get('set-1').subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/sets/set-1`);
    expect(request.request.method).toBe('GET');
    request.flush({});
  });

  it('deletes a whole set by id', () => {
    api.remove('set-1').subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/sets/set-1`);
    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });
  });

  it('adds one garment to the set in the path, by id in the body', () => {
    api.addItem('set-1', { item_id: 'item-9' }).subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/sets/set-1/items`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ item_id: 'item-9' });
    request.flush({});
  });

  // Both ids are path segments here, where the add puts one of them in a body:
  // a member of a set is addressable, and 04-API-SPEC.md answers 404 for an id
  // that is not one. Sending item_id in a body would ask a different question.
  it('removes one garment with both ids in the path', () => {
    api.removeItem('set-1', 'item-9').subscribe();

    const request = mock.expectOne(`${environment.apiUrl}/sets/set-1/items/item-9`);
    expect(request.request.method).toBe('DELETE');
    expect(request.request.body).toBeNull();
    request.flush({});
  });

  // The pair below is the contract this method exists to absorb. A 200 carries
  // the set that survived; a 204 carries nothing, and the caller has to be able
  // to tell them apart from the value alone — which is the whole reason the
  // return type is nullable rather than ItemSet.
  it('answers with the surviving set when the removal leaves two members', () => {
    const answers: (unknown | null)[] = [];
    api.removeItem('set-1', 'item-9').subscribe((set) => answers.push(set));

    mock
      .expectOne(`${environment.apiUrl}/sets/set-1/items/item-9`)
      .flush({ id: 'set-1', name: null, items: [], created_at: '2026-09-06T09:00:00Z' });

    expect(answers).toHaveLength(1);
    expect(answers[0]).toMatchObject({ id: 'set-1' });
  });

  it('answers null when the removal dissolved the set', () => {
    const answers: (unknown | null)[] = [];
    api.removeItem('set-1', 'item-9').subscribe((set) => answers.push(set));

    mock
      .expectOne(`${environment.apiUrl}/sets/set-1/items/item-9`)
      .flush(null, { status: 204, statusText: 'No Content' });

    expect(answers).toEqual([null]);
  });
});

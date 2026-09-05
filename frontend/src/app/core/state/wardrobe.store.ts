import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { Observable, Subscription, tap } from 'rxjs';

import { ItemsApi } from '../api/items.api';
import { Category, Color } from '../../shared/models/enums';
import { Item, ItemUpdate } from '../../shared/models/item.model';

// One page, always. 04-API-SPEC.md caps `limit` at 200 and nothing in the plan
// sends `offset`, because task 1.8 filters client-side over whatever is loaded
// — so the explicit limit is what keeps the filter bar honest. Above 200 items
// the grid shows the newest 200 while the header still states the true total.
export const WARDROBE_PAGE_SIZE = 200;

// DECISIONS.md 007, and 01-ARCHITECTURE.md and 05-FRONTEND-SPEC.md both give
// the same two numbers. They are pinned to hand-transcribed literals in
// wardrobe.store.spec.ts rather than asserted against themselves: at 1.6 every
// expectation about MAX_UPLOAD_BYTES was written in terms of it, so mutating
// the constant moved the goalposts and the whole suite stayed green (101).
export const POLL_INTERVAL_MS = 2000;
export const POLL_DEADLINE_MS = 180_000;

interface ApiErrorBody {
  readonly code?: string;
}

// The guard C6's sketch in 05-FRONTEND-SPEC.md lacks, and it is the run itself
// rather than a boolean beside it: a run cannot exist without the timer and
// request it owns, so "are we polling" and "is anything scheduled" cannot drift
// apart. One place creates it, one place destroys it. DECISIONS.md 103.
//
// `seen` is every id this run has ever waited for, and it is what pushes the
// deadline out when a second batch arrives mid-run (DECISIONS.md 108). It is
// deliberately not the set the reload decision compares against: that one is
// the ids awaited at the moment a response lands, where this one is cumulative.
interface PollRun {
  deadline: number;
  readonly seen: Set<string>;
  timer: ReturnType<typeof setTimeout> | null;
  request: Subscription | null;
}

// A file the user picked, on screen before the request answers. Deliberately
// not an Item and deliberately not in item.model.ts: that file mirrors the
// wire field for field (DECISIONS.md 059) and none of this ever goes near it.
// It lives here rather than beside PendingStrip because core/ imports nothing
// from features/ anywhere in this project. DECISIONS.md 097.
export interface PendingUpload {
  readonly key: string;
  readonly url: string;
  readonly name: string;
}

// The four tag fields 1.8 gives a control, keyed by 04-API-SPEC.md's own query
// parameter names so the address bar, this object and the endpoint all call
// them one thing — 059's rule applied to a shape that never goes on the wire.
// Nothing here is ever sent: the filter runs over the loaded collection
// (05-FRONTEND-SPEC.md), which is why GET /items still receives the two
// parameters the store already sends and no more. DECISIONS.md 110.
export interface ItemFilters {
  readonly category?: Category;
  readonly color_primary?: Color;
  readonly formality_min?: number;
  readonly formality_max?: number;
  readonly warmth_min?: number;
  readonly warmth_max?: number;
  // `true` rather than `boolean`, so an off filter cannot be spelled as
  // `never_worn: false` — the absent key is the only off state, which is what
  // every other dimension here means by omission and what normalise below
  // relies on. It is also what keeps `?never_worn=false` out of the address
  // bar. DECISIONS.md 228.
  readonly never_worn?: true;
}

// Transcribed by hand from 02-DATA-MODEL.md, where `formality` and `warmth` are
// both "integer 1-5", and where migration 0001 spells the same bound as a
// CHECK. Literals rather than anything derived: a constant that reads its own
// value from the code beneath it defends nothing. DECISIONS.md 101.
export const SCALE_MIN = 1;
export const SCALE_MAX = 5;

// A null value is an unknown, not a non-match, so it passes that field's
// filter. Per field rather than per row, because the two differ on a row that
// is a week away: `PATCH {"color_primary": null}` is a 200 that clears one
// column (exclude_unset makes an explicit null a supplied one), so a `ready`
// item can carry a null beside four real tags — and hiding it under "black"
// asserts something nobody has said. DECISIONS.md 109.
function admits<T>(value: T | null, wanted: T | undefined): boolean {
  return wanted === undefined || value === null || value === wanted;
}

function admitsRange(
  value: number | null,
  min: number | undefined,
  max: number | undefined,
): boolean {
  if (value === null) {
    return true;
  }
  return (min === undefined || value >= min) && (max === undefined || value <= max);
}

// `status` is deliberately absent from every clause but the last, and the
// stopped-waiting tile staying visible under the four tag filters *falls out
// of* that rather than being provided by it: its tags really are null. Anyone
// simplifying those four to read `status` should know that is what they are
// removing.
//
// `never_worn` is the exception and it is not a tag filter. `wear_count` is
// NOT NULL DEFAULT 0, so there is no unknown for 109's rule to protect, and a
// processing row's zero means nothing has happened yet rather than that nobody
// wore it — which is exactly the row the panel's `ready`-scoped count leaves
// out. The gate is written here rather than factored into a helper: the next
// status-aware filter has to make this argument again rather than inherit it.
// DECISIONS.md 109, 228.
export function applyFilters(items: readonly Item[], filters: ItemFilters): readonly Item[] {
  return items.filter(
    (candidate) =>
      admits(candidate.category, filters.category) &&
      admits(candidate.color_primary, filters.color_primary) &&
      admitsRange(candidate.formality, filters.formality_min, filters.formality_max) &&
      admitsRange(candidate.warmth, filters.warmth_min, filters.warmth_max) &&
      (filters.never_worn === undefined ||
        (candidate.status === 'ready' && candidate.wear_count === 0)),
  );
}

// The gate's range input is not a browser's — jsdom does not snap to `step`,
// and an unbound range reads 50 where a browser reads 3 — so the rounding is
// ours, at the one door into the filter state, rather than trusted to the
// control. 06-TESTING-STRATEGY.md carries the measurement. DECISIONS.md 115.
function scalePoint(value: number | undefined): number | undefined {
  if (value === undefined || Number.isNaN(value)) {
    return undefined;
  }
  return Math.min(SCALE_MAX, Math.max(SCALE_MIN, Math.round(value)));
}

// The pair is the interval and the handles carry no order of their own, so a
// max dragged below a min is a narrower range rather than an empty result.
function scaleRange(
  min: number | undefined,
  max: number | undefined,
): readonly [number | undefined, number | undefined] {
  const low = scalePoint(min);
  const high = scalePoint(max);
  return low !== undefined && high !== undefined && low > high ? [high, low] : [low, high];
}

// Inactive keys are omitted rather than carried as undefined, because "is a
// filter on" is read off this object's key count on the wardrobe page and
// written from its entries into the query string.
function normalise(filters: ItemFilters): ItemFilters {
  const [formalityMin, formalityMax] = scaleRange(filters.formality_min, filters.formality_max);
  const [warmthMin, warmthMax] = scaleRange(filters.warmth_min, filters.warmth_max);

  return {
    ...(filters.category !== undefined && { category: filters.category }),
    ...(filters.color_primary !== undefined && { color_primary: filters.color_primary }),
    ...(formalityMin !== undefined && { formality_min: formalityMin }),
    ...(formalityMax !== undefined && { formality_max: formalityMax }),
    ...(warmthMin !== undefined && { warmth_min: warmthMin }),
    ...(warmthMax !== undefined && { warmth_max: warmthMax }),
    ...(filters.never_worn !== undefined && { never_worn: filters.never_worn }),
  };
}

// Same rule as retagErrorKey below: branch on the documented code, never on
// the status. 04-API-SPEC.md gives this endpoint four failures and they are
// four different things to say. DECISIONS.md 092, 099.
const UPLOAD_ERROR_KEYS: Readonly<Record<string, string>> = {
  unsupported_file_type: 'wardrobe.upload.error.unsupportedType',
  file_too_large: 'wardrobe.upload.error.fileTooLarge',
  upload_failed: 'wardrobe.upload.error.uploadFailed',
  validation_error: 'wardrobe.upload.error.validation',
};

function uploadErrorKey(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const code = (error.error as ApiErrorBody | null)?.code;
    // The server names the offending file inside `detail` and this drops it:
    // CONVENTIONS.md forbids rendering a raw error, so a 415 on one file out
    // of twelve cannot say which. Recorded rather than solved, DECISIONS.md 099.
    if (code !== undefined && code in UPLOAD_ERROR_KEYS) {
      return UPLOAD_ERROR_KEYS[code];
    }
  }
  return 'wardrobe.upload.error.general';
}

// Branches on the documented code rather than on the status. `item_edited` was
// named at task 1.4 to give the frontend exactly this, and 04-API-SPEC.md
// records that a code with no producer invites a branch that can never be
// taken — so this is the branch that makes the code real.
function retagErrorKey(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const body = error.error as ApiErrorBody | null;
    if (body?.code === 'item_edited') {
      return 'wardrobe.error.retagEdited';
    }
  }
  return 'wardrobe.error.retag';
}

@Injectable({ providedIn: 'root' })
export class WardrobeStore {
  private readonly api = inject(ItemsApi);

  private readonly itemsSignal = signal<readonly Item[]>([]);
  private readonly totalSignal = signal(0);
  private readonly loadingSignal = signal(false);
  private readonly loadErrorSignal = signal<string | null>(null);
  private readonly retryingSignal = signal<ReadonlySet<string>>(new Set());
  private readonly retagErrorsSignal = signal<ReadonlyMap<string, string>>(new Map());
  private readonly pendingSignal = signal<readonly PendingUpload[]>([]);
  private readonly uploadingSignal = signal(false);
  private readonly uploadErrorSignal = signal<string | null>(null);
  private readonly stoppedWaitingSignal = signal<ReadonlySet<string>>(new Set());
  private readonly filtersSignal = signal<ItemFilters>({});

  private pendingKeySeq = 0;
  private run: PollRun | null = null;

  readonly items = this.itemsSignal.asReadonly();
  readonly total = this.totalSignal.asReadonly();
  readonly isLoading = this.loadingSignal.asReadonly();
  readonly loadError = this.loadErrorSignal.asReadonly();
  readonly retrying = this.retryingSignal.asReadonly();
  readonly retagErrors = this.retagErrorsSignal.asReadonly();
  readonly pending = this.pendingSignal.asReadonly();
  readonly isUploading = this.uploadingSignal.asReadonly();
  readonly uploadError = this.uploadErrorSignal.asReadonly();
  readonly stoppedWaiting = this.stoppedWaitingSignal.asReadonly();
  readonly filters = this.filtersSignal.asReadonly();

  readonly isEmpty = computed(() => this.itemsSignal().length === 0);
  readonly visible = computed(() => applyFilters(this.itemsSignal(), this.filtersSignal()));
  readonly processing = computed(() =>
    this.itemsSignal().filter((item) => item.status === 'processing'),
  );

  // The subtraction is what keeps the loop and the screen saying the same
  // thing. A `processing` row the loop has given up on is one the user has
  // been told we stopped waiting for, and an effect keyed on `processing` goes
  // on waiting for it — silently, for another three minutes, from the next
  // time anything else puts a row into the collection. DECISIONS.md 105.
  readonly awaitingTags = computed(() =>
    this.processing().filter((item) => !this.stoppedWaitingSignal().has(item.id)),
  );

  constructor() {
    effect(() => {
      const awaiting = this.awaitingTags();
      if (awaiting.length === 0) {
        this.stopPolling();
        return;
      }
      if (this.run === null) {
        this.startPolling(awaiting);
        return;
      }
      this.extendDeadline(this.run, awaiting);
    });
  }

  // The one door into the filter state, so the coercion has one place to live.
  // The URL is not written here: this store is providedIn: 'root' and outlives
  // the page, so a store that wrote the address bar would write it from behind
  // whatever screen came next — 107's failure, one collection over. The page
  // owns the URL and calls this. DECISIONS.md 110.
  setFilters(filters: ItemFilters): void {
    this.filtersSignal.set(normalise(filters));
  }

  load(): void {
    this.loadingSignal.set(true);
    this.loadErrorSignal.set(null);

    this.api.list(WARDROBE_PAGE_SIZE).subscribe({
      next: (response) => {
        this.itemsSignal.set(response.items);
        this.totalSignal.set(response.total);
        // An explicit fresh start, so anything the last visit gave up on is
        // waited for again. The poll's own reload deliberately does not do
        // this: clearing mid-run would return a given-up id to `awaitingTags`
        // with the deadline already behind it, and the run would give up and
        // clear and give up again.
        this.stoppedWaitingSignal.set(new Set());
        this.loadingSignal.set(false);
      },
      error: () => {
        this.loadErrorSignal.set('wardrobe.error.load');
        this.loadingSignal.set(false);
      },
    });
  }

  // One selection is one request, so the in-flight mark is a boolean where
  // retag's is a Set: several retags run independently, an upload batch does
  // not. The guard mirrors retag's for the same reason — the camera leaves the
  // sheet open, so a second capture can arrive while the first is in flight.
  upload(files: readonly File[]): void {
    if (files.length === 0 || this.uploadingSignal()) {
      return;
    }
    this.uploadingSignal.set(true);
    this.uploadErrorSignal.set(null);
    this.pendingSignal.set(
      files.map((file) => ({
        key: `pending-${this.pendingKeySeq++}`,
        url: URL.createObjectURL(file),
        name: file.name,
      })),
    );

    this.api.upload(files).subscribe({
      next: (response) => {
        // Prepended, because GET /items orders created_at DESC and these are
        // the newest rows: appending would drop a fresh upload below a hundred
        // older items, which reads as the upload having done nothing.
        this.itemsSignal.update((items) => [...response.items, ...items]);
        // The 202 carries no `total`, so the header's count is ours to move.
        // Without this it understates by the size of every batch. 094, 100.
        this.totalSignal.update((total) => total + response.items.length);
        this.finishUpload();
      },
      error: (error: unknown) => {
        this.uploadErrorSignal.set(uploadErrorKey(error));
        this.finishUpload();
      },
    });
  }

  dismissUploadError(): void {
    this.uploadErrorSignal.set(null);
  }

  // `force` is the caller's and defaults off. Item detail sends the unforced
  // request first and only passes true once the 409 has been shown and
  // answered; the grid tile has no way to pass it. DECISIONS.md 122.
  retag(id: string, force = false): void {
    if (this.retryingSignal().has(id)) {
      return;
    }
    this.setRetrying(id, true);
    this.setRetagError(id, null);

    this.api.retag(id, force).subscribe({
      next: (item) => {
        this.replace(item);
        // Without this the retry on a given-up tile does nothing visible: the
        // 202 puts the row back to `processing`, `awaitingTags` still excludes
        // it, and no run starts. Cleared on success rather than on click, so a
        // refused retag leaves the tile saying what it said before.
        this.resumeWaiting(id);
        this.setRetrying(id, false);
      },
      error: (error: unknown) => {
        this.setRetagError(id, retagErrorKey(error));
        this.setRetrying(id, false);
      },
    });
  }

  // Called from the wardrobe page's DestroyRef. This service is
  // providedIn: 'root' and outlives the page, so a run nobody stops keeps
  // polling behind whatever screen comes next. DECISIONS.md 107.
  stopPolling(): void {
    const run = this.run;
    if (run === null) {
      return;
    }
    if (run.timer !== null) {
      clearTimeout(run.timer);
    }
    run.request?.unsubscribe();
    this.run = null;
  }

  private startPolling(awaiting: readonly Item[]): void {
    this.run = {
      deadline: Date.now() + POLL_DEADLINE_MS,
      seen: new Set(awaiting.map((item) => item.id)),
      timer: null,
      request: null,
    };
    this.schedule(this.run);
  }

  // A second batch arriving mid-run gets its own three minutes rather than the
  // remainder of the first one's. 098 keeps the sheet open after a camera
  // capture precisely so the next garment can be shot immediately, so
  // back-to-back batches are the designed path — and two full batches tag
  // serially for longer than one deadline covers. DECISIONS.md 108.
  private extendDeadline(run: PollRun, awaiting: readonly Item[]): void {
    let arrived = false;
    for (const item of awaiting) {
      if (!run.seen.has(item.id)) {
        run.seen.add(item.id);
        arrived = true;
      }
    }
    if (arrived) {
      run.deadline = Date.now() + POLL_DEADLINE_MS;
    }
  }

  private schedule(run: PollRun): void {
    run.timer = setTimeout(() => {
      run.timer = null;
      this.poll(run);
    }, POLL_INTERVAL_MS);
  }

  // Request one of two. This one answers "which of these is still tagging",
  // and it can never answer "what did the others become" — a body filtered to
  // status=processing carries no finished row. DECISIONS.md 102.
  private poll(run: PollRun): void {
    const awaited = new Set(this.awaitingTags().map((item) => item.id));

    run.request = this.api.list(WARDROBE_PAGE_SIZE, 'processing').subscribe({
      next: (response) => {
        run.request = null;
        // Compared as ids rather than as a count. A second batch landing while
        // the first is finishing can leave the count unchanged with the
        // membership completely different, and the reload would never fire.
        const stillTagging = new Set(response.items.map((item) => item.id));
        if ([...awaited].some((id) => !stillTagging.has(id))) {
          this.reload(run);
          return;
        }
        this.rearm(run);
      },
      // Q5: a dropped connection or a cold start on Render is not news. The
      // deadline is what bounds a poll that never succeeds, and a red banner
      // over an otherwise healthy grid is the worse answer. DECISIONS.md 106.
      error: () => {
        run.request = null;
        this.rearm(run);
      },
    });
  }

  // Request two of two, and the only one that ever puts a tag on a tile. It is
  // not load(): that sets isLoading, and the page swaps the entire grid for a
  // loading line when it is true — so reusing it would blank the wardrobe
  // every time a single item finished tagging.
  private reload(run: PollRun): void {
    run.request = this.api.list(WARDROBE_PAGE_SIZE).subscribe({
      next: (response) => {
        run.request = null;
        this.itemsSignal.set(response.items);
        this.totalSignal.set(response.total);
        this.rearm(run);
      },
      error: () => {
        run.request = null;
        this.rearm(run);
      },
    });
  }

  // Re-armed after the whole step settles, reload included, rather than run
  // from a fixed interval: one poll in flight at a time is then a property of
  // the loop rather than a hope about how fast the server answers.
  // DECISIONS.md 104.
  private rearm(run: PollRun): void {
    if (Date.now() >= run.deadline) {
      this.giveUp();
      return;
    }
    this.schedule(run);
  }

  // Nothing is written into `items` — a client-side 'failed' would be a row no
  // server issued, on the one model whose contract is that everything in it
  // came off the wire, and 1.8 filters that collection while 1.9 edits from
  // it. 097 stays intact; this is a second collection beside it, the same
  // shape as `retrying` and `retagErrors`. DECISIONS.md 105.
  private giveUp(): void {
    const abandoned = this.awaitingTags().map((item) => item.id);
    this.stoppedWaitingSignal.update((current) => new Set([...current, ...abandoned]));
    this.stopPolling();
  }

  private resumeWaiting(id: string): void {
    this.stoppedWaitingSignal.update((current) => {
      const next = new Set(current);
      next.delete(id);
      return next;
    });
  }

  // The previews go on both paths, including the failure: a rejected batch
  // uploads nothing, and leaving its files on screen would show the user
  // photographs that are not arriving. Revoking is what releases the bytes the
  // browser is holding for each one; no test can see it (jsdom implements
  // neither half of the object-URL API) and it is named in AUDITS.md O-14.
  private finishUpload(): void {
    for (const entry of this.pendingSignal()) {
      URL.revokeObjectURL(entry.url);
    }
    this.pendingSignal.set([]);
    this.uploadingSignal.set(false);
  }

  // Replaces the row rather than merging fields into it: every write endpoint
  // answers with the whole item for that reason (DECISIONS.md 034, 050).
  private replace(item: Item): void {
    this.itemsSignal.update((items) =>
      items.map((current) => (current.id === item.id ? item : current)),
    );
  }

  private setRetrying(id: string, retrying: boolean): void {
    this.retryingSignal.update((current) => {
      const next = new Set(current);
      if (retrying) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }

  // Waiting, never optimistic. An edited row written locally would be an `Item`
  // no server issued, on the one collection whose contract is that everything
  // in it came off the wire — and it is worse than the synthetic row 097
  // refused, because a preview is visibly not a row where a guessed edit is
  // indistinguishable from a real one. The server also decides things this
  // client cannot: whether five dependent fields were cleared, and whether the
  // row has just stopped being `failed` (116). DECISIONS.md 120.
  edit(id: string, changes: ItemUpdate): Observable<Item> {
    return this.api.update(id, changes).pipe(
      tap((item) => {
        this.replace(item);
        // The row the user has just corrected by hand is not the row that
        // failed to retag, so the message about that failure goes. Cleared on
        // success only: a rejected save leaves the tile saying what it said.
        this.setRetagError(id, null);
      }),
    );
  }

  // The first operation in this project that removes a row from `items()`
  // without a load(), which makes it the first test of the leak 093 accepted:
  // both id-keyed collections are dropped here rather than left to outlive
  // their row. `total` is the caller's problem, not this method's — see
  // `forget`. DECISIONS.md 121.
  archive(id: string): Observable<Item> {
    return this.api.archive(id).pipe(tap(() => this.forget(id)));
  }

  // Split out from `archive` because only the caller knows whether this row was
  // ever counted. A row fetched by id on a deep link never entered `items()`
  // and was never in `total`, so decrementing for it would understate the
  // wardrobe by one until the next load. DECISIONS.md 121.
  forget(id: string): void {
    const present = this.itemsSignal().some((item) => item.id === id);
    this.itemsSignal.update((items) => items.filter((item) => item.id !== id));
    if (present) {
      this.totalSignal.update((total) => Math.max(0, total - 1));
    }
    this.setRetagError(id, null);
    this.resumeWaiting(id);
  }

  private setRetagError(id: string, key: string | null): void {
    this.retagErrorsSignal.update((current) => {
      const next = new Map(current);
      if (key === null) {
        next.delete(id);
      } else {
        next.set(id, key);
      }
      return next;
    });
  }
}

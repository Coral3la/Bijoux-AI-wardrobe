import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';

import { ItemsApi } from '../api/items.api';
import { Item } from '../../shared/models/item.model';

// One page, always. 04-API-SPEC.md caps `limit` at 200 and nothing in the plan
// sends `offset`, because task 1.8 filters client-side over whatever is loaded
// — so the explicit limit is what keeps the filter bar honest. Above 200 items
// the grid shows the newest 200 while the header still states the true total.
export const WARDROBE_PAGE_SIZE = 200;

interface ApiErrorBody {
  readonly code?: string;
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

  private pendingKeySeq = 0;

  readonly items = this.itemsSignal.asReadonly();
  readonly total = this.totalSignal.asReadonly();
  readonly isLoading = this.loadingSignal.asReadonly();
  readonly loadError = this.loadErrorSignal.asReadonly();
  readonly retrying = this.retryingSignal.asReadonly();
  readonly retagErrors = this.retagErrorsSignal.asReadonly();
  readonly pending = this.pendingSignal.asReadonly();
  readonly isUploading = this.uploadingSignal.asReadonly();
  readonly uploadError = this.uploadErrorSignal.asReadonly();

  readonly isEmpty = computed(() => this.itemsSignal().length === 0);
  readonly processing = computed(() =>
    this.itemsSignal().filter((item) => item.status === 'processing'),
  );

  load(): void {
    this.loadingSignal.set(true);
    this.loadErrorSignal.set(null);

    this.api.list(WARDROBE_PAGE_SIZE).subscribe({
      next: (response) => {
        this.itemsSignal.set(response.items);
        this.totalSignal.set(response.total);
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

  retag(id: string): void {
    if (this.retryingSignal().has(id)) {
      return;
    }
    this.setRetrying(id, true);
    this.setRetagError(id, null);

    this.api.retag(id).subscribe({
      next: (item) => {
        this.replace(item);
        this.setRetrying(id, false);
      },
      error: (error: unknown) => {
        this.setRetagError(id, retagErrorKey(error));
        this.setRetrying(id, false);
      },
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

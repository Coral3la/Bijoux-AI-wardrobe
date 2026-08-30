import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';

import { LooksApi } from '../api/looks.api';
import { Look, LookUpdate } from '../../shared/models/look.model';

interface ApiErrorBody {
  readonly code?: string;
}

// Separate from StylistStore, which is about *making* a look: this one is
// about looks that already exist. The two are used together on one screen —
// the stylist page renders a card from one and rates it through the other —
// and that is the clearest evidence they are different jobs rather than one
// store split in half. DECISIONS.md 182.
const UPDATE_ERROR_KEYS: Readonly<Record<string, string>> = {
  // The look was on screen when the button was tapped and is not there now.
  // Its own message rather than the general one, because it is the only
  // failure here a user can do anything about: reload the list.
  not_found: 'looks.error.notFound',
  validation_error: 'looks.error.validation',
};

function updateErrorKey(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const code = (error.error as ApiErrorBody | null)?.code;
    if (code !== undefined && code in UPDATE_ERROR_KEYS) {
      return UPDATE_ERROR_KEYS[code];
    }
  }
  return 'looks.error.general';
}

@Injectable({ providedIn: 'root' })
export class LooksStore {
  private readonly api = inject(LooksApi);

  private readonly looksSignal = signal<readonly Look[]>([]);
  private readonly loadingSignal = signal(false);
  private readonly errorSignal = signal<string | null>(null);
  // The id being written, not a boolean: the saved-looks screen renders a
  // control per row, and a flag would say a write is running without saying
  // which row is waiting on it. Same shape as StylistStore.swappingItemId.
  private readonly updatingSignal = signal<string | null>(null);
  // The newest version of a look this store knows about — optimistic the
  // moment a button is pressed, then the server's own answer. The stylist
  // screen holds its look in StylistStore and cannot be handed a new one, so
  // it matches this by id and prefers it.
  private readonly updatedSignal = signal<Look | null>(null);

  readonly looks = this.looksSignal.asReadonly();
  readonly isLoading = this.loadingSignal.asReadonly();
  readonly error = this.errorSignal.asReadonly();
  readonly updatingId = this.updatingSignal.asReadonly();
  readonly updated = this.updatedSignal.asReadonly();

  // This service is providedIn: 'root' and outlives every screen, so without
  // this the previous visit's list is on screen before the request for this
  // one answers. StylistStore.reset exists for the same reason.
  reset(): void {
    this.looksSignal.set([]);
    this.loadingSignal.set(false);
    this.errorSignal.set(null);
    this.updatingSignal.set(null);
    this.updatedSignal.set(null);
  }

  // For the stylist page, which shows this store's error and StylistStore's in
  // one line: without it a failed save stays on screen under a swap that has
  // since failed for its own reason, and the line has to pick between two live
  // errors on no principle. StylistStore clears its own at the start of every
  // request; this is the same courtesy from the outside, because the swap that
  // supersedes this error is not this store's to observe.
  clearError(): void {
    this.errorSignal.set(null);
  }

  loadSaved(): void {
    this.loadingSignal.set(true);
    this.errorSignal.set(null);

    this.api.listSaved().subscribe({
      next: (response) => {
        this.looksSignal.set(response.looks);
        this.loadingSignal.set(false);
      },
      error: () => {
        this.errorSignal.set('looks.error.load');
        this.loadingSignal.set(false);
      },
    });
  }

  // Optimistic, for both the heart and the thumbs. `STAGE-3` asks for that at
  // 3.3 and 3.2 shipped the heart without it — one PATCH path with two
  // behaviours would be a difference no reader could reconstruct, so this
  // supersedes DECISIONS.md 182 on that point (183). The cost is honest: on a
  // flaky network a control flips and then flips back.
  //
  // It takes the whole look rather than an id, which is what makes the
  // optimistic render possible at all — the stylist screen's look lives in
  // StylistStore and is not in `looks`, so there is nothing here to merge into.
  update(look: Look, changes: LookUpdate): void {
    if (this.updatingSignal() !== null) {
      return;
    }

    const previousUpdated = this.updatedSignal();
    const previousLooks = this.looksSignal();

    this.updatingSignal.set(look.id);
    this.errorSignal.set(null);
    this.write({ ...look, ...changes });

    this.api.update(look.id, changes).subscribe({
      next: (saved) => {
        // The server's answer replaces the guess even though they normally
        // agree: it is the only version that reflects what the row holds, and
        // a PATCH that clamped or ignored something would otherwise never show.
        this.write(saved);
        this.updatingSignal.set(null);
      },
      error: (error: unknown) => {
        // Restored exactly, not recomputed. `updated` may have been null —
        // the first tap on the stylist screen — and setting it to the
        // pre-tap look instead would leave a value behind that was never there.
        this.updatedSignal.set(previousUpdated);
        this.looksSignal.set(previousLooks);
        this.errorSignal.set(updateErrorKey(error));
        this.updatingSignal.set(null);
      },
    });
  }

  private write(look: Look): void {
    this.updatedSignal.set(look);
    // Replaced where it stands rather than removed when it is unsaved. The
    // list was fetched with is_saved=true, so an unsaved row no longer matches
    // the query it came from — but taking it away under the finger that
    // unsaved it makes the mistake uncorrectable, where leaving it with an
    // empty heart makes it one tap back. It is gone on the next load, which is
    // the moment the user is no longer looking at it.
    this.looksSignal.update((looks) =>
      looks.map((existing) => (existing.id === look.id ? look : existing)),
    );
  }
}

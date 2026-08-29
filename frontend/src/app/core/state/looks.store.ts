import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';

import { LooksApi } from '../api/looks.api';
import { Look, LookUpdate } from '../../shared/models/look.model';

interface ApiErrorBody {
  readonly code?: string;
}

// Separate from StylistStore, which is about *making* a look: this one is
// about looks that already exist. The two are used together on one screen —
// the stylist page renders a card from one and hearts it through the other —
// and that is the clearest evidence they are different jobs rather than one
// store split in half. DECISIONS.md 182.
const UPDATE_ERROR_KEYS: Readonly<Record<string, string>> = {
  // The look was on screen when the heart was tapped and is not there now.
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
  // heart per row, and a flag would say a save is running without saying which
  // row is waiting on it. Same shape as StylistStore.swappingItemId.
  private readonly updatingSignal = signal<string | null>(null);
  // The last look this store successfully wrote. The stylist screen holds its
  // look in StylistStore and cannot be handed a new one, so it matches this by
  // id and prefers it — which keeps the server's own answer on screen rather
  // than a locally toggled copy of it.
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

  // Not optimistic, deliberately. `STAGE-3` asks for an optimistic update at
  // 3.3 and does not ask for one here, and the response *is* the look — so
  // rendering it is exact where a locally toggled copy is a guess that happens
  // to be right. The wait is one request on a button the user has just pressed.
  update(id: string, changes: LookUpdate): void {
    if (this.updatingSignal() !== null) {
      return;
    }
    this.updatingSignal.set(id);
    this.errorSignal.set(null);

    this.api.update(id, changes).subscribe({
      next: (look) => {
        this.updatedSignal.set(look);
        // Replaced where it stands rather than removed when it is unsaved.
        // The list was fetched with is_saved=true, so an unsaved row no longer
        // matches the query it came from — but taking it away under the finger
        // that unsaved it makes the mistake uncorrectable, where leaving it
        // with an empty heart makes it one tap back. It is gone on the next
        // load, which is the moment the user is no longer looking at it.
        this.looksSignal.update((looks) =>
          looks.map((existing) => (existing.id === look.id ? look : existing)),
        );
        this.updatingSignal.set(null);
      },
      error: (error: unknown) => {
        this.errorSignal.set(updateErrorKey(error));
        this.updatingSignal.set(null);
      },
    });
  }
}

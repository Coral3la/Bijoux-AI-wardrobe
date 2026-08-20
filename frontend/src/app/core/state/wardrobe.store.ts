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

  readonly items = this.itemsSignal.asReadonly();
  readonly total = this.totalSignal.asReadonly();
  readonly isLoading = this.loadingSignal.asReadonly();
  readonly loadError = this.loadErrorSignal.asReadonly();
  readonly retrying = this.retryingSignal.asReadonly();
  readonly retagErrors = this.retagErrorsSignal.asReadonly();

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

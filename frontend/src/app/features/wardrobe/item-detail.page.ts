import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ItemsApi } from '../../core/api/items.api';
import { SetsApi } from '../../core/api/sets.api';
import { I18nService } from '../../core/i18n/i18n.service';
import { WardrobeStore } from '../../core/state/wardrobe.store';
import { ItemSet } from '../../shared/models/item-set.model';
import { Item, ItemUpdate } from '../../shared/models/item.model';
import { CloudinaryUrlPipe } from '../../shared/pipes/cloudinary-url.pipe';
import { Button } from '../../shared/ui/button';
import { SetPicker } from './set-picker';
import { TagEditor } from './tag-editor';

// Branches on the documented code rather than on the status, which is the rule
// wardrobe.store.ts states for the upload and the retag: 04-API-SPEC.md gives
// this pair of endpoints two 422s and they are two different things to say, and
// only one of them has an obvious cause the user can see. `set_member_taken` is
// reachable only from a stale collection — the picker excludes a garment that
// already carries a set_id — which is exactly why it needs a sentence: a
// wardrobe loaded before somebody else's tab declared a set is the case.
const PICK_ERROR_KEYS: Readonly<Record<string, string>> = {
  set_item_unavailable: 'item.set.error.unavailable',
  set_member_taken: 'item.set.error.taken',
};

function pickErrorKey(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const code = (error.error as { code?: string } | null)?.code;
    if (code !== undefined && code in PICK_ERROR_KEYS) {
      return PICK_ERROR_KEYS[code];
    }
  }
  return 'item.set.error.add';
}

@Component({
  selector: 'app-item-detail-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, CloudinaryUrlPipe, RouterLink, SetPicker, TagEditor],
  template: `
    <main class="mx-auto flex w-full max-w-3xl flex-col gap-region px-6 py-region">
      <a
        routerLink="/wardrobe"
        class="min-h-11 self-start text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('item.back') }}
      </a>

      @if (item(); as row) {
        <!-- The garment, its name and the one action that acts on it are one
             unit: at region distance the name floats away from the
             photograph it names. DECISIONS.md 212. -->
        <div class="flex flex-col gap-group">
          <!-- The detail transform, built from image_public_id. The server sends
               image_url as a 300px padded thumbnail and nothing else, so this is
               the first screen in the project that cannot use it. O-10's pipe,
               at the first caller that needs it. -->
          <img
            [src]="row.image_public_id | cloudinaryUrl: 'detail'"
            [alt]="row.display_name ?? i18n.t('item.untitled')"
            class="mx-auto aspect-square w-full max-w-md rounded-2xl bg-surface object-contain"
          />

          <!-- Under the photograph now, and still the body face: display_name is
               user-entered and may be non-Latin, which Fraunces does not cover.
               05's rule names this screen as one of four that must apply it
               deliberately, so the size grows and the family does not (071). -->
          <h1 class="text-3xl leading-tight">{{ row.display_name ?? i18n.t('item.untitled') }}</h1>

          <!-- The primary action on this screen, and 05-FRONTEND-SPEC.md's
               instruction is that it is not buried behind edit and delete — so it
               sits directly under the photograph, above the tags. Only on a ready
               row: the stylist is shown ready, unarchived items alone, so the
               button on any other row would navigate to a request the endpoint
               answers anchor_unavailable to. -->
          @if (row.status === 'ready') {
            <a
              appButton
              routerLink="/stylist"
              [queryParams]="{ anchor: row.id }"
              class="self-start"
            >
              {{ i18n.t('item.styleAround') }}
            </a>
          }
        </div>

        <!-- Both notices are about the tags below them — one says they were
             set by hand, the other that they are still short — so they are
             grouped with the editor rather than left three siblings at equal
             distance. DECISIONS.md 212. -->
        <div class="flex flex-col gap-group">
          @if (row.user_edited) {
            <p class="text-sm">
              <span class="font-medium">{{ i18n.t('item.edited.badge') }}</span>
              — {{ i18n.t('item.edited.explain') }}
            </p>
          }

          <!-- 116 clears a failed status when a saved row carries every required tag, so
               a row still marked failed after a save is one that is genuinely
               short. The message is read off the status the response carried and
               never off a client-side copy of the required set — naming the
               missing field would need that copy, which is what B declined. -->
          @if (row.status === 'failed') {
            <p class="rounded-xl bg-surface-elevated p-4 text-sm font-medium text-danger">
              {{ i18n.t('item.incomplete') }}
            </p>
          }

          @if (row.status === 'processing') {
            <p class="rounded-xl bg-surface-elevated p-4 text-sm text-ink-muted">
              {{ i18n.t('item.processing') }}
            </p>
          } @else {
            <section class="flex flex-col gap-3">
              <h2 class="font-display text-xl">{{ i18n.t('item.edit.title') }}</h2>
              <app-tag-editor
                [item]="row"
                [saving]="saving()"
                [errorKey]="saveError()"
                (save)="onSave($event)"
              />
            </section>
          }
        </div>

        <section class="flex flex-col gap-2">
          <h2 class="font-display text-xl">{{ i18n.t('item.wear.title') }}</h2>
          <!-- Real from 3.4, which is what the placeholder here was waiting
               for. Never-worn gets its own sentence rather than a zero and a
               blank date: it is the state most of a wardrobe is in, and 3.6
               builds a whole insights panel on counting it. -->
          @if (row.wear_count === 0) {
            <p class="text-sm">{{ i18n.t('item.wear.never') }}</p>
          } @else {
            <p class="text-sm">{{ i18n.t('item.wear.count', { count: row.wear_count }) }}</p>
            <!-- Guarded rather than assumed. Every writer of wear_count also
                 writes last_worn_at, so this cannot be false today — but the
                 two are separate nullable columns and the type says so. -->
            @if (row.last_worn_at; as worn) {
              <p class="text-sm">{{ i18n.t('item.wear.last', { date: worn }) }}</p>
            }
          }
        </section>

        <!-- The set row, and it renders in both states rather than only when
             there is a set: a garment in none is where a set is declared from,
             and STAGE-4A puts the declaration on this screen because it is
             where a user is standing when they think about one. The branch is
             row.set_id and not set(), which is null both for a garment in no
             set and for one whose set failed to load — the second must not
             offer to declare a set that already exists. -->
        <section class="flex flex-col gap-group">
          <div class="flex flex-col gap-2">
            <h2 class="font-display text-xl">{{ i18n.t('item.set.title') }}</h2>

            @if (row.set_id === null) {
              <p class="text-sm">{{ i18n.t('item.set.explain') }}</p>
            } @else if (set(); as declared) {
              <!-- The content face, for 071's reason: a set's name was typed by
                   a person and Fraunces is not the family to render it in. -->
              @if (declared.name; as name) {
                <p class="font-sans text-sm text-ink">{{ name }}</p>
              }

              <ul class="flex flex-wrap gap-4">
                @for (member of members(); track member.id) {
                  <li class="w-24">
                    <a
                      [routerLink]="['/wardrobe', member.id]"
                      class="flex flex-col gap-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                    >
                      <!-- Empty alt, because the name below is inside the same
                           anchor: with alt text the link announces twice. -->
                      <img
                        [src]="member.image_url"
                        alt=""
                        loading="lazy"
                        class="aspect-4/5 w-full rounded-[2px] object-contain"
                      />
                      <span class="font-sans text-xs text-ink">{{ memberName(member) }}</span>
                      <!-- An archived member stays in its set (02-DATA-MODEL.md)
                           and GET /items excludes it, so this row is the only
                           place in the application it is visible at all. Saying
                           so is the API spec's requirement of any client that
                           draws a set. -->
                      @if (member.is_archived) {
                        <span
                          class="text-[10px] font-medium tracking-[0.18em] text-ink-soft uppercase"
                          >{{ i18n.t('item.set.archived') }}</span
                        >
                      }
                    </a>
                  </li>
                }
              </ul>
            }
          </div>

          <div class="flex flex-col gap-2">
            <div class="flex flex-wrap items-center gap-3">
              <button
                appButton
                variant="secondary"
                type="button"
                (click)="openPicker()"
                [disabled]="picking()"
                class="disabled:opacity-50"
              >
                {{ row.set_id === null ? i18n.t('item.set.declare') : i18n.t('item.set.add') }}
              </button>

              @if (row.set_id !== null) {
                <button
                  appButton
                  variant="ghost"
                  type="button"
                  (click)="removeFromSet()"
                  [disabled]="removingFromSet()"
                  class="disabled:opacity-50"
                >
                  {{ removingFromSet() ? i18n.t('item.set.removing') : i18n.t('item.set.remove') }}
                </button>
              }
            </div>

            <!-- Said before the control is pressed, which is STAGE-4A's
                 requirement and the one place a user can act on it: the rule is
                 the server's, enforced by DELETE /sets/{id}/items/{id}
                 answering 204, and this is it stated once in words. Two members
                 exactly — at three the removal leaves a set behind. -->
            @if (dissolves()) {
              <p class="text-sm">{{ i18n.t('item.set.dissolves') }}</p>
            }
          </div>

          @if (setError(); as key) {
            <p class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
          }
        </section>

        <!-- The armed line is the confirmation for the button directly above
             it, not a notice about the page. DECISIONS.md 212. -->
        <div class="flex flex-col gap-group">
          <div class="flex flex-wrap items-center gap-3 border-bs border-line pt-4">
            <!-- One control, ungated. It sends the unforced retag; the 409 opens
                 the second step. Gating it on user_edited and forcing straight
                 away would mean the 409 is never produced from the UI, and
                 acceptance criterion 6 would stay a route test. 122. -->
            <button
              appButton
              variant="secondary"
              type="button"
              (click)="retag()"
              [disabled]="retagging()"
              class="disabled:opacity-50"
            >
              {{ retagging() ? i18n.t('item.retag.working') : i18n.t('item.retag.action') }}
            </button>

            <!-- Two deliberate clicks, not window.confirm and not a modal. The
                 gate's confirm() returns undefined, so a confirm-guarded delete
                 would read as tested and never run — 098 with a sharper edge. A
                 modal was declined on cost: a fourth hand-rolled focus trap,
                 with inert unsupported, to guard a misclick two clicks already
                 guard. DECISIONS.md 126. -->
            <!-- The armed state stays a class binding rather than a variant swap:
                 the danger variant is what this control looks like unarmed, and
                 arming it fills the button in. -->
            <button
              appButton
              variant="danger"
              type="button"
              (click)="onDelete()"
              (blur)="disarm()"
              [disabled]="deleting()"
              class="disabled:opacity-50"
              [class.bg-danger]="armed()"
              [class.text-surface]="armed()"
            >
              {{ deleteLabel() }}
            </button>
          </div>

          @if (armed()) {
            <p class="text-sm">{{ i18n.t('item.delete.arm') }}</p>
          }
        </div>

        @if (retagConflict()) {
          <div class="flex flex-col items-start gap-3 rounded-xl bg-surface-elevated p-4">
            <p class="text-sm font-medium">{{ i18n.t('item.retag.confirm') }}</p>
            <div class="flex flex-wrap gap-3">
              <button appButton variant="danger" type="button" (click)="retag(true)">
                {{ i18n.t('item.retag.confirmAction') }}
              </button>
              <button appButton variant="ghost" type="button" (click)="dismissConflict()">
                {{ i18n.t('item.retag.cancel') }}
              </button>
            </div>
          </div>
        }

        @if (actionError(); as key) {
          <p class="text-sm font-medium text-danger">{{ i18n.t(key) }}</p>
        }

        <!-- The whole loaded wardrobe goes in and the sheet excludes what it
             must; the page supplies the id it is showing, which is the one
             exclusion the sheet cannot work out for itself. -->
        @if (picking()) {
          <app-set-picker
            [items]="store.items()"
            [currentItemId]="row.id"
            [saving]="addingToSet()"
            [errorKey]="pickError()"
            (picked)="onPicked($event)"
            (dismissed)="closePicker()"
          />
        }
      } @else if (loadError()) {
        <p class="text-sm font-medium text-danger">{{ i18n.t('item.error.load') }}</p>
      }
    </main>
  `,
})
export class ItemDetailPage {
  protected readonly i18n = inject(I18nService);
  // Read by the template since 4A.2: the picker's candidates are the wardrobe
  // this page already holds, rather than a second collection fetched for it.
  protected readonly store = inject(WardrobeStore);
  private readonly api = inject(ItemsApi);
  private readonly sets = inject(SetsApi);
  private readonly router = inject(Router);

  // Read from the snapshot, not a subscription: nothing changes `:id` under
  // this component — every route into it is a fresh navigation from the grid.
  // 1.11 adding next/prev on this screen is what would break that, and it is
  // named here rather than left for whoever writes it. DECISIONS.md 127.
  private readonly id = inject(ActivatedRoute).snapshot.paramMap.get('id') ?? '';

  // The row fetched by id when the collection has none, kept beside `items()`
  // and never written into it. A deep-linked row therefore does not live-update
  // — the poll derives from `items()` — which is honest rather than accidental:
  // the poll is stopped on this route anyway, because WardrobePage's DestroyRef
  // stops it on navigation away. DECISIONS.md 127.
  private readonly fetched = signal<Item | null>(null);
  protected readonly loadError = signal(false);

  protected readonly saving = signal(false);
  protected readonly saveError = signal<string | null>(null);
  protected readonly retagging = signal(false);
  protected readonly retagConflict = signal(false);
  protected readonly deleting = signal(false);
  protected readonly armed = signal(false);
  protected readonly actionError = signal<string | null>(null);

  // The set this garment belongs to, hydrated from GET /sets/{set_id} rather
  // than assembled out of items(): the collection excludes archived rows, so a
  // set with an archived member would draw one member short with nothing on
  // screen saying so, and a deep link onto this route has no collection at all.
  // 04-API-SPEC.md assigns the fetch to "the one screen that renders them",
  // which is this one.
  protected readonly set = signal<ItemSet | null>(null);
  // The row's own error line — a set that would not load, or a removal that
  // failed. Add failures go to the sheet instead, in `pickError`, because that
  // is where the user was standing when they asked.
  protected readonly setError = signal<string | null>(null);
  protected readonly pickError = signal<string | null>(null);
  protected readonly picking = signal(false);
  protected readonly addingToSet = signal(false);
  protected readonly removingFromSet = signal(false);

  protected readonly item = computed(
    () => this.store.items().find((candidate) => candidate.id === this.id) ?? this.fetched(),
  );

  protected readonly members = computed(
    () => this.set()?.items.filter((member) => member.id !== this.id) ?? [],
  );

  // Two exactly. A set of three loses a member and survives; a set of two has
  // nothing left to be, which the server enforces and this line announces.
  protected readonly dissolves = computed(() => this.set()?.items.length === 2);

  protected readonly deleteLabel = computed(() => {
    if (this.deleting()) {
      return this.i18n.t('item.delete.working');
    }
    return this.armed() ? this.i18n.t('item.delete.arm') : this.i18n.t('item.delete.action');
  });

  constructor() {
    // WardrobePage's guard, on the second page that can start a run. This one
    // does not poll on arrival, but it may call store.load() when the picker
    // opens on an empty collection — and the store is providedIn: 'root', so a
    // run nobody stops keeps polling behind whatever screen comes next.
    // DECISIONS.md 107.
    inject(DestroyRef).onDestroy(() => this.store.stopPolling());

    const row = this.item();
    if (row === null) {
      this.api.get(this.id).subscribe({
        next: (item) => {
          this.fetched.set(item);
          this.loadSet(item);
        },
        error: () => this.loadError.set(true),
      });
      return;
    }
    this.loadSet(row);
  }

  private loadSet(row: Item): void {
    const setId = row.set_id;
    if (setId === null) {
      return;
    }
    this.sets.get(setId).subscribe({
      next: (found) => this.set.set(found),
      // The row states that this garment is in a set — set_id says so — and
      // then cannot name the others. It deliberately does not fall back to the
      // empty state, which would offer to declare a set that already exists.
      error: () => this.setError.set('item.set.error.load'),
    });
  }

  protected openPicker(): void {
    this.disarm();
    this.pickError.set(null);
    this.picking.set(true);
    // A deep link onto this route never loaded the wardrobe, and the sheet
    // would open on nothing. This is the store's own load rather than a second
    // way of fetching items, and it is asked for here rather than on
    // construction because it is the picker that needs the collection.
    if (this.store.items().length === 0) {
      this.store.load();
    }
  }

  protected closePicker(): void {
    this.picking.set(false);
  }

  // One control, two endpoints. A garment in no set declares one over itself
  // and the garment just picked; a garment in a set adds to the set it has.
  protected onPicked(picked: Item): void {
    const declared = this.set();
    this.addingToSet.set(true);
    this.pickError.set(null);

    const request =
      declared === null
        ? this.sets.create({ item_ids: [this.id, picked.id] })
        : this.sets.addItem(declared.id, { item_id: picked.id });

    request.subscribe({
      next: (found) => {
        this.absorb(found);
        this.addingToSet.set(false);
        // Closed on success, where the upload sheet's camera path stays open:
        // there is one garment to pick and the thing to look at afterwards is
        // the row behind this sheet. DECISIONS.md 098's asymmetry, decided the
        // other way for a control that is not a batch.
        this.picking.set(false);
      },
      error: (error: unknown) => {
        this.pickError.set(pickErrorKey(error));
        this.addingToSet.set(false);
      },
    });
  }

  protected removeFromSet(): void {
    const declared = this.set();
    if (declared === null) {
      return;
    }
    this.disarm();
    this.removingFromSet.set(true);
    this.setError.set(null);

    this.sets.removeItem(declared.id, this.id).subscribe({
      next: (survivor) => {
        // The screen ends in the same state either way — this garment has no
        // set — and the difference is whether the *other* member still has one.
        // A null is the 204: the set dissolved, so every member it held loses
        // its set_id, including the one that was never named in the URL. A set
        // object is the 200: only this garment was detached, and the survivors
        // arrive as server rows.
        const orphaned = survivor === null ? declared.items.map((member) => member.id) : [this.id];
        this.store.clearSetId(orphaned);
        if (survivor !== null) {
          this.store.absorbSet(survivor);
        }
        this.detach();
        this.removingFromSet.set(false);
      },
      error: () => {
        this.setError.set('item.set.error.remove');
        this.removingFromSet.set(false);
      },
    });
  }

  private absorb(found: ItemSet): void {
    this.set.set(found);
    this.store.absorbSet(found);
    // A deep-linked row never entered items(), so the store write cannot reach
    // it and the page's own copy has to be moved by hand — the same thing
    // onSave does with the row a PATCH answers with.
    const mine = found.items.find((member) => member.id === this.id);
    if (this.fetched() !== null && mine !== undefined) {
      this.fetched.set(mine);
    }
  }

  private detach(): void {
    this.set.set(null);
    const row = this.fetched();
    if (row !== null) {
      this.fetched.set({ ...row, set_id: null });
    }
  }

  protected memberName(member: Item): string {
    const name = member.display_name?.trim();
    return name ? name : this.i18n.t('item.untitled');
  }

  protected onSave(changes: ItemUpdate): void {
    this.disarm();
    this.saving.set(true);
    this.saveError.set(null);

    this.store.edit(this.id, changes).subscribe({
      next: (item) => {
        // Written to the fallback too, so a deep-linked row shows its own save.
        if (this.fetched() !== null) {
          this.fetched.set(item);
        }
        this.saving.set(false);
      },
      // One string for every rejection. 04-API-SPEC.md names the offending
      // field inside `detail`, and CONVENTIONS.md forbids rendering a raw
      // error, so this cannot say which field — recorded as a limitation the
      // way 099 recorded the filename it cannot show. DECISIONS.md 128.
      error: () => {
        this.saveError.set('item.error.save');
        this.saving.set(false);
      },
    });
  }

  protected retag(force = false): void {
    this.disarm();
    this.retagging.set(true);
    this.retagConflict.set(false);
    this.actionError.set(null);

    this.api.retag(this.id, force).subscribe({
      next: () => {
        this.retagging.set(false);
        // The row is `processing` now and this editor must not be open on one
        // (STAGE-1 1.9). Leaving is the same rule the deep-link guard applies,
        // one second later.
        void this.router.navigate(['/wardrobe']);
      },
      error: (error: unknown) => {
        this.retagging.set(false);
        if (error instanceof HttpErrorResponse && this.code(error) === 'item_edited') {
          this.retagConflict.set(true);
          return;
        }
        this.actionError.set('item.retag.error');
      },
    });
  }

  protected dismissConflict(): void {
    this.retagConflict.set(false);
  }

  protected onDelete(): void {
    if (!this.armed()) {
      this.armed.set(true);
      return;
    }
    this.armed.set(false);
    this.deleting.set(true);
    this.actionError.set(null);

    this.store.archive(this.id).subscribe({
      next: () => {
        this.deleting.set(false);
        void this.router.navigate(['/wardrobe']);
      },
      error: () => {
        this.deleting.set(false);
        this.actionError.set('item.error.delete');
      },
    });
  }

  // Any other interaction disarms, not only blur: an armed delete that survives
  // a save or a retag is a second click landing on a control the user has
  // stopped thinking about.
  protected disarm(): void {
    this.armed.set(false);
  }

  private code(error: HttpErrorResponse): string | undefined {
    return (error.error as { code?: string } | null)?.code;
  }
}

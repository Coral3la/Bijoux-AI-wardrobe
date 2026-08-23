import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';

// Hand-written copies of MAX_FILES_PER_REQUEST and max_upload_bytes in
// backend/app/core/config.py. Nothing compares the two — a browser cannot read
// pydantic-settings and no endpoint publishes the limits — so this is the third
// instance of the class CONVENTIONS.md records for the upload limits and the
// password rules. MB means mebibytes here, 1024 squared, because that is what
// the server means. DECISIONS.md 101.
export const MAX_FILES_PER_REQUEST = 20;
export const MAX_UPLOAD_MB = 10;
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

// Matches the formats app/services/storage.py identifies from the file's own
// bytes. `accept` is a hint the user can override, so it replaces no
// server-side check — it stops the gallery offering GIFs and SVGs that the API
// answers with a 415. DECISIONS.md 045.
const ACCEPTED = 'image/jpeg,image/png,image/webp,image/heic,image/heif';

@Component({
  selector: 'app-upload-sheet',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- A plain element, not <dialog>. jsdom implements neither showModal nor
         show nor close (measured at 1.6), so a dialog-based sheet could not be
         opened by any test in this project. A testability constraint that
         changes a design decision is recorded as one. DECISIONS.md 098. -->
    <div class="fixed inset-0 z-40 flex flex-col justify-end">
      <button
        type="button"
        (click)="dismissed.emit()"
        [attr.aria-label]="i18n.t('wardrobe.upload.dismiss')"
        class="absolute inset-0 bg-ink/40"
      ></button>

      <section
        role="dialog"
        aria-modal="true"
        [attr.aria-label]="i18n.t('wardrobe.upload.title')"
        class="relative flex flex-col gap-4 rounded-t-2xl bg-surface p-6 shadow-lg"
      >
        <h2 class="font-display text-xl">{{ i18n.t('wardrobe.upload.title') }}</h2>

        <!-- Part of the feature, not decoration: tagging accuracy depends on
             it, which is why it sits above the buttons rather than below. -->
        <p class="max-w-prose text-sm">{{ i18n.t('wardrobe.upload.tip') }}</p>

        @if (message(); as text) {
          <p class="text-sm font-medium text-danger">{{ text }}</p>
        }

        <div class="flex flex-col gap-3">
          <label
            class="flex min-h-11 cursor-pointer items-center justify-center rounded-md bg-accent px-4 text-surface focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent"
          >
            {{ i18n.t('wardrobe.upload.camera') }}
            <!-- The input stays focusable rather than display:none, so the
                 keyboard path is the native one and needs no handler. -->
            <input
              type="file"
              class="sr-only"
              [accept]="accepted"
              capture="environment"
              [disabled]="uploading()"
              (change)="onFiles($event, false)"
            />
          </label>

          <label
            class="flex min-h-11 cursor-pointer items-center justify-center rounded-md px-4 underline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent"
          >
            {{ i18n.t('wardrobe.upload.gallery') }}
            <input
              type="file"
              class="sr-only"
              [accept]="accepted"
              multiple
              [disabled]="uploading()"
              (change)="onFiles($event, true)"
            />
          </label>
        </div>

        <button
          type="button"
          (click)="dismissed.emit()"
          class="min-h-11 self-start rounded-md px-3 text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {{ i18n.t('wardrobe.upload.done') }}
        </button>
      </section>
    </div>
  `,
})
export class UploadSheet {
  protected readonly i18n = inject(I18nService);
  protected readonly accepted = ACCEPTED;

  readonly uploading = input(false);
  readonly serverError = input<string | null>(null);

  readonly filesSelected = output<readonly File[]>();
  // Not `close`: @angular-eslint/no-output-native refuses an output named
  // after a standard DOM event, because a native close event would fire the
  // same binding.
  readonly dismissed = output<void>();

  private readonly localError = signal<string | null>(null);

  // The local message is already rendered because only this component knows
  // the filename and the limit to interpolate; the server's is still a key.
  // The asymmetry is deliberate and the local one wins: when it is set, no
  // request was made, so there is no server answer to compete with it.
  protected readonly message = computed(() => {
    const local = this.localError();
    if (local !== null) {
      return local;
    }
    const key = this.serverError();
    return key === null ? null : this.i18n.t(key);
  });

  protected onFiles(event: Event, fromGallery: boolean): void {
    const input = event.target as HTMLInputElement;
    const files = [...(input.files ?? [])];
    // Without this, picking the same file twice fires no second change event.
    input.value = '';
    if (files.length === 0) {
      return;
    }

    const problem = this.reject(files);
    this.localError.set(problem);
    if (problem !== null) {
      return;
    }

    this.filesSelected.emit(files);
    // Asymmetric on purpose. The camera adds one garment at a time and the
    // next shot should need no navigation; the gallery is the batch path, and
    // after it the user's next move is watching the rows arrive, which a sheet
    // over the grid would hide. DECISIONS.md 098.
    if (fromGallery) {
      this.dismissed.emit();
    }
  }

  // The whole selection is refused for one bad file, mirroring the server:
  // 04-API-SPEC.md rejects the entire request, so filtering the good files out
  // here would make the sheet behave differently from the API it guards.
  private reject(files: readonly File[]): string | null {
    if (files.length > MAX_FILES_PER_REQUEST) {
      return this.i18n.t('wardrobe.upload.error.tooMany', { max: MAX_FILES_PER_REQUEST });
    }
    const oversized = files.find((file) => file.size > MAX_UPLOAD_BYTES);
    if (oversized !== undefined) {
      return this.i18n.t('wardrobe.upload.error.tooLarge', {
        name: oversized.name,
        max: MAX_UPLOAD_MB,
      });
    }
    return null;
  }
}

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../../../../public/i18n/en.json';
import { I18nService } from '../../core/i18n/i18n.service';
import { MAX_UPLOAD_BYTES, UploadSheet } from './upload-sheet';

// Transcribed from CONVENTIONS.md — "MAX_UPLOAD_MB=10 is 10,485,760 bytes" —
// and deliberately not computed from the component's own constant. Every size
// expectation below reads this literal instead. A mutation run at 1.6 proved
// why: with the expectations reading MAX_UPLOAD_BYTES, changing the component
// to 1000 * 1000 moved the tests with it and all 155 stayed green. A test that
// reads its expectation from the thing under test measures nothing on its own
// (06-TESTING-STRATEGY.md).
const TEN_MEBIBYTES = 10_485_760;

let fixture: ComponentFixture<UploadSheet>;
let mock: HttpTestingController;
let selected: File[][];
let closed: number;

function inputs(): HTMLInputElement[] {
  return [
    ...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLInputElement>(
      'input[type=file]',
    ),
  ];
}

function camera(): HTMLInputElement {
  return inputs()[0];
}

function gallery(): HTMLInputElement {
  return inputs()[1];
}

function text(): string {
  return (fixture.nativeElement as HTMLElement).textContent ?? '';
}

function file(name: string, size = 8): File {
  return new File([new Uint8Array(size)], name, { type: 'image/jpeg' });
}

// jsdom has no DataTransfer and `new FileList()` is an illegal constructor, so
// there is no way to build a real FileList — measured at task 1.6. This
// installs an array in its place, which is what the component spreads. It
// exercises our handler; it does not exercise FileList semantics.
async function pick(input: HTMLInputElement, files: File[]): Promise<void> {
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  input.dispatchEvent(new Event('change'));
  await fixture.whenStable();
}

async function render(uploading = false, serverError: string | null = null): Promise<void> {
  fixture = TestBed.createComponent(UploadSheet);
  fixture.componentRef.setInput('uploading', uploading);
  fixture.componentRef.setInput('serverError', serverError);
  fixture.componentInstance.filesSelected.subscribe((files) => selected.push([...files]));
  fixture.componentInstance.dismissed.subscribe(() => closed++);
  await fixture.whenStable();
}

describe('UploadSheet', () => {
  beforeEach(async () => {
    selected = [];
    closed = 0;
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    mock = TestBed.inject(HttpTestingController);

    const loading = TestBed.inject(I18nService).load();
    mock.expectOne('/i18n/en.json').flush(en);
    await loading;
  });

  afterEach(() => {
    mock.verify();
    TestBed.resetTestingModule();
  });

  // The limit is a hand-written copy of a Python setting and nothing compares
  // the two (CONVENTIONS.md). This is the only place the copy is checked at
  // all, and it is checked against a transcribed number rather than itself.
  it('mirrors ten mebibytes, not ten million bytes', () => {
    expect(MAX_UPLOAD_BYTES).toBe(TEN_MEBIBYTES);
  });

  // The tip is part of the feature: tagging accuracy depends on it.
  it('shows the framing tip above the buttons', async () => {
    await render();

    expect(text()).toContain('lay the item flat or hang it against a plain wall');
  });

  // Narrowed from image/* so the gallery stops offering GIFs and SVGs that the
  // API answers with a 415. DECISIONS.md 045.
  it('accepts exactly the formats the API accepts, on both inputs', async () => {
    await render();

    for (const input of inputs()) {
      expect(input.getAttribute('accept')).toBe(
        'image/jpeg,image/png,image/webp,image/heic,image/heif',
      );
    }
  });

  // jsdom reflects `capture` as a content attribute and gives it no property
  // and no behaviour. This asserts the string is on the right input. Whether a
  // phone opens the rear camera is unverifiable here and in Playwright.
  it('puts capture on the camera input and not on the gallery input', async () => {
    await render();

    expect(camera().getAttribute('capture')).toBe('environment');
    expect(gallery().hasAttribute('capture')).toBe(false);
  });

  it('puts multiple on the gallery input and not on the camera input', async () => {
    await render();

    expect(gallery().hasAttribute('multiple')).toBe(true);
    expect(camera().hasAttribute('multiple')).toBe(false);
  });

  it('emits the files a gallery pick selected', async () => {
    await render();
    await pick(gallery(), [file('a.jpg'), file('b.jpg')]);

    expect(selected).toHaveLength(1);
    expect(selected[0].map((f) => f.name)).toEqual(['a.jpg', 'b.jpg']);
  });

  // D3, and it is asymmetric on purpose: one garment at a time versus a batch.
  it('stays open after a camera capture', async () => {
    await render();
    await pick(camera(), [file('a.jpg')]);

    expect(selected).toHaveLength(1);
    expect(closed).toBe(0);
  });

  it('closes after a gallery pick', async () => {
    await render();
    await pick(gallery(), [file('a.jpg')]);

    expect(closed).toBe(1);
  });

  it('refuses more files than the server would take, and sends nothing', async () => {
    await render();
    await pick(
      gallery(),
      Array.from({ length: 21 }, (_, index) => file(`${index}.jpg`)),
    );

    expect(selected).toHaveLength(0);
    expect(text()).toContain('Choose at most 20 photos at a time.');
  });

  // Two files, one of them oversized: the message has to name the offending
  // file rather than the first one. Single-file coverage cannot tell the
  // difference — 093's lesson, applied before it recurs.
  it('names the oversized file when only the second one is too large', async () => {
    await render();
    await pick(gallery(), [file('small.jpg'), file('huge.jpg', TEN_MEBIBYTES + 1)]);

    expect(selected).toHaveLength(0);
    expect(text()).toContain('huge.jpg is larger than 10 MB.');
  });

  // The whole batch goes, mirroring the server, rather than the good files
  // being sent and the bad one dropped.
  it('refuses the whole selection for one bad file', async () => {
    await render();
    await pick(gallery(), [file('a.jpg'), file('huge.jpg', TEN_MEBIBYTES + 1), file('b.jpg')]);

    expect(selected).toHaveLength(0);
  });

  // CONVENTIONS.md: a limit in MB means mebibytes, 1024 squared. The two
  // definitions differ by 5% and the failure is a file the sheet accepts and
  // the API rejects with a 413.
  it('accepts a file of exactly the limit and refuses one byte more', async () => {
    await render();
    await pick(gallery(), [file('exact.jpg', TEN_MEBIBYTES)]);
    expect(selected).toHaveLength(1);

    await pick(gallery(), [file('over.jpg', TEN_MEBIBYTES + 1)]);
    expect(selected).toHaveLength(1);
  });

  it('renders the server message it was handed', async () => {
    await render(false, 'wardrobe.upload.error.uploadFailed');

    expect(text()).toContain("We couldn't store those photos.");
  });

  it('disables both inputs while a batch is in flight', async () => {
    await render(true);

    for (const input of inputs()) {
      expect(input.disabled).toBe(true);
    }
  });

  it('closes when the backdrop is used', async () => {
    await render();
    (fixture.nativeElement as HTMLElement).querySelector('button')!.click();

    expect(closed).toBe(1);
  });

  it('ignores a picker that was opened and dismissed', async () => {
    await render();
    await pick(gallery(), []);

    expect(selected).toHaveLength(0);
    expect(closed).toBe(0);
  });
});

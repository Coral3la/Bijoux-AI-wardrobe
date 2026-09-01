import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

type Strings = Readonly<Record<string, string>>;
export type Params = Readonly<Record<string, string | number>>;

// One run of a rendered string, and whether it came from the string table or
// from a value the caller supplied as content. DECISIONS.md 213.
export interface Segment {
  readonly text: string;
  readonly content: boolean;
}

// Shared despite the /g flag: String.replace resets lastIndex, exec would not.
const PLACEHOLDER = /\{\{\s*(\w+)\s*\}\}/g;

@Injectable({ providedIn: 'root' })
export class I18nService {
  private readonly http = inject(HttpClient);
  private readonly strings = signal<Strings>({});

  async load(locale = 'en'): Promise<void> {
    this.strings.set(await firstValueFrom(this.http.get<Strings>(`/i18n/${locale}.json`)));
  }

  t(key: string, params?: Params): string {
    const template = this.strings()[key] ?? key;
    if (params === undefined) {
      return template;
    }

    return template.replace(PLACEHOLDER, (placeholder, name: string) =>
      name in params ? String(params[name]) : placeholder,
    );
  }

  // The same template `t()` interpolates, cut *at* the placeholders rather than
  // through them, so an authored sentence can render a content value in the
  // content face while the key stays one whole reorderable string. A translation
  // that puts {{name}} first produces a leading content segment and nothing else
  // changes — which is the property that ruled out splitting keys. 213.
  //
  // `matchAll` rather than `replace`, because the split needs to know *where*
  // each placeholder sat and a replacement callback throws that away. Safe
  // against the shared /g regex above: matchAll clones it and never advances the
  // original's lastIndex, which `replace` has already left at 0.
  segments(key: string, params?: Params, content?: Params): readonly Segment[] {
    const template = this.strings()[key] ?? key;
    const parts: Segment[] = [];
    let cut = 0;

    for (const match of template.matchAll(PLACEHOLDER)) {
      const name = match[1];
      // Content wins when a name is in both, rather than the two racing on
      // object key order: a value the caller called content is content.
      const isContent = content !== undefined && name in content;
      const value = isContent ? content[name] : params?.[name];
      // Left inside the literal run rather than dropped, which is `t()`'s own
      // rule: an unsupplied placeholder stays visible so the fault is findable
      // on screen rather than silently blank.
      if (value === undefined) {
        continue;
      }
      if (match.index > cut) {
        parts.push({ text: template.slice(cut, match.index), content: false });
      }
      parts.push({ text: String(value), content: isContent });
      cut = match.index + match[0].length;
    }

    if (cut < template.length) {
      parts.push({ text: template.slice(cut), content: false });
    }
    return parts;
  }
}

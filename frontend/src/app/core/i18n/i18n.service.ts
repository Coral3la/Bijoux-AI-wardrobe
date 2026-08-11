import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

type Strings = Readonly<Record<string, string>>;
type Params = Readonly<Record<string, string | number>>;

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
}

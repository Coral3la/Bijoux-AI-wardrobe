import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, firstValueFrom, tap } from 'rxjs';

import { environment } from '../../../environments/environment';
import { TokenResponse, User } from '../../shared/models/user.model';

const TOKEN_KEY = 'bijoux.token';

export type RestoreNotice = 'unreachable' | 'signed-out';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly tokenSignal = signal<string | null>(localStorage.getItem(TOKEN_KEY));
  private readonly userSignal = signal<User | null>(null);
  private readonly noticeSignal = signal<RestoreNotice | null>(null);
  private readonly restoringSignal = signal(false);

  readonly token = this.tokenSignal.asReadonly();
  readonly currentUser = this.userSignal.asReadonly();
  readonly restoreNotice = this.noticeSignal.asReadonly();
  readonly restoring = this.restoringSignal.asReadonly();

  // A confirmed user, not a stored token: a token the server has not answered
  // for is a credential we hold, not a session. DECISIONS.md 067.
  readonly isAuthenticated = computed(() => this.userSignal() !== null);

  register(email: string, password: string, displayName: string | null): Observable<TokenResponse> {
    return this.http
      .post<TokenResponse>(`${environment.apiUrl}/auth/register`, {
        email,
        password,
        display_name: displayName,
      })
      .pipe(tap((response) => this.accept(response)));
  }

  login(email: string, password: string): Observable<TokenResponse> {
    return this.http
      .post<TokenResponse>(`${environment.apiUrl}/auth/login`, { email, password })
      .pipe(tap((response) => this.accept(response)));
  }

  async restore(): Promise<void> {
    if (this.restoringSignal()) {
      return;
    }
    if (this.tokenSignal() === null) {
      this.noticeSignal.set(null);
      return;
    }

    this.restoringSignal.set(true);
    try {
      const user = await firstValueFrom(this.http.get<User>(`${environment.apiUrl}/auth/me`));
      this.userSignal.set(user);
      this.noticeSignal.set(null);
    } catch (error: unknown) {
      // A 401 belongs to the interceptor, which has already cleared the session
      // and set 'signed-out'. Everything else means no usable answer arrived,
      // and the token is deliberately kept. DECISIONS.md 067.
      if (!(error instanceof HttpErrorResponse) || error.status !== 401) {
        this.noticeSignal.set('unreachable');
      }
    } finally {
      this.restoringSignal.set(false);
    }
  }

  logout(): void {
    this.clearSession();
  }

  // The server rejected the credential. Distinct from logout() so that the
  // notice has exactly one writer and no call ordering to get wrong.
  rejectSession(): void {
    this.clearSession();
    this.noticeSignal.set('signed-out');
  }

  private clearSession(): void {
    localStorage.removeItem(TOKEN_KEY);
    this.tokenSignal.set(null);
    this.userSignal.set(null);
  }

  private accept(response: TokenResponse): void {
    localStorage.setItem(TOKEN_KEY, response.access_token);
    this.tokenSignal.set(response.access_token);
    this.userSignal.set(response.user);
    this.noticeSignal.set(null);
  }
}

import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { userLabel } from '../../shared/models/user.model';

@Component({
  selector: 'app-wardrobe-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <main class="mx-auto flex w-full max-w-3xl flex-col items-start gap-4 p-6">
      <h1 class="font-display text-3xl">{{ i18n.t('wardrobe.title') }}</h1>

      <!-- Body face, deliberately: display_name is user-entered and may be
           non-Latin, which Fraunces does not cover. DECISIONS.md 071. -->
      @if (auth.currentUser(); as user) {
        <p class="text-sm">{{ i18n.t('wardrobe.signedInAs', { name: label(user) }) }}</p>
      }

      <button
        type="button"
        (click)="signOut()"
        class="min-h-11 rounded-md px-3 text-sm underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {{ i18n.t('wardrobe.signOut') }}
      </button>
    </main>
  `,
})
export class WardrobePage {
  protected readonly i18n = inject(I18nService);
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly label = userLabel;

  // No guard re-runs on a route that is already active. DECISIONS.md 068.
  protected signOut(): void {
    this.auth.logout();
    void this.router.navigateByUrl('/login');
  }
}

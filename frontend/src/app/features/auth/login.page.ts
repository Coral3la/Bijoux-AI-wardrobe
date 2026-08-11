import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';

@Component({
  selector: 'app-login-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<h1 class="font-display text-3xl">{{ i18n.t('login.title') }}</h1>`,
})
export class LoginPage {
  protected readonly i18n = inject(I18nService);
}

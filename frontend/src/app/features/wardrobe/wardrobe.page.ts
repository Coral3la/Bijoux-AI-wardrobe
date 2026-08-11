import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { I18nService } from '../../core/i18n/i18n.service';

@Component({
  selector: 'app-wardrobe-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<h1 class="font-display text-3xl">{{ i18n.t('wardrobe.title') }}</h1>`,
})
export class WardrobePage {
  protected readonly i18n = inject(I18nService);
}

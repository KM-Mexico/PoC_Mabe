import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-data-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'data-table' },
  template: `<div class="data-table__scroll"><ng-content /></div>`
})
export class DataTableComponent {}

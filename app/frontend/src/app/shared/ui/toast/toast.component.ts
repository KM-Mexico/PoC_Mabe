import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-toast',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'toast', role: 'status', 'aria-live': 'polite' },
  template: `<span aria-hidden="true">✓</span><strong>{{ message() }}</strong>`
})
export class ToastComponent {
  readonly message = input.required<string>();
}

import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-feedback-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="feedback" [attr.role]="kind() === 'error' ? 'alert' : 'status'">
      <span class="feedback__icon" aria-hidden="true">{{ icon() }}</span>
      <div><strong>{{ title() }}</strong><p>{{ message() }}</p></div>
    </div>
  `
})
export class FeedbackStateComponent {
  readonly kind = input<'loading' | 'empty' | 'error'>('empty');
  readonly title = input.required<string>();
  readonly message = input.required<string>();

  protected icon(): string {
    return { loading: '◌', empty: '◇', error: '!' }[this.kind()];
  }
}


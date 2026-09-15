import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';

@Component({
  selector: 'app-button',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'button-host' },
  template: `
    <button
      class="button"
      [class]="'button button--' + variant()"
      [attr.type]="type()"
      [disabled]="disabled()"
      (click)="pressed.emit()"
    ><ng-content /></button>
  `
})
export class ButtonComponent {
  readonly variant = input<ButtonVariant>('primary');
  readonly type = input<'button' | 'submit'>('button');
  readonly disabled = input(false);
  readonly pressed = output<void>();
}


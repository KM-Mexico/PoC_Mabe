import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-form-field',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'form-field' },
  template: `
    <label [attr.for]="controlId()">{{ label() }}</label>
    <ng-content />
    @if (error()) { <small class="field-error" role="alert">{{ error() }}</small> }
  `
})
export class FormFieldComponent {
  readonly controlId = input.required<string>();
  readonly label = input.required<string>();
  readonly error = input<string | null>(null);
}

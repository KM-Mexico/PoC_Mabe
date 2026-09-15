import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'app-toggle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label class="toggle">
      <input type="checkbox" [checked]="checked()" [disabled]="disabled()" (change)="changed()">
      <span aria-hidden="true"></span>
      <strong>{{ label() }}</strong>
    </label>
  `
})
export class ToggleComponent {
  readonly checked = input.required<boolean>();
  readonly disabled = input(false);
  readonly label = input.required<string>();
  readonly toggled = output<boolean>();

  protected changed(): void { this.toggled.emit(!this.checked()); }
}

import { ChangeDetectionStrategy, Component, ElementRef, ViewChild, input, output } from '@angular/core';
import { ButtonComponent } from '../button/button.component';

@Component({
  selector: 'app-confirm-dialog',
  imports: [ButtonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <dialog #dialog class="dialog" aria-labelledby="confirm-title" aria-describedby="confirm-description">
      <div class="dialog__icon" aria-hidden="true">!</div>
      <h2 id="confirm-title">{{ title() }}</h2>
      <p id="confirm-description">{{ description() }}</p>
      <div class="dialog__actions">
        <app-button variant="ghost" (pressed)="close()">Cancelar</app-button>
        <app-button variant="danger" (pressed)="accept()">{{ confirmLabel() }}</app-button>
      </div>
    </dialog>
  `
})
export class ConfirmDialogComponent {
  @ViewChild('dialog', { static: true }) private dialog?: ElementRef<HTMLDialogElement>;
  readonly confirmed = output<void>();
  readonly title = input('Eliminar proyecto');
  readonly description = input('Esta acción elimina el proyecto local. No puede deshacerse.');
  readonly confirmLabel = input('Eliminar');

  open(): void {
    this.dialog?.nativeElement.showModal();
  }

  close(): void {
    this.dialog?.nativeElement.close();
  }

  protected accept(): void {
    this.confirmed.emit();
    this.close();
  }
}

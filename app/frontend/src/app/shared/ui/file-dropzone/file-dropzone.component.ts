import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'app-file-dropzone',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label
      class="dropzone"
      for="document-files"
      (dragover)="allowDrop($event)"
      (drop)="dropFiles($event)"
    >
      <span class="dropzone__icon" aria-hidden="true">↑</span>
      <strong>Arrastra tus fuentes aquí</strong>
      <small>o selecciona TXT, MD, PDF y XLSX</small>
      <input id="document-files" class="visually-hidden" type="file" multiple accept=".txt,.md,.pdf,.xlsx" (change)="chooseFiles($event)">
    </label>
    @if (files().length) {
      <ul class="pending-files" aria-label="Archivos seleccionados">
        @for (file of files(); track file.name + file.size + file.lastModified; let index = $index) {
          <li>
            <span><strong>{{ file.name }}</strong><small>{{ file.type || 'Tipo por verificar' }} · {{ formatSize(file.size) }}</small></span>
            <button type="button" class="icon-button" [attr.aria-label]="'Remover ' + file.name" (click)="removed.emit(index)">×</button>
          </li>
        }
      </ul>
    }
  `
})
export class FileDropzoneComponent {
  readonly files = input<readonly File[]>([]);
  readonly selected = output<File[]>();
  readonly removed = output<number>();

  protected allowDrop(event: DragEvent): void {
    event.preventDefault();
  }

  protected dropFiles(event: DragEvent): void {
    event.preventDefault();
    const files = event.dataTransfer?.files;
    if (files?.length) this.selected.emit(Array.from(files));
  }

  protected chooseFiles(event: Event): void {
    const target = event.currentTarget;
    if (target instanceof HTMLInputElement && target.files?.length) {
      this.selected.emit(Array.from(target.files));
      target.value = '';
    }
  }

  protected formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
  }
}

import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { Router } from '@angular/router';
import { ClientIdentityService } from '../../../core/client-identity.service';

type Phase = 1 | 2 | 3;

@Component({
  selector: 'app-phase-navigation',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <nav class="phase-journey" [attr.aria-label]="'Fases del ' + identity.singular()">
      <ol>
        @for (phase of phases; track phase.id) {
          <li [class.active]="current() === phase.id" [class.complete]="current() > phase.id">
            <button type="button" [disabled]="phase.id > availableThrough()" [attr.aria-current]="current() === phase.id ? 'step' : null" (click)="navigate(phase.id)">
              <span>{{ current() > phase.id ? '✓' : phase.id }}</span>
              <span><strong>{{ phase.label }}</strong><small>{{ phase.hint }}</small></span>
            </button>
          </li>
        }
      </ol>
    </nav>
  `
})
export class PhaseNavigationComponent {
  readonly projectId = input.required<string>();
  readonly current = input.required<Phase>();
  readonly availableThrough = input<Phase>(3);
  readonly hasUnsavedChanges = input(false);
  private readonly router = inject(Router);
  readonly identity = inject(ClientIdentityService);
  readonly phases: readonly { id: Phase; label: string; hint: string }[] = [
    { id: 1, label: 'Definición de idea', hint: 'Contexto de la iniciativa' },
    { id: 2, label: 'Preparar borrador', hint: 'Fuentes, entrevista y cifras' },
    { id: 3, label: 'Revisar y finalizar', hint: 'Edición, calidad y exportación' }
  ];

  navigate(phase: Phase): void {
    if (phase === this.current() || phase > this.availableThrough()) return;
    if (this.hasUnsavedChanges() && !window.confirm('Hay información sin guardar. Si cambias de fase, se perderán esos cambios. ¿Deseas continuar?')) return;
    if (phase === 1) void this.router.navigate(['/'], { queryParams: { edit: this.projectId() } });
    if (phase === 2) void this.router.navigate(['/generate', this.projectId()], { queryParams: { step: 'sources' } });
    if (phase === 3) void this.router.navigate(['/review', this.projectId()]);
  }
}

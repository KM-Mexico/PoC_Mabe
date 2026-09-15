import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { Project, ProjectsApi } from '../../../core/api/projects.api';
import { ClientIdentityService } from '../../../core/client-identity.service';
import { BadgeComponent, BadgeTone } from '../badge/badge.component';

@Component({
  selector: 'app-project-context',
  imports: [RouterLink, BadgeComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="project-context" [attr.aria-label]="identity.singularTitle() + ' actual'">
      <div class="project-context__mark" aria-hidden="true">{{ initial() }}</div>
      <div class="project-context__identity">
        <span>{{ identity.singularTitle() }} actual</span>
        <h2>{{ project()?.name || 'Cargando proyecto…' }}</h2>
        <p>{{ project()?.organization || 'Recuperando información' }}</p>
      </div>
      <div class="project-context__meta">
        <span class="project-context__location"><span aria-hidden="true">●</span>{{ location() }}</span>
        @if (project(); as current) { <app-badge [label]="statusLabel(current.status)" [tone]="statusTone(current.status)" /> }
        <a [routerLink]="['/generate', projectId()]" [queryParams]="{ step: 'sources' }">Ver contexto</a>
      </div>
    </section>
  `
})
export class ProjectContextComponent implements OnInit {
  readonly projectId = input.required<string>();
  readonly location = input.required<string>();
  private readonly projectsApi = inject(ProjectsApi);
  private readonly destroyRef = inject(DestroyRef);
  readonly identity = inject(ClientIdentityService);
  readonly project = signal<Project | null>(null);

  ngOnInit(): void {
    this.projectsApi.get(this.projectId()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: (project) => this.project.set(project) });
  }

  initial(): string { return this.project()?.name.trim().charAt(0).toLocaleUpperCase() || 'BC'; }
  statusLabel(status: Project['status']): string { return ({ draft: 'En definición', generated: 'Borrador generado', in_review: 'En revisión', final: 'Finalizado' })[status]; }
  statusTone(status: Project['status']): BadgeTone { return ({ draft: 'neutral', generated: 'info', in_review: 'warning', final: 'success' } as const)[status]; }
}

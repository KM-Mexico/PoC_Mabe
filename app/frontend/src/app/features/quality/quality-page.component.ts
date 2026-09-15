import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, input, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { BusinessCaseVersion, GenerationApi } from '../../core/api/generation.api';
import { ClientIdentityService } from '../../core/client-identity.service';
import { ExportRecord, QualityApi, QualityValidation } from '../../core/api/quality.api';
import { BadgeComponent } from '../../shared/ui/badge/badge.component';
import { CardComponent } from '../../shared/ui/card/card.component';
import { FeedbackStateComponent } from '../../shared/ui/feedback-state/feedback-state.component';
import { ToastComponent } from '../../shared/ui/toast/toast.component';
import { PhaseNavigationComponent } from '../../shared/ui/phase-navigation/phase-navigation.component';
import { ProjectContextComponent } from '../../shared/ui/project-context/project-context.component';

@Component({
  selector: 'app-quality-page',
  imports: [DatePipe, RouterLink, BadgeComponent, CardComponent, FeedbackStateComponent, ToastComponent, PhaseNavigationComponent, ProjectContextComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <a class="back-link" [routerLink]="['/review', id()]">← Volver a revisión</a>
    <app-project-context [projectId]="id()" location="Calidad y exportación" />
    <header class="page-heading"><div><span class="eyebrow">Último paso</span><h1>Comprueba y comparte</h1><p>El agente revisa trazabilidad, consistencia, finanzas y claridad antes de preparar el documento final.</p></div>@if (version(); as current) { <app-badge [label]="current.status" /> }</header>
    <app-phase-navigation [projectId]="id()" [current]="3" [availableThrough]="3" />
    @if (message()) { <app-toast [message]="message() ?? ''" /> }
    @if (loading()) { <app-feedback-state kind="loading" title="Cargando quality gate" message="Recuperando la versión vigente." /> }
    @else if (error()) { <app-feedback-state kind="error" title="No pudimos completar la acción" [message]="error() ?? ''" /> }
    @else if (!version()) { <app-feedback-state kind="empty" title="No existe una versión" [message]="'Genera y revisa primero el ' + identity.singular() + '.'" /> }
    @else {
      <div class="quality-actions"><button type="button" class="button button--primary" (click)="runValidation()" [disabled]="working() || inspectionLocked()" [attr.title]="inspectionLocked() ? 'Esta versión ya superó 95/100. Edítala para habilitar una nueva inspección.' : null">{{ working() ? 'Validando…' : (inspectionLocked() ? 'Inspección completada' : 'Ejecutar validación integral') }}</button><button type="button" class="button button--secondary" (click)="finalizeVersion()" [disabled]="working() || !latest()?.passed || version()?.status === 'final'">Marcar como Final</button></div>
      @if (inspectionLocked() && version()?.status !== 'final') { <div class="inspection-complete" role="status"><strong>La versión ya supera 95/100</strong><p>No es necesario repetir la inspección mientras el contenido no cambie. Puedes marcarla como final o volver a revisión.</p></div> }
      @if (version()?.status === 'final') { <section class="export-ready" aria-labelledby="export-ready-title"><div><span class="export-ready__icon" aria-hidden="true">✓</span><div><span class="eyebrow">Versión final lista</span><h2 id="export-ready-title">Ya puedes exportar y compartir</h2><p>Elige el formato que mejor se adapte a tu audiencia.</p></div></div><div class="export-ready__actions"><a class="button button--primary" [href]="exportUrl('pdf')" target="_blank">Abrir vista A4 / PDF</a><a class="button button--secondary" [href]="exportUrl('markdown')">Descargar Markdown</a><a class="button button--secondary" [href]="exportUrl('json')">Descargar JSON</a></div></section> }
      @if (latest(); as validation) {
        <div class="quality-hero" [class.quality-hero--passed]="validation.passed"><div><span class="eyebrow">Score global</span><strong>{{ validation.score }}</strong><span>/100</span></div><div><h2>{{ validation.passed ? 'Gate aprobado' : 'Correcciones requeridas' }}</h2><p>Umbral {{ validation.threshold }} · {{ validation.blockers }} bloqueantes · Rúbrica {{ validation.rubric_version }}</p></div></div>
        @if (!validation.passed) { <section class="remediation-panel" aria-labelledby="remediation-title"><div><span class="eyebrow">Siguiente acción recomendada</span><h2 id="remediation-title">Corrige esta versión y vuelve a validarla</h2><p>El plan de corrección ahora está junto al editor, para que puedas resolver cada hallazgo en contexto.</p></div><div class="remediation-panel__actions">@if (needsEvidence(validation)) { <a class="button button--primary" [routerLink]="['/generate', id()]" [queryParams]="{ step: 'sources' }">Agregar fuentes y regenerar</a> }<a class="button button--secondary" [routerLink]="['/review', id()]">Revisar hallazgos y editar</a></div></section> }
        <section class="dimension-grid" aria-label="Puntuación por dimensión">@for (item of dimensions(validation); track item.name) { <app-card><span>{{ dimensionLabel(item.name) }}</span><strong>{{ item.score }}</strong><progress max="100" [value]="item.score">{{ item.score }}</progress></app-card> }</section>
        <div class="quality-records"><app-card><h2>Historial de validaciones</h2>@for (item of validations(); track item.id) { <button type="button" class="validation-history" [class.active]="latest()?.id === item.id" (click)="latest.set(item)"><strong>{{ item.score }}/100 · {{ item.passed ? 'Aprobada' : 'No aprobada' }}</strong><small>{{ item.created_at | date:'short' }}</small></button> }</app-card>
          @if (version()?.status === 'final' && exports().length) { <app-card><h2>Registro de exportaciones</h2>@for (record of exports(); track record.id) { <small class="export-record">{{ record.format }} · {{ record.created_at | date:'short' }}<br>{{ record.content_hash.slice(0, 12) }}…</small> }</app-card> }
        </div>
      } @else { <app-feedback-state kind="empty" title="Esta versión aún no fue validada" message="Ejecuta el gate integral para conocer bloqueantes y score." /> }
    }
  `
})
export class QualityPageComponent implements OnInit {
  readonly id = input.required<string>(); private readonly generationApi = inject(GenerationApi); private readonly qualityApi = inject(QualityApi); private readonly destroyRef = inject(DestroyRef); readonly identity = inject(ClientIdentityService);
  readonly version = signal<BusinessCaseVersion | null>(null); readonly validations = signal<QualityValidation[]>([]); readonly latest = signal<QualityValidation | null>(null); readonly exports = signal<ExportRecord[]>([]);
  readonly loading = signal(true); readonly working = signal(false); readonly error = signal<string | null>(null); readonly message = signal<string | null>(null);
  ngOnInit(): void { this.generationApi.versions(this.id()).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({ next: (versions) => { if (versions[0]) this.generationApi.version(versions[0].id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe((version) => { this.version.set(version); this.loadValidations(); this.loadExports(); }); }, error: () => this.error.set('Verifica que la API esté disponible.') }); }
  dimensions(validation: QualityValidation): { name: string; score: number }[] { return Object.entries(validation.dimension_scores).map(([name, score]) => ({ name, score })); }
  dimensionLabel(value: string): string { return value.replaceAll('_', ' '); }
  loadValidations(): void { const current = this.version(); if (current) this.qualityApi.validations(current.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe((items) => { this.validations.set(items); this.latest.set(items[0] ?? null); }); }
  loadExports(): void { const current = this.version(); if (current) this.qualityApi.exports(current.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe((items) => this.exports.set(items)); }
  runValidation(): void { const current = this.version(); if (!current) return; this.working.set(true); this.error.set(null); this.qualityApi.validate(current.id).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.working.set(false))).subscribe({ next: (result) => { this.message.set(result.passed ? 'Quality gate aprobado.' : 'Validación completada con correcciones requeridas.'); this.loadValidations(); }, error: () => this.error.set('No fue posible validar esta versión.') }); }
  finalizeVersion(): void { const current = this.version(); if (!current) return; this.working.set(true); this.qualityApi.finalize(current.id).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.working.set(false))).subscribe({ next: () => { this.version.set({ ...current, status: 'final' }); this.message.set('Versión finalizada y lista para exportar.'); this.loadExports(); }, error: () => this.error.set('El gate no permite finalizar: revisa bloqueantes y propuestas pendientes.') }); }
  exportUrl(format: 'json' | 'markdown' | 'pdf'): string { const current = this.version(); return current ? this.qualityApi.exportUrl(current.id, format) : '#'; }
  inspectionLocked(): boolean { return (this.validations()[0]?.score ?? 0) > 95; }
  needsEvidence(validation: QualityValidation): boolean { return validation.findings.some((finding) => finding.dimension === 'evidencia_trazabilidad'); }
}

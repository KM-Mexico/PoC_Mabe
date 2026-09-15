import { HttpErrorResponse, HttpEventType } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, OnInit, ViewChild, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { DocumentsApi, EvidenceChunk, SourceDocument, UploadBatch } from '../../core/api/documents.api';
import { AgentInterview, InterviewApi } from '../../core/api/interview.api';
import { ClientIdentityService } from '../../core/client-identity.service';
import { Project, ProjectsApi } from '../../core/api/projects.api';
import { BadgeComponent } from '../../shared/ui/badge/badge.component';
import { ButtonComponent } from '../../shared/ui/button/button.component';
import { CardComponent } from '../../shared/ui/card/card.component';
import { ConfirmDialogComponent } from '../../shared/ui/confirm-dialog/confirm-dialog.component';
import { DataTableComponent } from '../../shared/ui/data-table/data-table.component';
import { FeedbackStateComponent } from '../../shared/ui/feedback-state/feedback-state.component';
import { FileDropzoneComponent } from '../../shared/ui/file-dropzone/file-dropzone.component';
import { ToastComponent } from '../../shared/ui/toast/toast.component';
import { ToggleComponent } from '../../shared/ui/toggle/toggle.component';
import { PhaseNavigationComponent } from '../../shared/ui/phase-navigation/phase-navigation.component';
import { ProjectContextComponent } from '../../shared/ui/project-context/project-context.component';
import { CaseGenerationPanelComponent } from './case-generation-panel.component';

type PreparationStep = 'sources' | 'interview' | 'financial';

const ALLOWED_EXTENSIONS = ['.txt', '.md', '.pdf', '.xlsx'];
const MAX_FILE_BYTES = 15 * 1024 * 1024;
const MAX_BATCH_BYTES = 50 * 1024 * 1024;
const PREPARATION_STEPS: PreparationStep[] = ['sources', 'interview', 'financial'];
const STATUS_LABELS: Record<SourceDocument['status'], string> = { pending: 'Pendiente', processing: 'Procesando', ready: 'Listo', error: 'Error', requires_ocr: 'Requiere OCR' };

@Component({
  selector: 'app-generation-page',
  imports: [RouterLink, BadgeComponent, ButtonComponent, CardComponent, ConfirmDialogComponent, DataTableComponent, FeedbackStateComponent, FileDropzoneComponent, ToastComponent, ToggleComponent, PhaseNavigationComponent, ProjectContextComponent, CaseGenerationPanelComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="guided-header">
      <div class="guided-header__top"><a class="back-link" routerLink="/">← Mis {{ identity.plural() }}</a><span class="autosave-note">✓ Información guardada</span></div>
      <app-project-context [projectId]="id()" location="Preparar borrador" />
      <header class="page-heading workspace-heading"><div><span class="eyebrow">Construcción guiada</span><h1>Prepara tu borrador</h1><p>Completa una tarea a la vez. Siempre sabrás dónde estás y qué sigue.</p></div></header>
      <app-phase-navigation [projectId]="id()" [current]="2" [availableThrough]="availablePhase()" [hasUnsavedChanges]="selectedFiles().length > 0 || financialChangesPending()" />
    </div>

    @if (successMessage()) { <app-toast [message]="successMessage() ?? ''" /> }

    <div class="preparation-shell">
      <main class="preparation-main">
        <nav class="prepare-stepper" aria-label="Pasos para preparar el borrador">
          <button type="button" [class.active]="activeStep() === 'sources'" [class.complete]="sourceStepComplete()" [attr.aria-current]="activeStep() === 'sources' ? 'step' : null" (click)="goToStep('sources')"><span>{{ sourceStepComplete() ? '✓' : '1' }}</span><div><strong>Fuentes</strong><small>{{ readyDocuments().length }} listas</small></div></button>
          <button type="button" [class.active]="activeStep() === 'interview'" [class.complete]="interviewStepComplete()" [attr.aria-current]="activeStep() === 'interview' ? 'step' : null" (click)="goToStep('interview')"><span>{{ interviewStepComplete() ? '✓' : '2' }}</span><div><strong>Entrevista</strong><small>{{ interviewStatusLabel() }}</small></div></button>
          <button type="button" [class.active]="activeStep() === 'financial'" [attr.aria-current]="activeStep() === 'financial' ? 'step' : null" (click)="goToStep('financial')"><span>3</span><div><strong>Finanzas</strong><small>Generar borrador</small></div></button>
        </nav>

        <section class="step-workspace" [attr.data-step]="activeStep()">
          @if (activeStep() === 'sources') {
            <header class="step-heading"><div><span class="eyebrow">Paso 1 de 3 · Fuentes</span><h2 id="workspace-step-title" tabindex="-1">Selecciona la evidencia que leerá el agente</h2><p>Adjunta información útil y confirma qué fragmentos deben respaldar el {{ identity.singular() }}.</p></div><span class="count">{{ documents().length }}/10</span></header>
            <div class="agent-tip" role="note"><span class="agent-orb" aria-hidden="true">✦</span><div><strong>Más contexto produce un mejor resultado</strong><p>Cuanta más información relevante compartas, mejor podrá el agente contrastar supuestos, detectar vacíos y redactar un caso defendible. La calidad importa más que la cantidad.</p></div></div>
            @if (project()?.status !== 'draft') { <div class="source-update-notice" role="status"><strong>Estás corrigiendo un borrador existente</strong><p>Las fuentes que agregues se aplicarán al crear una nueva versión. Después de subirlas, continúa por Entrevista y Finanzas hasta “Crear nueva versión corregida”.</p></div> }
            <div class="privacy-notice" role="note"><strong>Información protegida</strong><p>Los archivos permanecen en el backend privado y sólo se muestra aquí el texto extraído para su revisión.</p></div>
            <app-card>
              <div class="section-heading"><div><span class="eyebrow">Agregar fuentes</span><h3>Sube lo que ya tengas</h3></div></div>
              <app-file-dropzone [files]="selectedFiles()" (selected)="addFiles($event)" (removed)="removeFile($event)" />
              @if (selectionError()) { <p class="form-error" role="alert">{{ selectionError() }}</p> }
              <div class="upload-actions"><small>TXT, MD, PDF o XLSX · 15 MiB por archivo.</small><app-button [disabled]="uploading() || selectedFiles().length === 0" (pressed)="uploadFiles()">{{ uploading() ? 'Procesando…' : 'Subir y procesar' }}</app-button></div>
              @if (uploading()) { <div class="upload-progress" role="status"><label for="upload-progress">Progreso: {{ progress() }}%</label><progress id="upload-progress" max="100" [value]="progress()"></progress></div> }
              @if (uploadResults().length) { <ul class="upload-results" aria-label="Resultado de la carga">@for (result of uploadResults(); track result.file_name) { <li [class.result-error]="!result.accepted"><strong>{{ result.file_name }}</strong><span>{{ result.accepted ? 'Procesado correctamente' : result.message }}</span></li> }</ul> }
            </app-card>

            <section class="source-library" aria-labelledby="documents-title">
              <div class="section-heading"><div><span class="eyebrow">Biblioteca</span><h3 id="documents-title">Fuentes disponibles</h3></div></div>
              @if (documents().length) { <div class="list-toolbar"><label class="visually-hidden" for="document-search">Buscar documentos</label><input id="document-search" type="search" placeholder="Buscar por nombre" [value]="documentSearch()" (input)="setDocumentSearch($event)"><label class="visually-hidden" for="document-status">Filtrar por estado</label><select id="document-status" [value]="documentStatus()" (change)="setDocumentStatus($event)"><option value="">Todos los estados</option><option value="ready">Listos</option><option value="requires_ocr">Requieren OCR</option><option value="error">Con error</option></select></div> }
              @if (loading()) { <app-feedback-state kind="loading" title="Cargando fuentes" message="Consultando la evidencia local." /> }
              @else if (loadError()) { <app-feedback-state kind="error" title="No pudimos cargar las fuentes" [message]="loadError() ?? ''" /><app-button variant="secondary" (pressed)="loadDocuments()">Reintentar</app-button> }
              @else if (!documents().length) { <app-feedback-state kind="empty" title="Aún no hay evidencia" message="Puedes continuar sin fuentes; el agente marcará la información no respaldada." /> }
              @else if (!filteredDocuments().length) { <app-feedback-state kind="empty" title="Sin coincidencias" message="Ajusta la búsqueda o el filtro de estado." /> }
              @else {
                <app-data-table><table><thead><tr><th>Documento</th><th>Estado</th><th>Uso</th><th>Acciones</th></tr></thead><tbody>@for (document of pagedDocuments(); track document.id) { <tr [class.selected-row]="selectedDocument()?.id === document.id"><td><button type="button" class="table-link" [disabled]="document.status !== 'ready'" [attr.aria-label]="'Abrir fuente ' + document.original_name" (click)="selectDocument(document)">{{ document.original_name }}</button><small>{{ document.chunk_count }} fragmentos · {{ formatSize(document.byte_size) }}</small></td><td><app-badge [label]="statusLabel(document.status)" /></td><td><app-toggle [checked]="document.included" [disabled]="document.status !== 'ready'" [label]="'Incluir ' + document.original_name" (toggled)="toggleDocument(document, $event)" /></td><td><app-button variant="ghost" (pressed)="requestDelete(document)">Eliminar</app-button></td></tr> }</tbody></table></app-data-table>
                <nav class="pagination" aria-label="Paginación de documentos"><button type="button" (click)="previousDocumentPage()" [disabled]="documentPage() === 1">Anterior</button><span>Página {{ documentPage() }} de {{ documentTotalPages() }}</span><button type="button" (click)="nextDocumentPage()" [disabled]="documentPage() === documentTotalPages()">Siguiente</button></nav>
              }
            </section>

          } @else if (activeStep() === 'interview') {
            <header class="step-heading"><div><span class="eyebrow">Paso 2 de 3 · Entrevista</span><h2 id="workspace-step-title" tabindex="-1">Fortalece el caso con el agente</h2><p>El agente usa las fuentes disponibles y pregunta únicamente lo que no debe inferir.</p></div></header>
            <app-case-generation-panel [projectId]="id()" mode="interview" (interviewUpdated)="setInterview($event)" />
          } @else {
            <header class="step-heading"><div><span class="eyebrow">Paso 3 de 3 · Finanzas</span><h2 id="workspace-step-title" tabindex="-1">Completa las cifras y genera</h2><p>Revisa la estimación final antes de construir el primer borrador.</p></div></header>
            <app-case-generation-panel [projectId]="id()" mode="financial" (interviewUpdated)="setInterview($event)" (financialDirty)="financialChangesPending.set($event)" />
          }
        </section>

        @if (activeStep() !== 'financial') {
          <footer class="workspace-actions"><app-button variant="secondary" [disabled]="activeStep() === 'sources'" (pressed)="previousStep()">Atrás</app-button><div><small>{{ nextActionHint() }}</small><app-button (pressed)="nextStep()">Continuar</app-button></div></footer>
        }
      </main>

      <aside class="workspace-summary" aria-label="Resumen del proyecto"><app-card><span class="eyebrow">Tu {{ identity.singular() }}</span><h2>{{ project()?.name || 'Cargando…' }}</h2><p>{{ project()?.organization }}</p><dl><div><dt>Decisión</dt><dd>{{ project()?.setup?.decision || 'Sin definir' }}</dd></div><div><dt>Fuentes activas</dt><dd>{{ readyDocuments().length }}</dd></div><div><dt>Entrevista</dt><dd>{{ interviewStatusLabel() }}</dd></div><div><dt>Horizonte</dt><dd>{{ project()?.horizon_years || '—' }} años · {{ project()?.currency || '—' }}</dd></div></dl><div class="summary-next"><strong>Ahora</strong><span>{{ activeStepLabel() }}</span></div></app-card></aside>
    </div>
    <dialog #sourceDialog class="source-dialog" aria-labelledby="preview-title" (close)="closePreview()"><div class="source-dialog__heading"><div><span class="eyebrow">Vista de la fuente</span><h2 id="preview-title">{{ selectedDocument()?.original_name }}</h2><p>Texto extraído que utilizará el agente.</p></div><button type="button" class="icon-button" aria-label="Cerrar fuente" (click)="closePreview()">×</button></div>@if (chunksLoading()) { <app-feedback-state kind="loading" title="Cargando fragmentos" message="Preparando la vista trazable." /> } @else if (!chunks().length) { <app-feedback-state kind="empty" title="Sin fragmentos" message="Este documento no produjo texto consultable." /> } @else { <div class="chunk-list">@for (chunk of chunks(); track chunk.id) { <article class="chunk"><div class="chunk__heading"><span>{{ chunkReference(chunk) }}</span><app-toggle [checked]="chunk.included" [label]="'Incluir fragmento ' + (chunk.ordinal + 1)" (toggled)="toggleChunk(chunk, $event)" /></div><pre>{{ chunk.content }}</pre></article> }</div> }</dialog>
    <app-confirm-dialog #deleteDialog title="Eliminar documento" description="Se eliminarán el binario local y todos sus fragmentos. Esta acción no puede deshacerse." confirmLabel="Eliminar fuente" (confirmed)="deleteSelected()" />
  `
})
export class GenerationPageComponent implements OnInit {
  @ViewChild('deleteDialog') private deleteDialog?: ConfirmDialogComponent;
  @ViewChild('sourceDialog') private sourceDialog?: ElementRef<HTMLDialogElement>;
  readonly id = input.required<string>();
  private readonly documentsApi = inject(DocumentsApi);
  private readonly projectsApi = inject(ProjectsApi);
  private readonly interviewApi = inject(InterviewApi);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly identity = inject(ClientIdentityService);
  readonly activeStep = signal<PreparationStep>('sources');
  readonly project = signal<Project | null>(null);
  readonly interview = signal<AgentInterview | null>(null);
  readonly financialChangesPending = signal(false);
  readonly selectedFiles = signal<readonly File[]>([]);
  readonly documents = signal<SourceDocument[]>([]);
  readonly selectedDocument = signal<SourceDocument | null>(null);
  readonly chunks = signal<EvidenceChunk[]>([]);
  readonly uploadResults = signal<UploadBatch['items']>([]);
  readonly loading = signal(true);
  readonly chunksLoading = signal(false);
  readonly uploading = signal(false);
  readonly progress = signal(0);
  readonly selectionError = signal<string | null>(null);
  readonly loadError = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);
  readonly documentSearch = signal('');
  readonly documentStatus = signal('');
  readonly documentPage = signal(1);
  readonly readyDocuments = computed(() => this.documents().filter((document) => document.status === 'ready' && document.included));
  readonly sourceStepComplete = computed(() => !this.loading());
  readonly interviewStepComplete = computed(() => (this.interview()?.analysis_count ?? 0) > 0);
  readonly filteredDocuments = computed(() => { const term = this.documentSearch().trim().toLocaleLowerCase(); return this.documents().filter((document) => (!term || document.original_name.toLocaleLowerCase().includes(term)) && (!this.documentStatus() || document.status === this.documentStatus())); });
  readonly documentTotalPages = computed(() => Math.max(1, Math.ceil(this.filteredDocuments().length / 5)));
  readonly pagedDocuments = computed(() => this.filteredDocuments().slice((this.documentPage() - 1) * 5, this.documentPage() * 5));
  private selectedForDelete: SourceDocument | null = null;

  ngOnInit(): void {
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => { const requested = params.get('step') as PreparationStep | null; this.activeStep.set(requested && PREPARATION_STEPS.includes(requested) ? requested : 'sources'); });
    this.projectsApi.get(this.id()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: (project) => this.project.set(project), error: () => this.loadError.set('No pudimos cargar la información del proyecto.') });
    this.interviewApi.get(this.id()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: (interview) => this.interview.set(interview), error: () => this.interview.set(null) });
    this.loadDocuments();
  }

  goToStep(step: PreparationStep): void {
    if (step === this.activeStep()) return;
    this.activeStep.set(step);
    void this.router.navigate([], { relativeTo: this.route, queryParams: { step }, queryParamsHandling: 'merge', replaceUrl: true });
    setTimeout(() => document.getElementById('workspace-step-title')?.focus());
  }
  previousStep(): void { const index = PREPARATION_STEPS.indexOf(this.activeStep()); if (index > 0) this.goToStep(PREPARATION_STEPS[index - 1]); }
  nextStep(): void { const index = PREPARATION_STEPS.indexOf(this.activeStep()); if (index < PREPARATION_STEPS.length - 1) this.goToStep(PREPARATION_STEPS[index + 1]); }
  activeStepLabel(): string { return { sources: 'Seleccionar fuentes', interview: 'Responder al agente', financial: 'Completar finanzas' }[this.activeStep()]; }
  nextActionHint(): string { return this.activeStep() === 'sources' ? 'Las fuentes son opcionales; podrás volver después.' : 'Podrás generar incluso si quedan datos pendientes.'; }
  interviewStatusLabel(): string { const interview = this.interview(); if (!interview) return 'Pendiente'; return interview.status === 'ready' ? 'Contexto suficiente' : `${interview.answers ? Object.keys(interview.answers).length : 0} respuestas`; }
  availablePhase(): 2 | 3 { return this.project()?.status === 'draft' ? 2 : 3; }
  setInterview(interview: AgentInterview): void { this.interview.set(interview); }

  loadDocuments(): void {
    this.loading.set(true); this.loadError.set(null);
    this.documentsApi.list(this.id()).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({ next: (documents) => { this.documents.set(documents); const selected = this.selectedDocument(); if (selected) this.selectedDocument.set(documents.find((item) => item.id === selected.id) ?? null); }, error: () => this.loadError.set('Verifica que la API esté disponible e intenta de nuevo.') });
  }
  addFiles(files: File[]): void {
    this.selectionError.set(null); const combined = [...this.selectedFiles(), ...files];
    const invalidType = combined.find((file) => !ALLOWED_EXTENSIONS.some((extension) => file.name.toLowerCase().endsWith(extension))); if (invalidType) { this.selectionError.set(`${invalidType.name}: formato no soportado.`); return; }
    const oversized = combined.find((file) => file.size > MAX_FILE_BYTES); if (oversized) { this.selectionError.set(`${oversized.name}: excede el máximo de 15 MiB.`); return; }
    if (combined.length + this.documents().length > 10) { this.selectionError.set('Un proyecto puede contener como máximo 10 documentos.'); return; }
    if (combined.reduce((total, file) => total + file.size, 0) > MAX_BATCH_BYTES) { this.selectionError.set('El lote excede el máximo de 50 MiB.'); return; }
    this.selectedFiles.set(combined);
  }
  removeFile(index: number): void { this.selectedFiles.update((files) => files.filter((_, current) => current !== index)); this.selectionError.set(null); }
  uploadFiles(): void {
    if (!this.selectedFiles().length || this.uploading()) return;
    this.uploading.set(true); this.progress.set(0); this.uploadResults.set([]); this.successMessage.set(null); this.selectionError.set(null);
    this.documentsApi.upload(this.id(), this.selectedFiles()).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.uploading.set(false))).subscribe({
      next: (event) => { if (event.type === HttpEventType.UploadProgress && event.total) this.progress.set(Math.round((event.loaded / event.total) * 100)); if (event.type === HttpEventType.Response && event.body) { this.progress.set(100); this.uploadResults.set(event.body.items); this.selectedFiles.set([]); this.successMessage.set(event.body.rejected_count ? `${event.body.accepted_count} archivos procesados; ${event.body.rejected_count} rechazados.` : `${event.body.accepted_count} archivos procesados correctamente.`); this.loadDocuments(); } },
      error: (response: HttpErrorResponse) => { const batch = this.uploadErrorBatch(response); if (batch) this.uploadResults.set(batch.items); this.selectionError.set(this.uploadErrorMessage(response, batch)); }
    });
  }
  private uploadErrorBatch(response: HttpErrorResponse): UploadBatch | null { const value: unknown = response.error; if (!value || typeof value !== 'object' || !('items' in value) || !Array.isArray((value as UploadBatch).items)) return null; return value as UploadBatch; }
  private uploadErrorMessage(response: HttpErrorResponse, batch: UploadBatch | null): string { const rejected = batch?.items.filter((item) => !item.accepted).map((item) => `${item.file_name}: ${item.message || 'no se pudo procesar'}`); if (rejected?.length) return rejected.join(' · '); if (response.status === 413) return 'El lote supera el límite permitido de 50 MiB o 10 documentos.'; if (response.status === 0) return 'No se pudo conectar con la API. Verifica que el servicio esté disponible.'; return `No fue posible procesar el lote (HTTP ${response.status}). Intenta de nuevo.`; }
  selectDocument(document: SourceDocument): void { this.selectedDocument.set(document); this.chunks.set([]); if (document.status !== 'ready') return; this.chunksLoading.set(true); this.sourceDialog?.nativeElement.showModal(); this.documentsApi.chunks(document.id).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.chunksLoading.set(false))).subscribe({ next: (chunks) => this.chunks.set(chunks), error: () => this.loadError.set('No fue posible cargar los fragmentos del documento.') }); }
  closePreview(): void { if (this.sourceDialog?.nativeElement.open) this.sourceDialog.nativeElement.close(); this.selectedDocument.set(null); this.chunks.set([]); }
  toggleDocument(document: SourceDocument, included: boolean): void { this.documentsApi.setDocumentIncluded(document.id, included).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: (updated) => { this.documents.update((documents) => documents.map((item) => item.id === updated.id ? updated : item)); if (this.selectedDocument()?.id === updated.id) this.selectedDocument.set(updated); }, error: () => this.loadError.set('No fue posible guardar la selección del documento.') }); }
  toggleChunk(chunk: EvidenceChunk, included: boolean): void { this.documentsApi.setChunkIncluded(chunk.id, included).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: (updated) => this.chunks.update((chunks) => chunks.map((item) => item.id === updated.id ? updated : item)), error: () => this.loadError.set('No fue posible guardar la selección del fragmento.') }); }
  requestDelete(document: SourceDocument): void { this.selectedForDelete = document; this.deleteDialog?.open(); }
  deleteSelected(): void { const document = this.selectedForDelete; if (!document) return; this.documentsApi.delete(document.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: () => { this.documents.update((documents) => documents.filter((item) => item.id !== document.id)); if (this.selectedDocument()?.id === document.id) this.closePreview(); this.successMessage.set('Documento y fragmentos eliminados localmente.'); }, error: () => this.loadError.set('No fue posible eliminar el documento.') }); this.selectedForDelete = null; }
  statusLabel(status: SourceDocument['status']): string { return STATUS_LABELS[status]; }
  setDocumentSearch(event: Event): void { this.documentSearch.set((event.target as HTMLInputElement).value); this.documentPage.set(1); }
  setDocumentStatus(event: Event): void { this.documentStatus.set((event.target as HTMLSelectElement).value); this.documentPage.set(1); }
  previousDocumentPage(): void { this.documentPage.update((value) => Math.max(1, value - 1)); }
  nextDocumentPage(): void { this.documentPage.update((value) => Math.min(this.documentTotalPages(), value + 1)); }
  formatSize(bytes: number): string { if (bytes < 1024) return `${bytes} B`; if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`; return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`; }
  chunkReference(chunk: EvidenceChunk): string { if (chunk.page_number) return `Página ${chunk.page_number}`; if (chunk.sheet_name) return `${chunk.sheet_name} · ${chunk.cell_range ?? 'rango no disponible'}`; return `Fragmento ${chunk.ordinal + 1}`; }
}

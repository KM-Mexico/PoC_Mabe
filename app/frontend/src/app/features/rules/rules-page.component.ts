import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, ViewChild, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize } from 'rxjs';
import { RuleDetail, RuleSummary, RulesApi } from '../../core/api/rules.api';
import { BadgeComponent } from '../../shared/ui/badge/badge.component';
import { ButtonComponent } from '../../shared/ui/button/button.component';
import { CardComponent } from '../../shared/ui/card/card.component';
import { ConfirmDialogComponent } from '../../shared/ui/confirm-dialog/confirm-dialog.component';
import { DataTableComponent } from '../../shared/ui/data-table/data-table.component';
import { FeedbackStateComponent } from '../../shared/ui/feedback-state/feedback-state.component';
import { ToastComponent } from '../../shared/ui/toast/toast.component';
import { MarkdownPreviewComponent } from '../../shared/ui/markdown-preview/markdown-preview.component';

@Component({
  selector: 'app-rules-page',
  imports: [FormsModule, DatePipe, BadgeComponent, ButtonComponent, CardComponent, ConfirmDialogComponent, DataTableComponent, FeedbackStateComponent, ToastComponent, MarkdownPreviewComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="page-heading"><div><span class="eyebrow">Configuración avanzada</span><h1>Guía editorial del agente</h1><p>Administra los criterios que el agente debe seguir al construir cada sección. Esta configuración normalmente no requiere cambios.</p></div></header>
    <div class="privacy-notice" role="note"><strong>Configuración protegida</strong><p>Los cambios se guardan como borrador y sólo se aplican después de validarlos y publicarlos. Los documentos ya generados no cambian.</p></div>
    @if (message()) { <app-toast [message]="message() ?? ''" /> }
    @if (loading()) { <app-feedback-state kind="loading" title="Cargando reglas" message="Validando cobertura y versiones publicadas." /> }
    @else if (error()) { <app-feedback-state kind="error" title="No pudimos cargar las reglas" [message]="error() ?? ''" /> }
    @else {
      <div class="rules-layout">
        <nav class="rules-nav" aria-label="Secciones de reglas">
          <label class="visually-hidden" for="rule-search">Buscar reglas</label><input id="rule-search" type="search" placeholder="Buscar sección" [value]="ruleSearch()" (input)="setRuleSearch($event)">
          @for (rule of filteredRules(); track rule.section_id) {
            <button type="button" [class.active]="selected()?.section_id === rule.section_id" (click)="select(rule)"><span>{{ rule.title }}</span><small>Publicada v{{ rule.published_version }} @if (rule.draft_version) { · Borrador v{{ rule.draft_version }} }</small></button>
          }
        </nav>
        <div class="rules-workspace">
          @if (selected(); as rule) {
            <app-card>
              <div class="section-heading"><div><span class="eyebrow">{{ rule.section_id }}</span><h2>{{ rule.title }}</h2></div><app-badge [label]="rule.draft_version ? 'Borrador' : 'Publicada'" /></div>
              <div class="workspace-tabs" role="tablist" aria-label="Vista de la regla"><button type="button" role="tab" [attr.aria-selected]="activeTab() === 'editor'" [class.active]="activeTab() === 'editor'" (click)="activeTab.set('editor')">Editor</button><button type="button" role="tab" [attr.aria-selected]="activeTab() === 'preview'" [class.active]="activeTab() === 'preview'" (click)="activeTab.set('preview')">Vista previa</button><button type="button" role="tab" [attr.aria-selected]="activeTab() === 'history'" [class.active]="activeTab() === 'history'" (click)="activeTab.set('history')">Historial</button></div>
              @if (activeTab() === 'editor') { <div class="rule-panel" role="tabpanel"><label for="rule-markdown">Regla Markdown</label><textarea id="rule-markdown" class="rule-editor" [ngModel]="markdown()" (ngModelChange)="markdown.set($event)" [disabled]="saving()" spellcheck="false"></textarea>@if (validationErrors().length) { <div class="rule-errors" role="alert"><strong>La regla no puede publicarse:</strong><ul>@for (item of validationErrors(); track item) { <li>{{ item }}</li> }</ul></div> }<div class="rule-actions"><app-button variant="secondary" [disabled]="saving()" (pressed)="saveDraft()">Guardar borrador</app-button><app-button variant="secondary" [disabled]="!rule.draft_version || saving()" (pressed)="validateDraft()">Validar</app-button><app-button [disabled]="!rule.draft_version || saving()" (pressed)="publishDraft()">Publicar versión</app-button><app-button variant="ghost" (pressed)="restoreDialog.open()">Restaurar default</app-button></div></div> }
              @if (activeTab() === 'preview') { <div class="rule-panel rule-preview-panel" role="tabpanel"><div class="rule-preview-heading"><div><span class="eyebrow">Vista renderizada</span><h3>Así interpreta la estructura el agente</h3><p>La sintaxis Markdown se presenta como documento. El HTML permanece visible como texto y nunca se ejecuta.</p></div><app-badge label="Previsualización segura" tone="success" /></div><div class="rule-preview-canvas"><app-markdown-preview [markdown]="markdown()" /></div></div> }
              @if (activeTab() === 'history') { <div class="rule-panel" role="tabpanel"><app-data-table><table><thead><tr><th>Versión</th><th>Estado</th><th>Actor</th><th>Fecha</th></tr></thead><tbody>@for (version of pagedHistory(); track version.id) { <tr><td>v{{ version.version_number }}</td><td>{{ version.status }}</td><td>{{ version.actor }}</td><td>{{ version.created_at | date:'short' }}</td></tr> }</tbody></table></app-data-table><nav class="pagination" aria-label="Paginación del historial"><button type="button" (click)="previousHistoryPage()" [disabled]="historyPage() === 1">Anterior</button><span>Página {{ historyPage() }} de {{ historyTotalPages() }}</span><button type="button" (click)="nextHistoryPage()" [disabled]="historyPage() === historyTotalPages()">Siguiente</button></nav></div> }
            </app-card>
          }
        </div>
      </div>
    }
    <app-confirm-dialog #restoreDialog title="Restaurar regla predeterminada" description="Se publicará una nueva versión basada en el Markdown predeterminado. El historial existente se conservará." confirmLabel="Restaurar y publicar" (confirmed)="restoreDefault()" />
  `
})
export class RulesPageComponent implements OnInit {
  @ViewChild('restoreDialog') readonly restoreDialog!: ConfirmDialogComponent;
  private readonly api = inject(RulesApi);
  private readonly destroyRef = inject(DestroyRef);
  private detailRequest = 0;
  readonly rules = signal<RuleSummary[]>([]); readonly detail = signal<RuleDetail | null>(null); readonly selected = signal<RuleSummary | null>(null);
  readonly loading = signal(true); readonly saving = signal(false); readonly error = signal<string | null>(null); readonly message = signal<string | null>(null); readonly validationErrors = signal<string[]>([]);
  readonly activeTab = signal<'editor' | 'preview' | 'history'>('editor'); readonly ruleSearch = signal(''); readonly historyPage = signal(1);
  readonly filteredRules = computed(() => { const term = this.ruleSearch().trim().toLocaleLowerCase(); return this.rules().filter((rule) => !term || `${rule.title} ${rule.section_id}`.toLocaleLowerCase().includes(term)); });
  readonly historyTotalPages = computed(() => Math.max(1, Math.ceil((this.detail()?.versions.length ?? 0) / 5)));
  readonly pagedHistory = computed(() => (this.detail()?.versions ?? []).slice((this.historyPage() - 1) * 5, this.historyPage() * 5));
  readonly markdown = signal('');

  ngOnInit(): void { this.load(); }
  load(sectionId?: string): void {
    this.loading.set(true);
    this.api.list().pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({ next: (rules) => { this.rules.set(rules); const selected = rules.find((item) => item.section_id === sectionId) ?? rules[0]; if (selected) this.select(selected); }, error: () => this.error.set('Verifica que la API esté disponible.') });
  }
  select(rule: RuleSummary): void {
    const request = ++this.detailRequest;
    this.selected.set(rule); this.detail.set(null); this.markdown.set(''); this.validationErrors.set([]); this.historyPage.set(1);
    this.api.detail(rule.section_id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: (detail) => { if (request !== this.detailRequest) return; this.detail.set(detail); const draft = detail.versions.find((version) => version.status === 'draft'); this.markdown.set((draft ?? detail.published)?.markdown ?? ''); }, error: () => { if (request === this.detailRequest) this.error.set('No fue posible abrir la regla.'); } });
  }
  saveDraft(): void {
    const rule = this.selected(); if (!rule) return; this.saving.set(true); this.validationErrors.set([]);
    const request = rule.draft_version ? this.api.updateDraft(rule.section_id, rule.draft_version, this.markdown()) : this.api.createDraft(rule.section_id, this.markdown());
    request.pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({ next: () => { this.message.set('Borrador guardado. Las generaciones publicadas no cambiaron.'); this.load(rule.section_id); }, error: () => this.error.set('No fue posible guardar el borrador.') });
  }
  validateDraft(): void { const rule = this.selected(); if (!rule?.draft_version) return; this.api.validate(rule.section_id, rule.draft_version).pipe(takeUntilDestroyed(this.destroyRef)).subscribe((result) => { this.validationErrors.set(result.errors); this.message.set(result.valid ? 'Regla válida y lista para publicar.' : null); }); }
  publishDraft(): void { const rule = this.selected(); if (!rule?.draft_version) return; this.saving.set(true); this.api.publish(rule.section_id, rule.draft_version).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({ next: () => { this.message.set('Nueva versión publicada.'); this.load(rule.section_id); }, error: (response: { error?: { detail?: { errors?: string[] } } }) => this.validationErrors.set(response.error?.detail?.errors ?? ['La regla no pudo publicarse.']) }); }
  restoreDefault(): void { const rule = this.selected(); if (!rule) return; this.api.restore(rule.section_id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: () => { this.message.set('Default restaurado como una nueva versión publicada.'); this.load(rule.section_id); }, error: () => this.error.set('No fue posible restaurar la regla.') }); }
  setRuleSearch(event: Event): void { this.ruleSearch.set((event.target as HTMLInputElement).value); }
  previousHistoryPage(): void { this.historyPage.update((value) => Math.max(1, value - 1)); }
  nextHistoryPage(): void { this.historyPage.update((value) => Math.min(this.historyTotalPages(), value + 1)); }
}

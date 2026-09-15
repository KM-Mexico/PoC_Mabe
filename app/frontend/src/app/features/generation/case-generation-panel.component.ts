import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, OnInit, ViewChild, computed, inject, input, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { finalize, of, switchMap } from 'rxjs';
import { GenerationApi, GenerationInput } from '../../core/api/generation.api';
import { AgentInterview, InterviewApi } from '../../core/api/interview.api';
import { ClientIdentityService } from '../../core/client-identity.service';
import { Project, ProjectsApi } from '../../core/api/projects.api';
import { ButtonComponent } from '../../shared/ui/button/button.component';
import { FormFieldComponent } from '../../shared/ui/form-field/form-field.component';

@Component({
  selector: 'app-case-generation-panel',
  imports: [ReactiveFormsModule, ButtonComponent, FormFieldComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (mode() === 'interview') {
      <section class="assistant-interview interview-launcher" aria-labelledby="generation-title">
        <div class="assistant-message assistant-message--compact"><span class="agent-orb" aria-hidden="true">✦</span><div><span class="eyebrow">Entrevista guiada</span><h2 id="generation-title">Completa sólo la información que falta</h2><p>La entrevista se abre en una ventana dedicada para mantener visibles su alcance, temas y avance.</p></div></div>
        @if (loadingAgent()) { <div class="agent-loading" role="status"><span class="agent-orb" aria-hidden="true">✦</span><div><strong>Preparando la entrevista…</strong><small>Contrastando tus fuentes antes de definir las preguntas necesarias.</small></div></div> }
        @else if (interview(); as session) { <div class="interview-launcher__status"><div><span class="eyebrow">Plan de entrevista</span><h3>{{ session.status === 'ready' ? 'Entrevista completada' : session.remaining_question_count + (session.remaining_question_count === 1 ? ' pregunta pendiente' : ' preguntas pendientes') }}</h3><p>{{ interviewScope() }}</p><div class="interview-topic-list">@for (topic of session.topics; track topic) { <span>{{ categoryLabel(topic) }}</span> } @empty { <span>Sin temas pendientes</span> }</div></div><div class="interview-launcher__action"><strong>{{ session.answered_count }}/{{ session.total_question_count }}</strong><span>respondidas</span><button type="button" class="button button--primary" (click)="openInterview()">{{ session.status === 'ready' ? 'Ver diagnóstico' : (session.answered_count ? 'Continuar entrevista' : 'Iniciar entrevista') }}</button></div></div> }
        @if (agentError()) { <p class="form-error" role="alert">{{ agentError() }}</p> }
      </section>
      <dialog #interviewDialog class="interview-dialog" aria-labelledby="interview-dialog-title" (close)="closeInterview()">
        @if (interview(); as session) {
          <header class="interview-dialog__header"><div><span class="eyebrow">Entrevista del {{ identity.singular() }}</span><h2 id="interview-dialog-title">{{ session.status === 'ready' ? 'Diagnóstico completado' : 'Pregunta ' + currentQuestionNumber() + ' de ' + session.total_question_count }}</h2><p>{{ interviewScope() }}</p><div class="interview-topic-list">@for (topic of session.topics; track topic) { <span>{{ categoryLabel(topic) }}</span> }</div></div><button type="button" class="icon-button" aria-label="Cerrar entrevista" (click)="closeInterview()">×</button><progress max="100" [value]="interviewProgress()" aria-label="Progreso de la entrevista">{{ interviewProgress() }}%</progress></header>
          <div class="interview-dialog__body">
            <div class="agent-assessment"><div class="assessment-summary"><div><span class="eyebrow">Diagnóstico del agente</span><p>{{ identity.adapt(session.summary) }}</p></div><div [class]="'readiness-score ' + readinessClass()"><strong>{{ session.readiness_score }}%</strong><span>{{ readinessLevel() }}</span><progress max="100" [value]="session.readiness_score" [attr.aria-label]="'Preparación del ' + identity.singular()">{{ session.readiness_score }}%</progress></div></div><div class="assessment-columns"><div><strong>Ya está sustentado</strong><ul>@for (strength of session.strengths; track strength) { <li>{{ identity.adapt(strength) }}</li> }</ul></div><div><strong>Información por fortalecer</strong><ul>@for (gap of session.gaps; track gap) { <li>{{ identity.adapt(gap) }}</li> }</ul></div></div><button type="button" class="agent-refresh" (click)="reanalyze()" [disabled]="agentBusy()">↻ Reanalizar con las fuentes actuales</button></div>
            @if (session.status === 'ready') { <div class="agent-ready"><span aria-hidden="true">✓</span><div><strong>El agente tiene contexto suficiente</strong><p>Los datos no respaldados seguirán identificados como supuestos o pendientes.</p></div></div> }
            @if (currentQuestion(); as question) { <form class="agent-question" [formGroup]="answerForm" (ngSubmit)="answerQuestion()"><div class="question-meta"><span>Pregunta {{ currentQuestionNumber() }} de {{ session.total_question_count }}</span><span>Tema: {{ categoryLabel(question.category) }}</span>@if (question.required) { <span>Dato importante</span> }</div><h3>{{ identity.adapt(question.text) }}</h3><p>{{ identity.adapt(question.rationale) }}</p><app-form-field controlId="agent-answer" label="Tu respuesta"><textarea id="agent-answer" class="interview-answer" formControlName="answer" rows="9" placeholder="Escribe lo que sabes; puedes extenderte con todo el contexto necesario."></textarea></app-form-field><div class="question-actions"><app-button variant="secondary" type="button" [disabled]="agentBusy()" (pressed)="answerUnknown()">No lo sé todavía</app-button><app-button type="submit" [disabled]="answerForm.invalid || agentBusy()">{{ agentBusy() ? 'Analizando…' : 'Enviar y continuar' }}</app-button></div></form> }
            @if (answeredEntries().length) { <details class="answer-history"><summary>Respuestas aportadas ({{ answeredEntries().length }})</summary><dl>@for (item of answeredEntries(); track item[0]) { <div><dt>{{ answerLabel(item[0]) }}</dt><dd>{{ item[1] }}</dd></div> }</dl></details> }
          </div>
        }
      </dialog>
    } @else {
      <section class="financial-workspace" aria-labelledby="financial-title">
        <div class="assistant-message assistant-message--compact"><span class="agent-orb" aria-hidden="true">$</span><div><span class="eyebrow">Finanzas y generación</span><h2 id="financial-title">Define las cifras disponibles</h2><p>Los cálculos se realizan con fórmulas verificables. Si aún faltan cifras, el agente las marcará sin inventarlas.</p></div></div>
        <form class="financial-step" [formGroup]="financialForm" (ngSubmit)="generate()">
          <fieldset class="interview-card"><legend><span>$</span> Estimación financiera</legend><label class="unknown-data"><input type="checkbox" formControlName="financialUnknown"><span><strong>Aún no tengo cifras confiables</strong><small>Se generará una estructura con datos requeridos claramente identificados.</small></span></label>@if (!financialForm.controls.financialUnknown.value) { <div class="form-row form-row--three"><app-form-field controlId="investment" label="Inversión inicial estimada"><input id="investment" type="number" min="0" formControlName="initialInvestment"></app-form-field><app-form-field controlId="annualCost" label="Costo anual estimado"><input id="annualCost" type="number" min="0" formControlName="annualCost"></app-form-field><app-form-field controlId="annualBenefit" label="Beneficio anual estimado"><input id="annualBenefit" type="number" min="0" formControlName="annualBenefit"></app-form-field></div><p class="field-help">Se aplicarán a los {{ horizon() }} años configurados para calcular escenarios, sin delegar las fórmulas al modelo.</p> }</fieldset>
          @if (error()) { <p class="form-error" role="alert">{{ error() }}</p> }
          @if (generating()) { <div class="generation-progress" role="status"><div><span class="agent-orb" aria-hidden="true">✦</span><strong>El agente está construyendo y verificando el {{ identity.singular() }}…</strong></div><progress max="100" value="70"></progress><small>Redactando · Contrastando evidencia · Aplicando reglas · Corrigiendo incumplimientos</small></div> }
          <div class="generate-cta"><div><strong>{{ readinessLabel() }}</strong><small>{{ readinessHint() }}</small></div><app-button type="submit" [disabled]="financialForm.invalid || generating() || !project() || loadingAgent()">{{ generating() ? 'Construyendo…' : generateLabel() }}</app-button></div>
        </form>
      </section>
    }
  `
})
export class CaseGenerationPanelComponent implements OnInit {
  @ViewChild('interviewDialog') private interviewDialog?: ElementRef<HTMLDialogElement>;
  readonly projectId = input.required<string>();
  readonly mode = input<'interview' | 'financial'>('interview');
  readonly interviewUpdated = output<AgentInterview>();
  readonly financialDirty = output<boolean>();
  private readonly generationApi = inject(GenerationApi);
  private readonly interviewApi = inject(InterviewApi);
  private readonly projectsApi = inject(ProjectsApi);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly formBuilder = inject(FormBuilder);
  readonly identity = inject(ClientIdentityService);
  readonly project = signal<Project | null>(null);
  readonly interview = signal<AgentInterview | null>(null);
  readonly generating = signal(false);
  readonly loadingAgent = signal(true);
  readonly agentBusy = signal(false);
  readonly error = signal<string | null>(null);
  readonly agentError = signal<string | null>(null);
  private interviewOpenedOnce = false;
  readonly horizon = signal(5);
  readonly currentQuestion = computed(() => this.interview()?.questions[0] ?? null);
  readonly answeredEntries = computed(() => Object.entries(this.interview()?.answers ?? {}));
  readonly answerForm = this.formBuilder.nonNullable.group({ answer: ['', [Validators.required, Validators.maxLength(4000)]] });
  readonly financialForm = this.formBuilder.nonNullable.group({ financialUnknown: [false], initialInvestment: [0, [Validators.required, Validators.min(0)]], annualCost: [0, [Validators.required, Validators.min(0)]], annualBenefit: [0, [Validators.required, Validators.min(0)]] });

  ngOnInit(): void {
    this.projectsApi.get(this.projectId()).pipe(
      takeUntilDestroyed(this.destroyRef),
      switchMap((project) => {
        this.project.set(project); this.horizon.set(project.horizon_years);
        const setup = project.setup;
        if (setup) {
          const initialInvestment = Number(setup.initial_investment); const annualCost = Number(setup.annual_costs[0] ?? 0); const annualBenefit = Number(setup.annual_benefits[0] ?? 0);
          this.financialForm.patchValue({ initialInvestment, annualCost, annualBenefit, financialUnknown: initialInvestment === 0 && annualCost === 0 && annualBenefit === 0 });
          this.financialForm.markAsPristine();
        }
        this.financialForm.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.financialDirty.emit(this.financialForm.dirty));
        return this.interviewApi.get(this.projectId());
      }),
      switchMap((session) => (session || this.mode() === 'financial') ? of(session) : this.interviewApi.analyze(this.projectId())),
      finalize(() => this.loadingAgent.set(false))
    ).subscribe({ next: (session) => { if (session) this.updateInterview(session); }, error: () => this.agentError.set('No pudimos iniciar el análisis del agente. Puedes reintentar sin perder la información del proyecto.') });
  }

  reanalyze(): void {
    if (this.agentBusy()) return;
    this.agentBusy.set(true); this.agentError.set(null);
    this.interviewApi.analyze(this.projectId()).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.agentBusy.set(false))).subscribe({ next: (session) => this.updateInterview(session), error: () => this.agentError.set('No fue posible reanalizar el proyecto.') });
  }

  answerQuestion(answer = this.answerForm.controls.answer.value): void {
    const question = this.currentQuestion();
    if (!question || !answer.trim() || this.agentBusy()) return;
    this.agentBusy.set(true); this.agentError.set(null);
    this.interviewApi.answer(this.projectId(), { question_id: question.id, answer: answer.trim() }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.agentBusy.set(false))).subscribe({ next: (session) => { this.updateInterview(session); this.answerForm.reset(); }, error: () => this.agentError.set('No pudimos guardar la respuesta. Intenta de nuevo.') });
  }

  answerUnknown(): void { this.answerQuestion('No lo sé todavía; tratar como supuesto o dato requerido sin inventarlo.'); }

  generate(): void {
    const project = this.project(); const setup = project?.setup;
    if (!project || !setup || this.financialForm.invalid || this.generating()) return;
    const value = this.financialForm.getRawValue(); const periods = this.horizon(); const unknown = value.financialUnknown;
    const payload: GenerationInput = { document_kind: this.identity.clientId() === 'mabe' ? 'blueprint' : 'business_case', project_type: setup.project_type, responsible_area: setup.responsible_area, sponsor: setup.sponsor, audience: setup.audience, decision: setup.decision, problem: setup.problem, solution: setup.solution, interview_context: this.interview()?.answers ?? {}, financial: { initial_investment: unknown ? 0 : value.initialInvestment, annual_costs: Array.from({ length: periods }, () => unknown ? 0 : value.annualCost), annual_benefits: Array.from({ length: periods }, () => unknown ? 0 : value.annualBenefit) } };
    this.generating.set(true); this.error.set(null);
    this.generationApi.generate(this.projectId(), payload).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.generating.set(false))).subscribe({ next: () => { this.financialForm.markAsPristine(); this.financialDirty.emit(false); void this.router.navigate(['/review', this.projectId()]); }, error: () => this.error.set('No pudimos construir el borrador. El agente conservó tus respuestas; revisa las fuentes y vuelve a intentarlo.') });
  }

  openInterview(): void { if (!this.interviewDialog?.nativeElement.open) this.interviewDialog?.nativeElement.showModal(); }
  closeInterview(): void { if (this.interviewDialog?.nativeElement.open) this.interviewDialog.nativeElement.close(); }
  currentQuestionNumber(): number { const session = this.interview(); return session ? Math.min(session.answered_count + 1, Math.max(1, session.total_question_count)) : 1; }
  interviewProgress(): number { const session = this.interview(); return !session || !session.total_question_count ? 100 : Math.round(session.answered_count / session.total_question_count * 100); }
  interviewScope(): string { const session = this.interview(); if (!session) return 'Definiendo alcance…'; if (!session.topics.length) return 'No quedan temas pendientes; puedes revisar el diagnóstico.'; return `Temas pendientes: ${session.topics.map((topic) => this.categoryLabel(topic)).join(', ')}.`; }
  private updateInterview(session: AgentInterview): void { this.interview.set(session); this.interviewUpdated.emit(session); if (this.mode() === 'interview' && !this.interviewOpenedOnce) { this.interviewOpenedOnce = true; queueMicrotask(() => this.openInterview()); } }
  categoryLabel(category: string): string { return category.charAt(0).toLocaleUpperCase() + category.slice(1); }
  answerLabel(id: string): string { return id.replaceAll('_', ' ').replace(/^./, (letter) => letter.toLocaleUpperCase()); }
  readinessLabel(): string { return this.interview()?.status === 'ready' ? 'Contexto suficiente para un borrador defendible' : 'Puedes avanzar con datos pendientes'; }
  readinessHint(): string { return this.interview()?.status === 'ready' ? 'El agente aplicará y verificará las reglas de cada sección.' : 'Los vacíos se marcarán claramente como supuestos o datos requeridos.'; }
  generateLabel(): string { if (this.project()?.status !== 'draft') return 'Crear nueva versión corregida'; return this.interview()?.status === 'ready' ? `Construir ${this.identity.singular()}` : 'Construir con datos pendientes'; }
  readinessClass(): string { const score = this.interview()?.readiness_score ?? 0; return score < 50 ? 'readiness-score--low' : score < 80 ? 'readiness-score--medium' : 'readiness-score--high'; }
  readinessLevel(): string { const score = this.interview()?.readiness_score ?? 0; return score < 50 ? 'Preparación baja' : score < 80 ? 'Preparación media' : 'Preparación alta'; }
}

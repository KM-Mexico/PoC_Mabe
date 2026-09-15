import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import type { components } from './schema';

export type RuleSummary = components['schemas']['RuleSummaryRead'];
export type RuleDetail = components['schemas']['RuleDetailRead'];
export type RuleVersion = components['schemas']['RuleVersionRead'];
export type RuleValidation = components['schemas']['RuleValidationRead'];
export type RuleComparison = components['schemas']['RuleCompareRead'];

@Injectable({ providedIn: 'root' })
export class RulesApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/v1/rules';

  list(): Observable<RuleSummary[]> { return this.http.get<RuleSummary[]>(this.baseUrl); }
  detail(sectionId: string): Observable<RuleDetail> { return this.http.get<RuleDetail>(`${this.baseUrl}/${encodeURIComponent(sectionId)}`); }
  createDraft(sectionId: string, markdown?: string): Observable<RuleVersion> { return this.http.post<RuleVersion>(`${this.baseUrl}/${encodeURIComponent(sectionId)}/drafts`, { markdown: markdown ?? null, actor: 'local-user' }); }
  updateDraft(sectionId: string, version: number, markdown: string): Observable<RuleVersion> { return this.http.put<RuleVersion>(`${this.baseUrl}/${encodeURIComponent(sectionId)}/drafts/${version}`, { markdown, actor: 'local-user' }); }
  validate(sectionId: string, version: number): Observable<RuleValidation> { return this.http.post<RuleValidation>(`${this.baseUrl}/${encodeURIComponent(sectionId)}/drafts/${version}/validate`, {}); }
  publish(sectionId: string, version: number): Observable<RuleVersion> { return this.http.post<RuleVersion>(`${this.baseUrl}/${encodeURIComponent(sectionId)}/drafts/${version}/publish`, {}); }
  restore(sectionId: string): Observable<RuleVersion> { return this.http.post<RuleVersion>(`${this.baseUrl}/${encodeURIComponent(sectionId)}/restore-default`, { actor: 'local-user' }); }
  compare(sectionId: string, fromVersion: number, toVersion: number): Observable<RuleComparison> {
    const params = new HttpParams().set('from_version', fromVersion).set('to_version', toVersion);
    return this.http.get<RuleComparison>(`${this.baseUrl}/${encodeURIComponent(sectionId)}/compare`, { params });
  }
}

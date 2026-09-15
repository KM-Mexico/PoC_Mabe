import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import type { components } from './schema';

export type GenerationInput = components['schemas']['GenerationCreate'];
export type GenerationRun = components['schemas']['GenerationRunRead'];
export type BusinessCaseVersion = components['schemas']['BusinessCaseVersionRead'];
export type BusinessCaseVersionSummary = components['schemas']['BusinessCaseVersionSummaryRead'];

@Injectable({ providedIn: 'root' })
export class GenerationApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/v1';

  generate(projectId: string, payload: GenerationInput): Observable<GenerationRun> {
    const requestKey = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    return this.http.post<GenerationRun>(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/generations`, payload, { headers: { 'Idempotency-Key': requestKey } });
  }

  run(projectId: string, runId: string): Observable<GenerationRun> {
    return this.http.get<GenerationRun>(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/generations/${encodeURIComponent(runId)}`);
  }

  versions(projectId: string): Observable<BusinessCaseVersionSummary[]> {
    return this.http.get<BusinessCaseVersionSummary[]>(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/versions`);
  }

  version(versionId: string): Observable<BusinessCaseVersion> {
    return this.http.get<BusinessCaseVersion>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}`);
  }

  regenerate(versionId: string, sectionId: string | null = null): Observable<GenerationRun> {
    return this.http.post<GenerationRun>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}/regenerate`, { section_id: sectionId });
  }
}

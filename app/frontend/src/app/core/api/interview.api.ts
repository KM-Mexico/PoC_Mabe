import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import type { components } from './schema';

export type AgentInterview = components['schemas']['InterviewRead'];
export type InterviewAnswer = components['schemas']['InterviewAnswerCreate'];

@Injectable({ providedIn: 'root' })
export class InterviewApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/v1/projects';

  get(projectId: string): Observable<AgentInterview | null> {
    return this.http.get<AgentInterview | null>(`${this.baseUrl}/${encodeURIComponent(projectId)}/interview`);
  }

  analyze(projectId: string): Observable<AgentInterview> {
    return this.http.post<AgentInterview>(`${this.baseUrl}/${encodeURIComponent(projectId)}/interview/analyze`, {});
  }

  answer(projectId: string, payload: InterviewAnswer): Observable<AgentInterview> {
    return this.http.post<AgentInterview>(`${this.baseUrl}/${encodeURIComponent(projectId)}/interview/answers`, payload);
  }
}

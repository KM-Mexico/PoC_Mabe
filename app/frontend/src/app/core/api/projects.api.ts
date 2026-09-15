import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import type { components } from './schema';

export type Project = components['schemas']['ProjectRead'];
export type CreateProject = components['schemas']['ProjectCreate'];
export type UpdateProject = components['schemas']['ProjectUpdate'];

@Injectable({ providedIn: 'root' })
export class ProjectsApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/v1/projects';

  list(): Observable<Project[]> {
    return this.http.get<Project[]>(this.baseUrl);
  }

  get(projectId: string): Observable<Project> {
    return this.http.get<Project>(`${this.baseUrl}/${encodeURIComponent(projectId)}`);
  }

  create(payload: CreateProject): Observable<Project> {
    return this.http.post<Project>(this.baseUrl, payload);
  }

  update(projectId: string, payload: UpdateProject): Observable<Project> {
    return this.http.patch<Project>(`${this.baseUrl}/${encodeURIComponent(projectId)}`, payload);
  }

  delete(projectId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/${encodeURIComponent(projectId)}`);
  }
}

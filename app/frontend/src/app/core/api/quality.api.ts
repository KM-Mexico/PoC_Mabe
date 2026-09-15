import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import type { components } from './schema';
import type { ReviewComment } from './review.api';

export type QualityValidation = components['schemas']['QualityValidationRead'];
export type QualityFinding = components['schemas']['QualityFindingRead'];
export type ExportRecord = components['schemas']['ExportRecordRead'];
export type Finalization = components['schemas']['FinalizeRead'];

@Injectable({ providedIn: 'root' })
export class QualityApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/v1';

  validate(versionId: string): Observable<QualityValidation> { return this.http.post<QualityValidation>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}/validations`, {}); }
  validations(versionId: string): Observable<QualityValidation[]> { return this.http.get<QualityValidation[]>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}/validations`); }
  findingComment(findingId: string): Observable<ReviewComment> { return this.http.post<ReviewComment>(`${this.baseUrl}/findings/${encodeURIComponent(findingId)}/comments`, {}); }
  finalize(versionId: string): Observable<Finalization> { return this.http.post<Finalization>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}/finalize`, {}); }
  exports(versionId: string): Observable<ExportRecord[]> { return this.http.get<ExportRecord[]>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}/exports`); }
  exportUrl(versionId: string, format: 'json' | 'markdown' | 'pdf'): string { return `${this.baseUrl}/versions/${encodeURIComponent(versionId)}/exports/${format}`; }
}

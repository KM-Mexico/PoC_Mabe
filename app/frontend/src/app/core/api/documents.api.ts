import { HttpClient, HttpEvent } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import type { components } from './schema';

export type SourceDocument = components['schemas']['DocumentRead'];
export type EvidenceChunk = components['schemas']['EvidenceChunkRead'];
export type UploadBatch = components['schemas']['UploadBatchRead'];

@Injectable({ providedIn: 'root' })
export class DocumentsApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/v1';

  list(projectId: string): Observable<SourceDocument[]> {
    return this.http.get<SourceDocument[]>(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/documents`);
  }

  upload(projectId: string, files: readonly File[]): Observable<HttpEvent<UploadBatch>> {
    const body = new FormData();
    for (const file of files) body.append('files', file, file.name);
    return this.http.post<UploadBatch>(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/documents`, body, {
      observe: 'events',
      reportProgress: true
    });
  }

  chunks(documentId: string): Observable<EvidenceChunk[]> {
    return this.http.get<EvidenceChunk[]>(`${this.baseUrl}/documents/${encodeURIComponent(documentId)}/chunks`);
  }

  setDocumentIncluded(documentId: string, included: boolean): Observable<SourceDocument> {
    return this.http.patch<SourceDocument>(`${this.baseUrl}/documents/${encodeURIComponent(documentId)}`, { included });
  }

  setChunkIncluded(chunkId: string, included: boolean): Observable<EvidenceChunk> {
    return this.http.patch<EvidenceChunk>(`${this.baseUrl}/chunks/${encodeURIComponent(chunkId)}`, { included });
  }

  delete(documentId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/documents/${encodeURIComponent(documentId)}`);
  }
}

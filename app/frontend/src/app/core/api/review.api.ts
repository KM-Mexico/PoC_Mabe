import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import type { components } from './schema';
import type { BusinessCaseVersion } from './generation.api';

export type ReviewComment = components['schemas']['ReviewCommentRead'];
export type ReviewCommentInput = components['schemas']['ReviewCommentCreate'];
export type RevisionProposal = components['schemas']['RevisionProposalRead'];
export type ManualRevisionInput = components['schemas']['ManualRevisionCreate'];
export type VersionComparison = components['schemas']['VersionComparisonRead'];
export type VersionChange = components['schemas']['VersionChangeRead'];

@Injectable({ providedIn: 'root' })
export class ReviewApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api/v1';

  contentHash(versionId: string): Observable<{ content_hash: string }> { return this.http.get<{ content_hash: string }>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}/content-hash`); }
  comments(versionId: string, status = ''): Observable<ReviewComment[]> { const params = status ? new HttpParams().set('status', status) : undefined; return this.http.get<ReviewComment[]>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}/comments`, { params }); }
  createComment(versionId: string, payload: ReviewCommentInput): Observable<ReviewComment> { return this.http.post<ReviewComment>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}/comments`, payload); }
  propose(commentId: string): Observable<RevisionProposal> { return this.http.post<RevisionProposal>(`${this.baseUrl}/comments/${encodeURIComponent(commentId)}/proposal`, {}); }
  accept(proposalId: string): Observable<BusinessCaseVersion> { return this.http.post<BusinessCaseVersion>(`${this.baseUrl}/proposals/${encodeURIComponent(proposalId)}/accept`, {}); }
  reject(proposalId: string): Observable<RevisionProposal> { return this.http.post<RevisionProposal>(`${this.baseUrl}/proposals/${encodeURIComponent(proposalId)}/reject`, {}); }
  manualRevision(versionId: string, payload: ManualRevisionInput): Observable<BusinessCaseVersion> { return this.http.post<BusinessCaseVersion>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}/manual-revision`, payload); }
  restore(versionId: string, reason: string): Observable<BusinessCaseVersion> { return this.http.post<BusinessCaseVersion>(`${this.baseUrl}/versions/${encodeURIComponent(versionId)}/restore`, { reason }); }
  comparison(projectId: string, fromVersion: string, toVersion: string): Observable<VersionComparison> { const params = new HttpParams().set('from_version', fromVersion).set('to_version', toVersion); return this.http.get<VersionComparison>(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/version-comparison`, { params }); }
  history(projectId: string): Observable<VersionChange[]> { return this.http.get<VersionChange[]>(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/version-changes`); }
}

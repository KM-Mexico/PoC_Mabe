import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DocumentsApi } from './documents.api';

describe('DocumentsApi', () => {
  let api: DocumentsApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(DocumentsApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('uploads all selected files as multipart data', () => {
    const files = [new File(['uno'], 'uno.txt'), new File(['dos'], 'dos.md')];
    api.upload('project/id', files).subscribe();
    const request = http.expectOne('/api/v1/projects/project%2Fid/documents');
    expect(request.request.method).toBe('POST');
    expect(request.request.reportProgress).toBeTrue();
    expect(request.request.body instanceof FormData).toBeTrue();
    expect((request.request.body as FormData).getAll('files').length).toBe(2);
    request.flush({ accepted_count: 0, rejected_count: 0, items: [] });
  });

  it('persists chunk inclusion through the versioned API', () => {
    api.setChunkIncluded('chunk/id', false).subscribe();
    const request = http.expectOne('/api/v1/chunks/chunk%2Fid');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ included: false });
    request.flush({});
  });
});

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { RulesApi } from './rules.api';

describe('RulesApi', () => {
  let api: RulesApi; let http: HttpTestingController;
  beforeEach(() => { TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] }); api = TestBed.inject(RulesApi); http = TestBed.inject(HttpTestingController); });
  afterEach(() => http.verify());

  it('saves a versioned Markdown draft', () => {
    api.updateDraft('executive/summary', 2, '# Rule').subscribe();
    const request = http.expectOne('/api/v1/rules/executive%2Fsummary/drafts/2');
    expect(request.request.method).toBe('PUT'); expect(request.request.body).toEqual({ markdown: '# Rule', actor: 'local-user' }); request.flush({});
  });

  it('publishes a validated draft', () => {
    api.publish('executive_summary', 2).subscribe();
    const request = http.expectOne('/api/v1/rules/executive_summary/drafts/2/publish');
    expect(request.request.method).toBe('POST'); request.flush({});
  });
});

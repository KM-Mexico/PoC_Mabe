import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { GenerationApi } from './generation.api';

describe('GenerationApi', () => {
  let api: GenerationApi; let http: HttpTestingController;
  beforeEach(() => { TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] }); api = TestBed.inject(GenerationApi); http = TestBed.inject(HttpTestingController); });
  afterEach(() => http.verify());

  it('starts a typed generation run', () => {
    const payload = { project_type: 'Tecnología', responsible_area: 'Tecnología', sponsor: 'Sponsor', decision: 'Aprobar', problem: 'Demoras', audience: 'Comité', financial: { initial_investment: 100, annual_costs: [10], annual_benefits: [50] } };
    api.generate('project/id', payload).subscribe();
    const request = http.expectOne('/api/v1/projects/project%2Fid/generations');
    expect(request.request.method).toBe('POST'); expect(request.request.body).toEqual(payload); expect(request.request.headers.has('Idempotency-Key')).toBeTrue(); request.flush({});
  });

  it('regenerates without mutating the source version', () => {
    api.regenerate('version/id', 'executive_summary').subscribe();
    const request = http.expectOne('/api/v1/versions/version%2Fid/regenerate');
    expect(request.request.method).toBe('POST'); expect(request.request.body).toEqual({ section_id: 'executive_summary' }); request.flush({});
  });
});

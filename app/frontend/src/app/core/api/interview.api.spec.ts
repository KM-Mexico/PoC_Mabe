import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { InterviewApi } from './interview.api';

describe('InterviewApi', () => {
  let api: InterviewApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(InterviewApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('analyzes a project and persists an answer', () => {
    api.analyze('project/id').subscribe();
    const analyze = http.expectOne('/api/v1/projects/project%2Fid/interview/analyze');
    expect(analyze.request.method).toBe('POST');
    analyze.flush({});

    api.answer('project/id', { question_id: 'risk', answer: 'Riesgo de adopción' }).subscribe();
    const answer = http.expectOne('/api/v1/projects/project%2Fid/interview/answers');
    expect(answer.request.body).toEqual({ question_id: 'risk', answer: 'Riesgo de adopción' });
    answer.flush({});
  });
});

import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ProjectsApi } from './projects.api';

describe('ProjectsApi', () => {
  let api: ProjectsApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(ProjectsApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads projects from the versioned API', () => {
    api.list().subscribe((projects) => expect(projects).toEqual([]));
    const request = http.expectOne('/api/v1/projects');
    expect(request.request.method).toBe('GET');
    request.flush([]);
  });

  it('does not send a delete request with a raw identifier', () => {
    api.delete('id/with spaces').subscribe();
    const request = http.expectOne('/api/v1/projects/id%2Fwith%20spaces');
    expect(request.request.method).toBe('DELETE');
    request.flush(null);
  });

  it('updates an existing project definition using an encoded identifier', () => {
    api.update('project/one', { name: 'Definición actualizada' }).subscribe();
    const request = http.expectOne('/api/v1/projects/project%2Fone');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ name: 'Definición actualizada' });
    request.flush({});
  });
});

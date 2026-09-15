import { TestBed } from '@angular/core/testing';
import { MarkdownPreviewComponent } from './markdown-preview.component';

describe('MarkdownPreviewComponent', () => {
  it('renders structure without executing embedded HTML', async () => {
    await TestBed.configureTestingModule({ imports: [MarkdownPreviewComponent] }).compileComponents();
    const fixture = TestBed.createComponent(MarkdownPreviewComponent);
    fixture.componentRef.setInput('markdown', '---\ntitle: Regla segura\n---\n## Objetivo\nDEBE usar `evidencia`.\n\n- Punto **importante**\n\n<script>alert(1)</script>');
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('h2')?.textContent).toContain('Objetivo');
    expect(element.querySelector('code')?.textContent).toBe('evidencia');
    expect(element.querySelector('li strong')?.textContent).toBe('importante');
    expect(element.querySelector('script')).toBeNull();
    expect(element.textContent).toContain('<script>alert(1)</script>');
  });
});

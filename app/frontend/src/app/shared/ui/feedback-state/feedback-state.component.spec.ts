import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FeedbackStateComponent } from './feedback-state.component';

describe('FeedbackStateComponent', () => {
  let fixture: ComponentFixture<FeedbackStateComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [FeedbackStateComponent] }).compileComponents();
    fixture = TestBed.createComponent(FeedbackStateComponent);
    fixture.componentRef.setInput('kind', 'error');
    fixture.componentRef.setInput('title', 'Error controlado');
    fixture.componentRef.setInput('message', 'Intenta de nuevo.');
    fixture.detectChanges();
  });

  it('uses an alert role for an error', () => {
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('[role="alert"]')?.textContent).toContain('Error controlado');
  });
});


import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    title: 'Mis proyectos | Casecraft',
    loadComponent: () => import('./features/projects/projects-page.component').then((module) => module.ProjectsPageComponent)
  },
  {
    path: 'generate/:id',
    title: 'Construir documento | Casecraft',
    loadComponent: () => import('./features/generation/generation-page.component').then((module) => module.GenerationPageComponent)
  },
  {
    path: 'review/:id',
    title: 'Revisar documento | Casecraft',
    loadComponent: () => import('./features/review/review-page.component').then((module) => module.ReviewPageComponent)
  },
  {
    path: 'quality/:id',
    title: 'Finalizar documento | Casecraft',
    loadComponent: () => import('./features/quality/quality-page.component').then((module) => module.QualityPageComponent)
  },
  {
    path: 'rules',
    title: 'Configuración del agente | Casecraft',
    loadComponent: () => import('./features/rules/rules-page.component').then((module) => module.RulesPageComponent)
  },
  { path: '**', redirectTo: '' }
];

import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ClientIdentityService } from './core/client-identity.service';

@Component({
  selector: 'app-root',
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <a class="skip-link" href="#main-content">Saltar al contenido</a>
    <div class="app-shell">
      <header class="topbar">
        <a class="brand" routerLink="/" [attr.aria-label]="identity.activeClient().name + ', Casecraft, inicio'">
          <span class="client-wordmark" [class.client-wordmark--mabe]="identity.clientId() === 'mabe'">{{ identity.activeClient().wordmark }}</span>
          <span class="brand-divider" aria-hidden="true"></span>
          <span class="brand-description"><strong>Casecraft</strong><small>{{ identity.singularTitle() }} Workspace</small></span>
        </a>
        <div class="topbar-actions">
          <label class="client-switcher">
            <span>Cliente</span>
            <select [value]="identity.clientId()" (change)="selectClient($event)" aria-label="Seleccionar identidad del cliente">
              @for (client of identity.clients; track client.id) {
                <option [value]="client.id">{{ client.name }}</option>
              }
            </select>
          </label>
          <span class="poc-badge"><span aria-hidden="true">●</span> Entorno privado</span>
        </div>
      </header>
      <aside class="sidebar" aria-label="Navegación principal">
        <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">
          <span aria-hidden="true">▦</span><span class="nav-label-full">Mis {{ identity.plural() }}</span><span class="nav-label-short">{{ identity.pluralTitle() }}</span>
        </a>
        <a class="sidebar-create" routerLink="/" [queryParams]="{ new: 1 }">
          <span aria-hidden="true">＋</span><span class="nav-label-full">Nuevo {{ identity.singular() }}</span><span class="nav-label-short">Nuevo</span>
        </a>
        <a routerLink="/rules" routerLinkActive="active">
          <span aria-hidden="true">⚙</span><span class="nav-label-full">Configuración</span><span class="nav-label-short">Ajustes</span>
        </a>
        <div class="sidebar-note">
          <strong>Tu información está protegida</strong>
          <p>Los documentos permanecen en este entorno privado.</p>
        </div>
      </aside>
      <main id="main-content" class="main-content" tabindex="-1">
        <router-outlet />
      </main>
    </div>
  `
})
export class AppComponent {
  readonly identity = inject(ClientIdentityService);

  selectClient(event: Event): void {
    const selected = (event.target as HTMLSelectElement).value;
    if (selected === 'valia' || selected === 'mabe') this.identity.select(selected);
  }
}

import { DOCUMENT } from '@angular/common';
import { Injectable, computed, inject, signal } from '@angular/core';

export type ClientId = 'valia' | 'mabe';

export interface ClientIdentity {
  id: ClientId;
  name: string;
  wordmark: string;
}

const CLIENT_STORAGE_KEY = 'casecraft.client';

@Injectable({ providedIn: 'root' })
export class ClientIdentityService {
  private readonly document = inject(DOCUMENT);
  readonly clients: ReadonlyArray<ClientIdentity> = [
    { id: 'valia', name: 'Valia', wordmark: 'VALIA' },
    { id: 'mabe', name: 'Mabe', wordmark: 'mabe' }
  ];
  readonly clientId = signal<ClientId>(this.readStoredClient());
  readonly activeClient = computed(() => this.clients.find((client) => client.id === this.clientId()) ?? this.clients[0]);
  readonly singular = computed(() => this.clientId() === 'mabe' ? 'blueprint' : 'business case');
  readonly singularTitle = computed(() => this.clientId() === 'mabe' ? 'Blueprint' : 'Business case');
  readonly plural = computed(() => this.clientId() === 'mabe' ? 'blueprints' : 'business cases');
  readonly pluralTitle = computed(() => this.clientId() === 'mabe' ? 'Blueprints' : 'Business cases');

  constructor() {
    this.applyTheme(this.clientId());
  }

  select(client: ClientId): void {
    this.clientId.set(client);
    this.applyTheme(client);
    try {
      this.document.defaultView?.localStorage.setItem(CLIENT_STORAGE_KEY, client);
    } catch {
      // La identidad sigue activa aunque el navegador bloquee el almacenamiento.
    }
  }

  adapt(text: unknown): string {
    const value = String(text ?? '');
    if (this.clientId() !== 'mabe') return value;
    return value
      .replace(/\bbusiness cases\b/gi, (match) => match[0] === 'B' ? 'Blueprints' : 'blueprints')
      .replace(/\bbusiness case\b/gi, (match) => match[0] === 'B' ? 'Blueprint' : 'blueprint');
  }

  private readStoredClient(): ClientId {
    try {
      return this.document.defaultView?.localStorage.getItem(CLIENT_STORAGE_KEY) === 'mabe' ? 'mabe' : 'valia';
    } catch {
      return 'valia';
    }
  }

  private applyTheme(client: ClientId): void {
    this.document.documentElement.dataset['client'] = client;
  }
}

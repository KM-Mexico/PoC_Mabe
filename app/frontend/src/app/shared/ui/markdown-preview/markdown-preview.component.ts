import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';

type InlineToken = { kind: 'text' | 'strong' | 'emphasis' | 'code'; text: string };
type MetadataEntry = { key: string; value: string };
type MarkdownBlock =
  | { kind: 'metadata'; entries: MetadataEntry[] }
  | { kind: 'heading'; level: number; content: InlineToken[] }
  | { kind: 'paragraph' | 'quote'; content: InlineToken[] }
  | { kind: 'list'; ordered: boolean; items: InlineToken[][] }
  | { kind: 'code'; language: string; content: string }
  | { kind: 'table'; headers: InlineToken[][]; rows: InlineToken[][][] }
  | { kind: 'divider' };

@Component({
  selector: 'app-markdown-preview',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article class="markdown-document">
      @for (block of blocks(); track $index) {
        @switch (block.kind) {
          @case ('metadata') {
            <dl class="markdown-metadata">
              @for (entry of block.entries; track entry.key) { <div><dt>{{ metadataLabel(entry.key) }}</dt><dd>{{ entry.value }}</dd></div> }
            </dl>
          }
          @case ('heading') {
            @if (block.level === 1) { <h1><ng-container *ngTemplateOutlet="inline; context: { tokens: block.content }" /></h1> }
            @else if (block.level === 2) { <h2><ng-container *ngTemplateOutlet="inline; context: { tokens: block.content }" /></h2> }
            @else { <h3><ng-container *ngTemplateOutlet="inline; context: { tokens: block.content }" /></h3> }
          }
          @case ('paragraph') { <p><ng-container *ngTemplateOutlet="inline; context: { tokens: block.content }" /></p> }
          @case ('quote') { <blockquote><ng-container *ngTemplateOutlet="inline; context: { tokens: block.content }" /></blockquote> }
          @case ('list') {
            @if (block.ordered) { <ol>@for (item of block.items; track $index) { <li><ng-container *ngTemplateOutlet="inline; context: { tokens: item }" /></li> }</ol> }
            @else { <ul>@for (item of block.items; track $index) { <li><ng-container *ngTemplateOutlet="inline; context: { tokens: item }" /></li> }</ul> }
          }
          @case ('code') { <pre class="markdown-code"><span>{{ block.language || 'texto' }}</span><code>{{ block.content }}</code></pre> }
          @case ('table') {
            <div class="markdown-table"><table><thead><tr>@for (cell of block.headers; track $index) { <th><ng-container *ngTemplateOutlet="inline; context: { tokens: cell }" /></th> }</tr></thead><tbody>@for (row of block.rows; track $index) { <tr>@for (cell of row; track $index) { <td><ng-container *ngTemplateOutlet="inline; context: { tokens: cell }" /></td> }</tr> }</tbody></table></div>
          }
          @case ('divider') { <hr> }
        }
      }
      @empty { <p class="markdown-empty">No hay contenido para previsualizar.</p> }
    </article>

    <ng-template #inline let-tokens="tokens">
      @for (token of tokens; track $index) {
        @switch (token.kind) {
          @case ('strong') { <strong>{{ token.text }}</strong> }
          @case ('emphasis') { <em>{{ token.text }}</em> }
          @case ('code') { <code class="markdown-inline-code">{{ token.text }}</code> }
          @default { {{ token.text }} }
        }
      }
    </ng-template>
  `,
  imports: [NgTemplateOutlet]
})
export class MarkdownPreviewComponent {
  readonly markdown = input.required<string>();
  readonly blocks = computed(() => this.parse(this.markdown()));

  metadataLabel(key: string): string {
    return ({ section_id: 'Identificador', title: 'Título', version: 'Versión', status: 'Estado' } as Record<string, string>)[key] ?? key.replaceAll('_', ' ');
  }

  private parse(source: string): MarkdownBlock[] {
    const lines = source.replaceAll('\r\n', '\n').split('\n');
    const blocks: MarkdownBlock[] = [];
    let index = 0;

    if (lines[0]?.trim() === '---') {
      const closing = lines.slice(1).findIndex((line) => line.trim() === '---');
      if (closing >= 0) {
        const entries = lines.slice(1, closing + 1).flatMap((line) => {
          const separator = line.indexOf(':');
          if (separator < 1) return [];
          return [{ key: line.slice(0, separator).trim(), value: line.slice(separator + 1).trim().replace(/^['"]|['"]$/g, '') }];
        });
        if (entries.length) blocks.push({ kind: 'metadata', entries });
        index = closing + 2;
      }
    }

    while (index < lines.length) {
      const line = lines[index];
      const trimmed = line.trim();
      if (!trimmed) { index += 1; continue; }

      if (trimmed.startsWith('```')) {
        const language = trimmed.slice(3).trim();
        const content: string[] = [];
        index += 1;
        while (index < lines.length && !lines[index].trim().startsWith('```')) content.push(lines[index++]);
        index += index < lines.length ? 1 : 0;
        blocks.push({ kind: 'code', language, content: content.join('\n') });
        continue;
      }

      const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed);
      if (heading) { blocks.push({ kind: 'heading', level: heading[1].length, content: this.inline(heading[2]) }); index += 1; continue; }
      if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) { blocks.push({ kind: 'divider' }); index += 1; continue; }

      if (this.isTableHeader(lines, index)) {
        const headers = this.tableCells(line).map((cell) => this.inline(cell));
        const rows: InlineToken[][][] = [];
        index += 2;
        while (index < lines.length && lines[index].includes('|') && lines[index].trim()) rows.push(this.tableCells(lines[index++]).map((cell) => this.inline(cell)));
        blocks.push({ kind: 'table', headers, rows });
        continue;
      }

      const listMatch = /^(?:([-+*])|(\d+)\.)\s+(.+)$/.exec(trimmed);
      if (listMatch) {
        const ordered = !!listMatch[2];
        const items: InlineToken[][] = [];
        while (index < lines.length) {
          const item = /^(?:([-+*])|(\d+)\.)\s+(.+)$/.exec(lines[index].trim());
          if (!item || !!item[2] !== ordered) break;
          items.push(this.inline(item[3])); index += 1;
        }
        blocks.push({ kind: 'list', ordered, items });
        continue;
      }

      if (trimmed.startsWith('>')) {
        const quote: string[] = [];
        while (index < lines.length && lines[index].trim().startsWith('>')) quote.push(lines[index++].trim().replace(/^>\s?/, ''));
        blocks.push({ kind: 'quote', content: this.inline(quote.join(' ')) });
        continue;
      }

      const paragraph = [trimmed];
      index += 1;
      while (index < lines.length && lines[index].trim() && !this.isBlockStart(lines, index)) paragraph.push(lines[index++].trim());
      blocks.push({ kind: 'paragraph', content: this.inline(paragraph.join(' ')) });
    }
    return blocks;
  }

  private inline(value: string): InlineToken[] {
    const tokens: InlineToken[] = [];
    const pattern = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_)/g;
    let cursor = 0;
    for (const match of value.matchAll(pattern)) {
      const start = match.index ?? 0;
      if (start > cursor) tokens.push({ kind: 'text', text: value.slice(cursor, start) });
      const raw = match[0];
      const kind: InlineToken['kind'] = raw.startsWith('`') ? 'code' : raw.startsWith('**') || raw.startsWith('__') ? 'strong' : 'emphasis';
      const edge = kind === 'strong' ? 2 : 1;
      tokens.push({ kind, text: raw.slice(edge, -edge) });
      cursor = start + raw.length;
    }
    if (cursor < value.length) tokens.push({ kind: 'text', text: value.slice(cursor) });
    return tokens.length ? tokens : [{ kind: 'text', text: value }];
  }

  private isTableHeader(lines: string[], index: number): boolean {
    return lines[index].includes('|') && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1] ?? '') && (lines[index + 1] ?? '').includes('|');
  }
  private tableCells(line: string): string[] { return line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim()); }
  private isBlockStart(lines: string[], index: number): boolean {
    const value = lines[index].trim();
    return /^(#{1,6})\s+/.test(value) || value.startsWith('```') || value.startsWith('>') || /^(?:[-+*]|\d+\.)\s+/.test(value) || /^(-{3,}|\*{3,}|_{3,})$/.test(value) || this.isTableHeader(lines, index);
  }
}

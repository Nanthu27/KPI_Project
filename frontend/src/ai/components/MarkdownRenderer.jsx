/**
 * MarkdownRenderer
 * ----------------
 * Renders LLM markdown output properly:
 *   - ## headings
 *   - **bold**, *italic*
 *   - bullet lists (- / • / *)
 *   - numbered lists (1. 2. 3.)
 *   - tables (| col | col |)
 *   - `inline code` and ```code blocks```
 *   - > blockquotes
 *   - horizontal rules (---)
 *   - → arrow chains
 *   - <br> tags (from LLM output)
 *   - Copy button on code blocks
 *
 * Pure React + inline styles — no extra dependencies.
 */
import { useState } from 'react';

const COLORS = {
  heading: '#1E1B4B',
  body: '#1F2937',
  muted: '#6B7280',
  codeBg: '#1E1B4B',
  codeText: '#E2E8F0',
  inlineCodeBg: '#EDE9FE',
  inlineCodeText: '#5B21B6',
  tableBorder: '#E5E7EB',
  tableHeadBg: '#F5F3FF',
  blockquoteBorder: '#7C3AED',
  blockquoteBg: '#FAF5FF',
  linkColor: '#6D28D9',
};

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      onClick={handleCopy}
      style={{
        position: 'absolute', top: 8, right: 8,
        background: copied ? '#059669' : 'rgba(255,255,255,0.15)',
        border: 'none', borderRadius: 4, color: '#E2E8F0',
        fontSize: 11, fontFamily: 'inherit',
        padding: '3px 8px', cursor: 'pointer',
        transition: 'background 0.2s',
      }}
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}

function InlineText({ text }) {
  // Process: **bold**, *italic*, `code`, and plain text
  const tokens = [];
  let remaining = text;
  const patterns = [
    { re: /\*\*(.+?)\*\*/, type: 'bold' },
    { re: /\*(.+?)\*/, type: 'italic' },
    { re: /`([^`]+)`/, type: 'code' },
  ];

  while (remaining.length > 0) {
    let earliest = null;
    let earliestMatch = null;
    let earliestType = null;

    for (const { re, type } of patterns) {
      const m = remaining.match(re);
      if (m && (earliest === null || m.index < earliest)) {
        earliest = m.index;
        earliestMatch = m;
        earliestType = type;
      }
    }

    if (earliestMatch === null) {
      tokens.push({ type: 'text', content: remaining });
      break;
    }

    if (earliest > 0) {
      tokens.push({ type: 'text', content: remaining.slice(0, earliest) });
    }
    tokens.push({ type: earliestType, content: earliestMatch[1] });
    remaining = remaining.slice(earliest + earliestMatch[0].length);
  }

  return (
    <>
      {tokens.map((tok, i) => {
        if (tok.type === 'bold') return <strong key={i} style={{ fontWeight: 700, color: COLORS.heading }}>{tok.content}</strong>;
        if (tok.type === 'italic') return <em key={i} style={{ fontStyle: 'italic' }}>{tok.content}</em>;
        if (tok.type === 'code') return (
          <code key={i} style={{
            backgroundColor: COLORS.inlineCodeBg, color: COLORS.inlineCodeText,
            borderRadius: 4, padding: '1px 5px', fontSize: '0.88em',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            fontWeight: 600,
          }}>{tok.content}</code>
        );
        return <span key={i}>{tok.content}</span>;
      })}
    </>
  );
}

function parseTable(lines) {
  // lines[0] = header row, lines[1] = separator, lines[2+] = data rows
  const parseRow = (line) =>
    line.split('|').map(c => c.trim()).filter((_, i, arr) => i > 0 && i < arr.length - 1);

  const headers = parseRow(lines[0]);
  const rows = lines.slice(2).map(parseRow);

  return (
    <div style={{ overflowX: 'auto', margin: '10px 0' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th key={i} style={{
                backgroundColor: COLORS.tableHeadBg, color: COLORS.heading,
                border: `1px solid ${COLORS.tableBorder}`,
                padding: '6px 10px', textAlign: 'left', fontWeight: 700,
                whiteSpace: 'nowrap',
              }}>
                <InlineText text={h} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{ backgroundColor: ri % 2 === 0 ? '#fff' : '#FAFBFF' }}>
              {row.map((cell, ci) => (
                <td key={ci} style={{
                  border: `1px solid ${COLORS.tableBorder}`,
                  padding: '5px 10px', color: COLORS.body, fontSize: 12.5,
                }}>
                  <InlineText text={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function MarkdownRenderer({ content, isStreaming = false }) {
  if (!content) return null;

  // Normalise <br> tags from LLM output
  const normalised = content
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/\\n/g, '\n');

  const lines = normalised.split('\n');
  const elements = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // ── Skip empty lines (add spacing via margin on previous element) ──
    if (trimmed === '') {
      i++;
      continue;
    }

    // ── Horizontal rule ──
    if (/^---+$/.test(trimmed) || /^\*\*\*+$/.test(trimmed)) {
      elements.push(
        <hr key={i} style={{ border: 'none', borderTop: `1px solid ${COLORS.tableBorder}`, margin: '10px 0' }} />
      );
      i++;
      continue;
    }

    // ── Headings ──
    const h3 = trimmed.match(/^###\s+(.+)/);
    const h2 = trimmed.match(/^##\s+(.+)/);
    const h1 = trimmed.match(/^#\s+(.+)/);
    if (h1 || h2 || h3) {
      const text = (h1 || h2 || h3)[1];
      const sz = h1 ? 16 : h2 ? 14.5 : 13.5;
      const mt = h1 ? 14 : 10;
      elements.push(
        <div key={i} style={{ fontSize: sz, fontWeight: 700, color: COLORS.heading, marginTop: mt, marginBottom: 4 }}>
          <InlineText text={text} />
        </div>
      );
      i++;
      continue;
    }

    // ── Blockquote ──
    if (trimmed.startsWith('>')) {
      const text = trimmed.replace(/^>\s*/, '');
      elements.push(
        <div key={i} style={{
          borderLeft: `3px solid ${COLORS.blockquoteBorder}`,
          backgroundColor: COLORS.blockquoteBg,
          margin: '6px 0', padding: '6px 12px',
          borderRadius: '0 6px 6px 0',
          color: COLORS.muted, fontSize: 13, fontStyle: 'italic',
        }}>
          <InlineText text={text} />
        </div>
      );
      i++;
      continue;
    }

    // ── Code block ──
    if (trimmed.startsWith('```')) {
      const lang = trimmed.slice(3).trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      const code = codeLines.join('\n');
      elements.push(
        <div key={i} style={{ position: 'relative', margin: '8px 0' }}>
          {lang && (
            <div style={{
              backgroundColor: '#312E81', color: '#A5B4FC',
              fontSize: 10, fontFamily: 'monospace',
              padding: '3px 10px', borderRadius: '6px 6px 0 0',
              fontWeight: 600, letterSpacing: 0.5,
            }}>{lang.toUpperCase()}</div>
          )}
          <pre style={{
            backgroundColor: COLORS.codeBg, color: COLORS.codeText,
            padding: '12px 14px', margin: 0,
            borderRadius: lang ? '0 0 6px 6px' : '6px',
            fontSize: 12, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            overflowX: 'auto', lineHeight: 1.6, whiteSpace: 'pre',
          }}>
            {code}
          </pre>
          <CopyButton text={code} />
        </div>
      );
      continue;
    }

    // ── Table ──
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const tableLines = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableLines.push(lines[i]);
        i++;
      }
      if (tableLines.length >= 2) {
        elements.push(<div key={`table-${i}`}>{parseTable(tableLines)}</div>);
      }
      continue;
    }

    // ── Bullet list ──
    if (/^[-•*]\s/.test(trimmed)) {
      const listItems = [];
      while (i < lines.length && /^[-•*]\s/.test(lines[i].trim())) {
        listItems.push(lines[i].trim().replace(/^[-•*]\s+/, ''));
        i++;
      }
      elements.push(
        <ul key={`ul-${i}`} style={{ margin: '4px 0', paddingLeft: 18, listStyle: 'none' }}>
          {listItems.map((item, li) => (
            <li key={li} style={{ color: COLORS.body, fontSize: 13.5, lineHeight: 1.65, marginBottom: 3, display: 'flex', alignItems: 'flex-start', gap: 6 }}>
              <span style={{ color: '#7C3AED', fontWeight: 700, flexShrink: 0, marginTop: 1 }}>•</span>
              <span><InlineText text={item} /></span>
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // ── Numbered list ──
    if (/^\d+\.\s/.test(trimmed)) {
      const listItems = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        listItems.push(lines[i].trim().replace(/^\d+\.\s+/, ''));
        i++;
      }
      elements.push(
        <ol key={`ol-${i}`} style={{ margin: '4px 0', paddingLeft: 20, listStyle: 'none', counterReset: 'item' }}>
          {listItems.map((item, li) => (
            <li key={li} style={{ color: COLORS.body, fontSize: 13.5, lineHeight: 1.65, marginBottom: 3, display: 'flex', alignItems: 'flex-start', gap: 8 }}>
              <span style={{ color: '#7C3AED', fontWeight: 700, fontSize: 12, minWidth: 18, flexShrink: 0, marginTop: 2 }}>{li + 1}.</span>
              <span><InlineText text={item} /></span>
            </li>
          ))}
        </ol>
      );
      continue;
    }

    // ── Plain paragraph ──
    elements.push(
      <p key={i} style={{ margin: '3px 0 5px', fontSize: 13.5, lineHeight: 1.7, color: COLORS.body }}>
        <InlineText text={trimmed} />
      </p>
    );
    i++;
  }

  return (
    <div style={{ fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {elements}
      {isStreaming && (
        <span style={{
          display: 'inline-block', width: 8, height: 14,
          backgroundColor: '#7A5AF8', marginLeft: 3,
          animation: 'cascade-blink 1s infinite',
          verticalAlign: 'text-bottom', borderRadius: 2,
        }} />
      )}
    </div>
  );
}

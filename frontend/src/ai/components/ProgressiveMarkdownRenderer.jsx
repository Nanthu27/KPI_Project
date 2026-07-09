/**
 * ProgressiveMarkdownRenderer
 * ---------------------------
 * Renders a Cascade AI response as a natural chat message that reveals
 * itself in stages instead of dumping a full report at once.
 *
 * The system prompt (prompts.py) asks the model to:
 *   - never use section labels/headers
 *   - lead with the single most important point in <=100 words, ending on
 *     a complete sentence
 *   - split the rest into further `<!--MORE-->`-separated chunks, each a
 *     natural continuation of the one before it
 *
 * This component splits on that marker and reveals one additional chunk
 * per "Continue" click — not everything at once — so reading stays
 * comfortable and the person controls how deep they go.
 */
import { useState } from 'react';
import MarkdownRenderer from './MarkdownRenderer';

const MARKER = /<!--\s*MORE\s*-->/i;

export default function ProgressiveMarkdownRenderer({ content, isStreaming = false }) {
  const [revealed, setRevealed] = useState(1); // how many chunks are currently shown

  if (!content) return null;

  const chunks = content.split(MARKER).map(c => c.trim()).filter(Boolean);
  const visibleChunks = chunks.slice(0, revealed);
  const hasMore = !isStreaming && revealed < chunks.length;

  return (
    <div>
      {visibleChunks.map((chunk, i) => (
        <div key={i} style={{ marginTop: i > 0 ? 8 : 0 }}>
          <MarkdownRenderer
            content={chunk}
            isStreaming={isStreaming && i === visibleChunks.length - 1}
          />
        </div>
      ))}

      {hasMore && (
        <button
          onClick={() => setRevealed(r => r + 1)}
          style={{
            marginTop: 8,
            background: '#F5F3FF',
            border: '1px solid #E9D5FF',
            borderRadius: 14,
            padding: '5px 14px',
            color: '#6D28D9',
            fontSize: 12.5,
            fontWeight: 600,
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          Continue reading ↓
        </button>
      )}
    </div>
  );
}

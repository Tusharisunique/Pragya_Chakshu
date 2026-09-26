import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLang } from '../lib/context';
import { api } from '../lib/api';

// The backend sends a stable key plus params for every suggestion, so the copy
// lives in i18n and a language switch re-renders it. `fallback` is the original
// English sentence, used only if a key is ever missing from the dictionary.
function fill(template, params) {
  if (!template) return '';
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    params && params[name] != null ? String(params[name]) : match
  );
}

const IDENT_LABEL = {
  PGP_KEY: 'idPgpKey',
  BTC_ADDRESS: 'idBtcAddress',
  ONION_URL: 'idOnionUrl',
  EMAIL: 'idEmail',
};

// The API sends enums and bare counts as params. Those are chrome, not source
// data, so they are resolved to the reader's language before the template runs;
// otherwise the identifier type leaks through as ONION_URL and the count reads
// as a dangling digit followed by a transliterated noun.
function localiseParams(t, key, params) {
  if (key !== 'shared_identifier' || !params) return params;
  const label = IDENT_LABEL[params.type];
  const n = Number(params.count);
  return {
    ...params,
    type: label ? t[label] : params.type,
    count: Number.isFinite(n)
      ? fill(n === 1 ? t.actorCount1 : t.actorCountN, { n })
      : params.count,
  };
}

export default function NextStepsBar({ screen, caseId }) {
  const { t } = useLang();
  // Suggestions are kept as key/params pairs, never as rendered text, so the
  // display string is recomputed on every language change.
  const [suggestions, setSuggestions] = useState([]);
  const [idx, setIdx] = useState(0);

  // Screens without a case behind them get a static hint. Looked up during
  // render (not stored) so it follows the active language.
  const staticHint = t.nextStepHints?.[screen];

  useEffect(() => {
    setIdx(0);
    if (screen !== 'dashboard' || !caseId) return;
    let cancelled = false;
    api.getNextSteps(caseId)
      .then(data => {
        if (cancelled) return;
        const list = data?.full || [];
        setSuggestions(
          list.length
            ? list.map(s => ({ key: s.key, params: s.params, fallback: s.suggestion }))
            : [{ key: 'exploreOrExport', params: {} }]
        );
      })
      .catch(() => {
        if (!cancelled) setSuggestions([{ key: 'exploreOrExport', params: {} }]);
      });
    return () => { cancelled = true; };
  }, [screen, caseId]);

  const current = suggestions[idx] || suggestions[0];
  const dynamic = !staticHint && current
    ? fill(t.nextStepTexts?.[current.key], localiseParams(t, current.key, current.params))
        || current.fallback || ''
    : '';

  if (!staticHint && !dynamic) return null;

  return (
    <div className="next-steps-bar" style={{ padding: '8px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', maxWidth: 900 }}>
        {/* Label */}
        <span style={{
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--accent)',
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          whiteSpace: 'nowrap',
        }}>
          {t.nextSteps}
        </span>

        {/* Current suggestion */}
        <AnimatePresence mode="wait">
          <motion.span
            key={`${idx}-${t.nextSteps}`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
            style={{ fontSize: 13, color: 'var(--text-secondary)', flex: 1 }}
          >
            {staticHint || dynamic}
          </motion.span>
        </AnimatePresence>

        {/* Cycle through suggestions */}
        {suggestions.length > 1 && (
          <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setIdx(i => (i - 1 + suggestions.length) % suggestions.length)}
              style={{ padding: '2px 6px', fontSize: 12 }}
              aria-label={t.prevSuggestion}
            >←</button>
            <span style={{ fontSize: 11, color: 'var(--text-tertiary)', padding: '2px 4px', alignSelf: 'center' }}>
              {idx + 1}/{suggestions.length}
            </span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setIdx(i => (i + 1) % suggestions.length)}
              style={{ padding: '2px 6px', fontSize: 12 }}
              aria-label={t.nextSuggestion}
            >→</button>
          </div>
        )}
      </div>
    </div>
  );
}

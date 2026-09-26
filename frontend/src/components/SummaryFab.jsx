import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLang } from '../lib/context';
import { api } from '../lib/api';

// Line icons. Emoji glyphs render differently on every platform and read as
// placeholder art, so the few decorative ones are drawn instead.
const IconUpload = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="var(--accent)"
       strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 16V4.5M12 4.5L8 8.5M12 4.5l4 4" /><path d="M4 15v3.5A1.5 1.5 0 005.5 20h13a1.5 1.5 0 001.5-1.5V15" />
  </svg>
);
const IconCheck = ({ size = 40 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="var(--success)"
       strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" /><path d="M8 12.4l2.8 2.8L16.2 9.6" />
  </svg>
);
const IconSpark = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 2.5l2.1 6.1 6.1 2.1-6.1 2.1-2.1 6.1-2.1-6.1L3.8 10.7l6.1-2.1z" />
  </svg>
);

const fill = (tpl, vars) =>
  (tpl || '').replace(/\{(\w+)\}/g, (m, k) => (vars[k] === undefined ? m : String(vars[k])));

const pick = (t, one, other, n) => fill(n === 1 ? t[one] : t[other], { n });

// English does not need plural distinctions in "actor"/"record"; the other two
// languages do, so both forms are kept in the table and chosen by count.
const EVIDENCE_TYPE = {
  'handle continuity':  'evTypeHandle',
  'stylometric similarity': 'evTypeStylometric',
  'shared active hours': 'evTypeTemporal',
  'shared infrastructure': 'evTypeInfrastructure',
};

const ID_COUNT = {
  PGP_KEY:     ['idPgpKeyCount1', 'idPgpKeys'],
  BTC_ADDRESS: ['idBtcAddressCount1', 'idBtcAddresses'],
  ONION_URL:   ['idOnionSiteCount1', 'idOnionSites'],
};

// The API returns a stable key plus the substitution values, so the sentence can
// be assembled in the reader's language. Unknown keys fall back to the server's
// English prose rather than rendering an empty section.
function renderSection(t, sec) {
  const f = sec.facts || {};
  switch (sec.key) {
    case 'investigation':
      return [t.sumInvestigation, fill(t.sumInvestigationBody, f)];
    case 'no_actors':
      return [t.sumNoActors, t.sumNoActorsBody];
    case 'who_found': {
      const forum = f.forum_count
        ? fill(t.sumForumFound, {
            users: pick(t, 'nUsersOne', 'nUsersOther', f.forum_count),
            handles: f.forum_handles,
            extra: f.forum_extra > 0 ? fill(t.sumAndMore, { n: f.forum_extra }) : '',
          })
        : '';
      const market = f.market_count
        ? fill(t.sumMarketFound, {
            vendors: pick(t, 'nVendorsOne', 'nVendorsOther', f.market_count),
            handles: f.market_handles,
            extra: f.market_extra > 0 ? fill(t.sumAndMore, { n: f.market_extra }) : '',
          })
        : '';
      return [t.sumWhoFound, fill(t.sumWhoFoundBody, {
        actors: pick(t, 'nActorsOne', 'nActorsOther', f.total), forum, market,
      })];
    }
    case 'analysed':
      return [t.sumAnalysed, fill(t.sumAnalysedBody, {
        records: pick(t, 'nRecordsOne', 'nRecordsOther', f.total_events),
      })];
    case 'identity_none':
      return [t.sumIdentityNone, t.sumIdentityNoneBody];
    case 'identity_matching':
      return [t.sumIdentity, fill(t.sumIdentityBody, {
        evidence: pick(t, 'nEvidenceOne', 'nEvidenceOther', f.evidence),
        supporting: pick(t, 'nItemsOne', 'nItemsOther', f.supporting),
        conflicting: pick(t, 'nItemsOne', 'nItemsOther', f.conflicting),
      })];
    case 'strongest_lead': {
      const typeKey = EVIDENCE_TYPE[f.evidence_type];
      return [t.sumStrongest, fill(t.sumStrongestBody, {
        handle_a: f.handle_a,
        handle_b: f.handle_b,
        evidence_type: typeKey ? t[typeKey] : f.evidence_type,
        weight: f.weight,
      })];
    }
    case 'crypto_clues': {
      const parts = (f.parts || []).map(p => {
        const keys = ID_COUNT[p.key];
        return keys ? fill(p.n === 1 ? t[keys[0]] : t[keys[1]], { n: p.n }) : `${p.n}`;
      });
      return [t.sumCrypto, fill(t.sumCryptoBody, { parts: parts.join(', ') })];
    }
    case 'coordinated':
      return [t.sumCoordinated, fill(t.sumCoordinatedBody, {
        groups: pick(t, 'nGroupsOne', 'nGroupsOther', f.groups),
      })];
    case 'notes':
      return [t.sumNotes, fill(t.sumNotesBody, {
        notes: pick(t, 'nNotesOne', 'nNotesOther', f.notes),
      })];
    case 'case_status':
      return [t.sumStatus, fill(t.sumStatusBody, {
        status: String(f.status || '').toUpperCase() === 'OPEN'
          ? t.caseStatusOpen
          : f.status,
      })];
    default:
      return [sec.label, sec.body];
  }
}

export default function SummaryFab({ caseId }) {
  const { lang, t } = useLang();
  const [open, setOpen]       = useState(false);
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState(null);
  const [error, setError]     = useState('');

  const generate = async () => {
    setLoading(true); setError('');
    try {
      const data = await api.getSummary(caseId);
      setSummary(data);
    } catch (err) {
      setError(err.message || t.summaryFailed);
    }
    setLoading(false);
  };

  const downloadBlank = (url, filename) => {
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.target = '_blank';
    document.body.appendChild(a); a.click(); a.remove();
  };

  return (
    <>
      {/* FAB */}
      <motion.button
        whileHover={{ scale: 1.05, boxShadow: '0 8px 24px rgba(22,101,52,0.35)' }}
        whileTap={{ scale: 0.95 }}
        className="btn btn-primary fab"
        style={{ padding: '10px 18px', fontSize: 13, fontWeight: 600 }}
        onClick={() => { setOpen(true); if (!summary) generate(); }}
        id="generate-summary-fab"
      >
        <span style={{ display: 'flex' }}><IconSpark /></span> {t.generateSummary}
      </motion.button>

      {/* Modal */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed', inset: 0, background: 'var(--bg-overlay)',
              zIndex: 300, display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end',
              padding: '80px 24px 80px 24px',
            }}
            onClick={e => e.target === e.currentTarget && setOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, y: 24, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 24, scale: 0.97 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="card"
              style={{ width: '100%', maxWidth: 540, maxHeight: '70vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
            >
              {/* Header */}
              <div style={{
                padding: '20px 24px', borderBottom: '1px solid var(--border)',
                display: 'flex', alignItems: 'center', gap: 12,
              }}>
                <div style={{ fontWeight: 700, fontSize: 16, flex: 1 }}>{t.summaryTitle}</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => downloadBlank(api.exportCSV(caseId), 'investigation.csv')}
                  >{t.exportCSV}</button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => window.open(api.exportJSON(caseId), '_blank')}
                  >{t.exportJSON}</button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => window.open(api.exportReport(caseId, lang), '_blank')}
                  >{t.exportReport}</button>
                </div>
                <button className="btn btn-ghost btn-icon" onClick={() => setOpen(false)}>✕</button>
              </div>

              {/* Body */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
                {loading && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-tertiary)' }}>
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                      style={{ width: 16, height: 16, border: '2px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%' }}
                    />
                    {t.generating_s}
                  </div>
                )}
                {error && <p style={{ color: 'var(--danger)', fontSize: 14 }}>{error}</p>}
                {summary && (
                  <div>
                    {/* Stats row */}
                    {summary.stats && (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
                        {[
                          [t.sumStatActors, summary.stats.total_actors],
                          [t.events,        summary.stats.total_events],
                          [t.sumStatEvidence, summary.stats.evidence_items],
                        ].map(([label, val]) => (
                          <div key={label} style={{
                            padding: '12px 14px', background: 'var(--bg)',
                            border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', textAlign: 'center',
                          }}>
                            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>{val ?? '—'}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Sections */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      {((summary.summary_sections && summary.summary_sections.length)
                        ? summary.summary_sections
                        : (summary.summary_paragraphs || []).map(p => {
                            const cut = p.indexOf(': ');
                            return cut > 0
                              ? { label: p.slice(0, cut), body: p.slice(cut + 2) }
                              : { label: '', body: p };
                          })
                      ).map((sec, i) => {
                        const [label, body] = renderSection(t, sec);
                        return (
                          <div key={i}>
                            {label && (
                              <div style={{
                                fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
                                letterSpacing: '0.06em', color: 'var(--text-tertiary)',
                                marginBottom: 5,
                              }}>{label}</div>
                            )}
                            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.65, color: 'var(--text-primary)' }}>
                              {body}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Footer refresh */}
              {summary && !loading && (
                <div style={{ padding: '12px 24px', borderTop: '1px solid var(--border)' }}>
                  <button className="btn btn-ghost btn-sm" onClick={generate} style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                    ↻ {t.regenerate}
                  </button>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

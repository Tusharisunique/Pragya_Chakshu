import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLang } from '../lib/context';
import LangToggle from '../components/LangToggle';
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

// Simulates a live streaming feed of records being ingested
function useFeed(active) {
  const [items, setItems] = useState([]);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!active) { clearInterval(timerRef.current); return; }

    const SAMPLE_TYPES  = ['post_observed', 'vendor_observed', 'listing_observed', 'pgp_found', 'wallet_found'];
    const SAMPLE_SRCS   = ['dread_forum', 'alphav2_market', 'incognito_market', 'telegram_scrape'];
    const SAMPLE_ACTORS = ['user_0x41', 'v_nk99', 'shadow_x', 'rxdark', 'anon_99', 'buyer_zz'];

    let count = 0;
    timerRef.current = setInterval(() => {
      const type   = SAMPLE_TYPES[Math.floor(Math.random() * SAMPLE_TYPES.length)];
      const source = SAMPLE_SRCS[Math.floor(Math.random() * SAMPLE_SRCS.length)];
      const actor  = SAMPLE_ACTORS[Math.floor(Math.random() * SAMPLE_ACTORS.length)];
      count++;
      setItems(prev => [{
        id: count,
        ts: new Date().toLocaleTimeString(),
        type, source, actor,
      }, ...prev].slice(0, 40));
    }, 300);

    return () => clearInterval(timerRef.current);
  }, [active]);

  return items;
}

const TYPE_COLOR = {
  post_observed:    'var(--info)',
  vendor_observed:  'var(--success)',
  listing_observed: 'var(--warning)',
  pgp_found:        'var(--accent)',
  wallet_found:     'var(--danger)',
};

// ---- Correlation progress bar -----------------------------------------------
function CorrProgress({ progress, message, found }) {
  const pct = Math.min(100, Math.max(0, progress || 0));
  return (
    <div style={{ textAlign: 'left', maxWidth: 480, margin: '0 auto' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
      }}>
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
          style={{ width: 14, height: 14, border: '2px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%', flexShrink: 0 }}
        />
        <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
          Correlating actors...
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-tertiary)' }}>
          {pct.toFixed(0)}%
        </span>
      </div>

      {/* Progress bar */}
      <div style={{
        height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden', marginBottom: 12,
      }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4 }}
          style={{ height: '100%', background: 'var(--accent)', borderRadius: 3 }}
        />
      </div>

      <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 4 }}>
        {message}
      </div>
      {found > 0 && (
        <div style={{ fontSize: 12, color: 'var(--success)', marginTop: 4 }}>
          {found} actor link{found !== 1 ? 's' : ''} identified so far
        </div>
      )}
    </div>
  );
}

export default function IngestionScreen({ caseData, user, onDone, onBack }) {
  const { t } = useLang();
  const [path, setPath]         = useState(null);       // 'crawler' | 'manual'
  const [ingesting, setIngesting] = useState(false);
  const [done, setDone]         = useState(false);
  const [error, setError]       = useState('');
  const [maxEvents, setMaxEvents] = useState(500);

  // Correlation job state
  const [corrRunning, setCorrRunning]   = useState(false);
  const [corrProgress, setCorrProgress] = useState(0);
  const [corrMessage, setCorrMessage]   = useState('');
  const [corrFound, setCorrFound]       = useState(0);
  const pollRef = useRef(null);

  const feed = useFeed(ingesting);
  const feedRef = useRef(null);

  // auto-scroll feed to top
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = 0;
  }, [feed]);

  // Clean up polling on unmount
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const startIngestion = async () => {
    setError('');
    setIngesting(true);
    try {
      await api.loadSlice(caseData.case_id, maxEvents);
      setIngesting(false);
      setDone(true);
    } catch (err) {
      setIngesting(false);
      setError(err.message || 'Ingestion failed.');
    }
  };

  const startCorrelation = async () => {
    setCorrRunning(true);
    setCorrProgress(0);
    setCorrMessage('Starting correlation engine...');
    setCorrFound(0);
    setError('');

    try {
      // Kick off the background job - returns immediately
      await api.runCorrelation(caseData.case_id);

      // Poll for real progress every 1.5 seconds
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.getCorrelationStatus(caseData.case_id);
          setCorrProgress(status.progress_pct || 0);
          setCorrMessage(status.message || '');
          setCorrFound(status.found || 0);

          if (status.done) {
            clearInterval(pollRef.current);
            pollRef.current = null;
            setCorrProgress(100);
            // Brief pause so user sees 100% before transitioning
            setTimeout(() => onDone(), 600);
          }
        } catch {
          // Polling errors are transient - keep polling
        }
      }, 1500);
    } catch (err) {
      setCorrRunning(false);
      setError(err.message || 'Failed to start correlation. Check backend.');
    }
  };

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--bg)',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Header */}
      <header style={{
        display: 'flex', alignItems: 'center', padding: '0 24px',
        height: 56, background: 'var(--bg-card)', borderBottom: '1px solid var(--border)', gap: 12,
      }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>{t.back || 'Back'}</button>
        <div style={{ flex: 1, fontWeight: 600, fontSize: 15 }}>{caseData.name}</div>
        <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{t.ingestionTitle}</span>
        <LangToggle />
      </header>

      <main style={{ flex: 1, maxWidth: 800, margin: '0 auto', width: '100%', padding: '48px 24px' }}>

        {/* Title */}
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>{t.ingestionTitle}</h1>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 40, fontSize: 15 }}>{t.ingestDesc}</p>

        {/* Path selection */}
        {!path && !ingesting && !done && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}
          >
            {[
              { id: 'crawler', icon: '\u{1F504}', label: t.crawlerOption, desc: t.crawlerDesc },
              { id: 'manual',  icon: '\u{1F4C2}', label: t.manualOption,  desc: t.manualDesc  },
            ].map(opt => (
              <motion.button
                key={opt.id}
                whileHover={{ y: -2, boxShadow: 'var(--shadow-lg)' }}
                whileTap={{ scale: 0.98 }}
                className="card"
                style={{
                  padding: '32px 28px', textAlign: 'left', cursor: 'pointer',
                  border: '2px solid var(--border)', background: 'var(--bg-card)',
                  display: 'flex', flexDirection: 'column', gap: 12,
                  transition: 'box-shadow 200ms, border-color 200ms, transform 200ms',
                }}
                onClick={() => setPath(opt.id)}
                id={`ingest-${opt.id}`}
              >
                <span style={{ fontSize: 32 }}>{opt.icon}</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 6 }}>{opt.label}</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.5 }}>{opt.desc}</div>
                </div>
              </motion.button>
            ))}
          </motion.div>
        )}

        {/* Crawler config */}
        {path === 'crawler' && !ingesting && !done && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="card"
            style={{ padding: '32px' }}
          >
            <h2 style={{ fontSize: 17, fontWeight: 600, marginBottom: 20 }}>{t.crawlerOption}</h2>
            <div style={{ marginBottom: 24 }}>
              <label className="label">{t.sliceLabel}</label>
              <select
                className="input"
                value={maxEvents}
                onChange={e => setMaxEvents(Number(e.target.value))}
                style={{ maxWidth: 240 }}
              >
                {[100, 250, 500, 1000, 2000].map(v => (
                  <option key={v} value={v}>{v.toLocaleString()} events</option>
                ))}
              </select>
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              <button className="btn btn-secondary" onClick={() => setPath(null)}>{t.cancel}</button>
              <motion.button
                whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                className="btn btn-primary btn-lg"
                onClick={startIngestion}
                id="start-ingest-btn"
              >
                {t.loadSlice}
              </motion.button>
            </div>
          </motion.div>
        )}

        {/* Manual import */}
        {path === 'manual' && !ingesting && !done && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="card"
            style={{ padding: '32px' }}
          >
            <h2 style={{ fontSize: 17, fontWeight: 600, marginBottom: 20 }}>{t.manualOption}</h2>
            <div
              style={{
                border: '2px dashed var(--border)', borderRadius: 'var(--radius)',
                padding: '48px 32px', textAlign: 'center', color: 'var(--text-tertiary)',
                marginBottom: 24, cursor: 'pointer',
              }}
              onClick={() => document.getElementById('file-upload')?.click()}
            >
              <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'center' }}>
                <IconUpload />
              </div>
              <div style={{ fontSize: 14 }}>Drop a JSON/CSV file here, or click to browse</div>
              <input id="file-upload" type="file" accept=".json,.csv" style={{ display: 'none' }}
                onChange={() => { setPath('crawler'); startIngestion(); }}
              />
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-tertiary)', marginBottom: 20 }}>
              {t.ingestManualNote}

            </p>
            <div style={{ display: 'flex', gap: 12 }}>
              <button className="btn btn-secondary" onClick={() => setPath(null)}>{t.cancel}</button>
              <button className="btn btn-primary" onClick={() => { setPath('crawler'); startIngestion(); }}>
                {t.loadDefaultDataset}
              </button>
            </div>
          </motion.div>
        )}

        {/* Live preview during ingestion */}
        {ingesting && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                style={{ width: 16, height: 16, border: '2px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%' }}
              />
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{t.ingesting}</span>
            </div>

            <div className="card" style={{ overflow: 'hidden' }}>
              <div style={{
                padding: '10px 16px', background: 'var(--bg-elevated)',
                borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  {t.livePreview}
                </span>
                <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-tertiary)' }}>
                  {feed.length} records
                </span>
              </div>
              <div ref={feedRef} style={{ maxHeight: 320, overflowY: 'auto', padding: '0' }}>
                <AnimatePresence initial={false}>
                  {feed.map(item => (
                    <motion.div
                      key={item.id}
                      initial={{ opacity: 0, y: -8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2 }}
                      className="feed-item"
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '70px 1fr 1fr 1fr',
                        gap: 12, padding: '8px 16px',
                        borderBottom: '1px solid var(--border)',
                        fontSize: 12, alignItems: 'center',
                      }}
                    >
                      <span style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                        {item.ts}
                      </span>
                      <span style={{
                        fontWeight: 500,
                        color: TYPE_COLOR[item.type] || 'var(--text-secondary)',
                        fontFamily: 'var(--font-mono)', fontSize: 11,
                      }}>
                        {item.type}
                      </span>
                      <span style={{ color: 'var(--text-secondary)' }}>{item.source}</span>
                      <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                        {item.actor}
                      </span>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        )}

        {/* Done state - Start Correlation */}
        {done && !corrRunning && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ textAlign: 'center', padding: '48px 0' }}
          >
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'center' }}>
              <IconCheck />
            </div>
            <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8, color: 'var(--success)' }}>
              {t.ingestionDone}
            </div>
            <p style={{ color: 'var(--text-secondary)', marginBottom: 36, fontSize: 15 }}>
              Data loaded. The system is ready to compute relationships between actors.
            </p>
            {error && (
              <p style={{ color: 'var(--danger)', marginBottom: 20, fontSize: 14 }}>{error}</p>
            )}
            <motion.button
              whileHover={{ scale: 1.03, boxShadow: '0 4px 20px rgba(22,101,52,0.3)' }}
              whileTap={{ scale: 0.97 }}
              className="btn btn-primary btn-lg"
              onClick={startCorrelation}
              id="start-corr-btn"
              style={{ fontSize: 16, padding: '14px 36px' }}
            >
              {t.startCorr}
            </motion.button>
          </motion.div>
        )}

        {/* Correlation running - real progress polling */}
        {corrRunning && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ padding: '48px 0', textAlign: 'center' }}
          >
            <CorrProgress
              progress={corrProgress}
              message={corrMessage}
              found={corrFound}
            />
          </motion.div>
        )}

        {/* Error outside done state */}
        {error && !done && (
          <p style={{ marginTop: 20, color: 'var(--danger)', fontSize: 13 }}>{error}</p>
        )}
      </main>
    </div>
  );
}

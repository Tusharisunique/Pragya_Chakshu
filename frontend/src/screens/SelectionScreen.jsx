import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLang } from '../lib/context';
import { api } from '../lib/api';
import LangToggle from '../components/LangToggle';

// Line icons drawn in the current text colour so they inherit the theme.
const IconSearch = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
  </svg>
);
const IconUsers = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <circle cx="9" cy="8" r="3.2" /><path d="M3.5 19a5.5 5.5 0 0111 0" />
    <path d="M16 5.5a3.2 3.2 0 010 6" /><path d="M17.5 14.2A5.5 5.5 0 0121 19" />
  </svg>
);
const IconGlobe = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17" />
    <path d="M12 3.5c2.2 2.4 3.4 5.4 3.4 8.5S14.2 18.1 12 20.5c-2.2-2.4-3.4-5.4-3.4-8.5S9.8 5.9 12 3.5z" />
  </svg>
);
const IconNote = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <path d="M5 4.5h14v15H5z" /><path d="M8.5 9h7M8.5 12.5h7M8.5 16h4" />
  </svg>
);
const IconFolio = ({ size = 34 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
       aria-hidden="true">
    <path d="M3.5 7.5h6.2l1.8 2.2h9v9.3a1.5 1.5 0 01-1.5 1.5H5a1.5 1.5 0 01-1.5-1.5z" />
    <path d="M8 13.2h8M8 16.4h5" />
  </svg>
);

const STATUS_BADGE = {
  OPEN:   { cls: 'badge-success', label: null },
  CLOSED: { cls: 'badge-default', label: null },
};

export default function SelectionScreen({ user, onSelect, onSignOut }) {
  const { t } = useLang();
  const [cases, setCases]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [creating, setCreating] = useState(false);
  const [name, setName]         = useState('');
  const [desc, setDesc]         = useState('');
  const [saving, setSaving]     = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [error, setError]       = useState('');

  const load = () => {
    setLoading(true);
    api.getCases(user.id)
      .then(data => { setCases(Array.isArray(data) ? data : []); setLoading(false); })
      .catch(() => { setCases([]); setLoading(false); });
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError('');
    try {
      const c = await api.createCase({ name: name.trim(), description: desc.trim(), owner_id: user.id });
      setCreating(false);
      setName(''); setDesc('');
      onSelect(c, true); // isNew=true → go to ingestion screen
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  };

  const handleDelete = async (caseId, e) => {
    e.stopPropagation();
    if (!window.confirm(t.deleteConfirm)) return;
    setDeleting(caseId);
    try {
      await api.deleteCase(caseId);
      setCases(prev => prev.filter(c => c.case_id !== caseId));
    } catch {}
    setDeleting(null);
  };

  const fmt = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg)',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Nav */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        height: 56,
        background: 'var(--bg-card)',
        borderBottom: '1px solid var(--border)',
        gap: 12,
      }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-primary)', flex: 1, fontFamily: 'Yatra One, cursive' }}>
          {t.appName}
        </span>
        <LangToggle />
        <button className="btn btn-ghost btn-sm" onClick={onSignOut}>{t.signOut}</button>
      </header>

      <main style={{ flex: 1, padding: '48px 24px', maxWidth: 860, margin: '0 auto', width: '100%' }}>
        {/* Title row */}
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 32 }}>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
              {t.selectInv}
            </h1>
            <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
              Signed in as <span style={{ fontWeight: 600 }}>{user.id}</span>
            </p>
          </div>
          <motion.button
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            className="btn btn-primary"
            onClick={() => { setCreating(true); setError(''); }}
            id="new-investigation-btn"
          >
            + {t.newInv}
          </motion.button>
        </div>

        {/* Create modal */}
        <AnimatePresence>
          {creating && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              style={{
                position: 'fixed', inset: 0, background: 'var(--bg-overlay)',
                zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: 24,
              }}
              onClick={e => e.target === e.currentTarget && setCreating(false)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 16 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 16 }}
                transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                className="card"
                style={{ width: '100%', maxWidth: 440, padding: 32 }}
              >
                <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 24 }}>{t.newInv}</h2>
                <form onSubmit={handleCreate}>
                  <div style={{ marginBottom: 16 }}>
                    <label className="label">{t.invName}</label>
                    <input
                      className="input"
                      value={name}
                      onChange={e => setName(e.target.value)}
                      placeholder="e.g. Operation Neelkanth"
                      autoFocus
                      id="inv-name"
                    />
                  </div>
                  <div style={{ marginBottom: 24 }}>
                    <label className="label">{t.invDesc}</label>
                    <textarea
                      className="input"
                      value={desc}
                      onChange={e => setDesc(e.target.value)}
                      placeholder="Brief description of the investigation scope…"
                      rows={3}
                      id="inv-desc"
                    />
                  </div>
                  {error && (
                    <p style={{ fontSize: 13, color: 'var(--danger)', marginBottom: 16 }}>{error}</p>
                  )}
                  <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                    <button type="button" className="btn btn-secondary" onClick={() => setCreating(false)}>
                      {t.cancel}
                    </button>
                    <button type="submit" className="btn btn-primary" disabled={saving || !name.trim()} id="inv-create">
                      {saving ? '…' : t.create}
                    </button>
                  </div>
                </form>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Case list */}
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-tertiary)' }}>
            Loading…
          </div>
        ) : cases.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="card"
            style={{ padding: '60px 32px', textAlign: 'center' }}
          >
            <div style={{ marginBottom: 18, display: 'flex', justifyContent: 'center' }}>
              <IconFolio />
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: 15 }}>{t.noInvestigations}</p>
            <button
              className="btn btn-primary"
              style={{ marginTop: 20 }}
              onClick={() => setCreating(true)}
            >
              + {t.newInv}
            </button>
          </motion.div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
            {cases.map((c, i) => (
              <motion.div
                key={c.case_id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                className="card"
                style={{
                  padding: '20px',
                  cursor: 'pointer',
                  position: 'relative',
                  transition: 'box-shadow 150ms, border-color 150ms',
                }}
                onClick={() => onSelect(c, false)} // isNew=false → go straight to dashboard
                onMouseEnter={e => e.currentTarget.style.boxShadow = 'var(--shadow)'}
                onMouseLeave={e => e.currentTarget.style.boxShadow = 'var(--shadow-sm)'}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span
                    className={`badge ${STATUS_BADGE[c.status]?.cls || 'badge-default'}`}
                    style={{ fontSize: 10 }}
                  >
                    {c.status === 'OPEN' ? t.open : t.closed}
                  </span>
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ padding: '3px 6px', fontSize: 11, color: 'var(--text-tertiary)' }}
                    onClick={e => handleDelete(c.case_id, e)}
                    disabled={deleting === c.case_id}
                    title={t.deleteInv}
                  >
                    {deleting === c.case_id ? '…' : '✕'}
                  </button>
                </div>

                <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-primary)', marginBottom: 6, lineHeight: 1.3 }}>
                  {c.name}
                </div>
                {c.description && (
                  <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.4 }}>
                    {c.description.slice(0, 80)}{c.description.length > 80 ? '…' : ''}
                  </p>
                )}
                <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                  {t.lastUpdated}: {fmt(c.updated_at || c.created_at)}
                </div>

                {/* Continue arrow */}
                <div style={{
                  position: 'absolute', bottom: 18, right: 18,
                  color: 'var(--accent)', fontSize: 18, opacity: 0.6,
                }}>
                  →
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

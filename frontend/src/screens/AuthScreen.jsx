import { useState, useEffect, useCallback } from 'react';
import { motion, useReducedMotion, AnimatePresence } from 'framer-motion';
import { useLang } from '../lib/context';
import { storeUser } from '../lib/context';
import LangToggle from '../components/LangToggle';

// Minimal client-side auth: hash the password with a simple djb2 for storage
function hashPw(pw) {
  let h = 5381;
  for (let i = 0; i < pw.length; i++) h = ((h << 5) + h) ^ pw.charCodeAt(i);
  return (h >>> 0).toString(16);
}

const STORE_KEY = 'pc_accounts';
function getAccounts() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; }
  catch { return {}; }
}
function saveAccounts(obj) { localStorage.setItem(STORE_KEY, JSON.stringify(obj)); }

const BRAND_INITIAL_SIZE = 64;
const BRAND_FINAL_SIZE = 32; // Matches var(--text-2xl) for consistency with index.css
const TRIGGER_OFFSET = 0;
const TRANSITION_DISTANCE = 500;

function interpolate(progress, inputRange, outputRange, options = {}) {
  const { clamp = false } = options;
  const [inMin, inMax] = inputRange;
  const [outMin, outMax] = outputRange;
  let t = (progress - inMin) / (inMax - inMin);
  if (clamp) t = Math.max(0, Math.min(1, t));
  return outMin + t * (outMax - outMin);
}

export default function AuthScreen({ onAuth, scrollContainerRef }) {
  const { t } = useLang();
  const [mode, setMode] = useState('login');
  const [id, setId]     = useState('');
  const [pw, setPw]     = useState('');
  const [pw2, setPw2]   = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [scrollProgress, setScrollProgress] = useState(0);
  const reducedMotion = useReducedMotion();

  // Derived values from scroll progress
  const brandFontSize = interpolate(scrollProgress, [0, 1], [BRAND_INITIAL_SIZE, BRAND_FINAL_SIZE]);
  const brandY = interpolate(scrollProgress, [0, 1], [0, -170]); // Move up by 170px to sit above card
  const taglineOpacity = interpolate(scrollProgress, [0, 0.5], [1, 0], { clamp: true }); // Fade tagline out halfway
  const cardOpacity = interpolate(scrollProgress, [0.4, 1], [0, 1], { clamp: true });
  const cardY = interpolate(scrollProgress, [0.4, 1], [40, 0], { clamp: true });

  // Scroll listener to update progress state
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef?.current;
    if (!container || reducedMotion) return;
    const scrollTop = container.scrollTop;
    const progress = Math.min(Math.max((scrollTop - TRIGGER_OFFSET) / TRANSITION_DISTANCE, 0), 1);
    setScrollProgress(progress);
  }, [scrollContainerRef, reducedMotion]);

  useEffect(() => {
    const container = scrollContainerRef?.current;
    if (!container || reducedMotion) return;
    // Ensure we start at the top
    container.scrollTop = 0;
    setScrollProgress(0);
    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, [scrollContainerRef, reducedMotion, handleScroll]);

  // For reduced motion: jump to final state
  useEffect(() => {
    if (reducedMotion && scrollContainerRef?.current) {
      scrollContainerRef.current.scrollTop = TRANSITION_DISTANCE;
      setScrollProgress(1);
    }
  }, [reducedMotion, scrollContainerRef]);

  const submit = (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const accounts = getAccounts();
    const hashed   = hashPw(pw);

    setTimeout(() => {
      setLoading(false);
      if (mode === 'register') {
        if (pw !== pw2) { setError('Passwords do not match.'); return; }
        if (pw.length < 6) { setError('Password must be at least 6 characters.'); return; }
        if (!id.trim()) { setError('Investigator ID is required.'); return; }
        if (accounts[id.trim()]) { setError('Investigator ID already exists.'); return; }
        const newAccounts = { ...accounts, [id.trim()]: hashed };
        saveAccounts(newAccounts);
        const user = { id: id.trim(), firstLogin: true };
        storeUser(user);
        onAuth(user);
      } else {
        const stored = accounts[id.trim()];
        if (!stored || stored !== hashed) { setError(t.authError); return; }
        const user = { id: id.trim(), firstLogin: false };
        storeUser(user);
        onAuth(user);
      }
    }, 400);
  };

  return (
    <div style={{
      minHeight: `calc(100vh + ${TRANSITION_DISTANCE}px)`, // Allow scrolling
      background: 'var(--bg)',
      padding: '0',
    }}>
      {/* Lang toggle top-right */}
      <div style={{ position: 'fixed', top: 16, right: 20, zIndex: 100 }}>
        <LangToggle />
      </div>

      {/* Sticky container that holds the animation in view */}
      <div style={{
        position: 'sticky',
        top: 0,
        height: '100vh',
        height: '100svh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}>

        {/* Brand — animated via scroll */}
        <motion.div
          style={{
            position: 'absolute',
            textAlign: 'center',
            willChange: 'transform, opacity',
            transformOrigin: 'center center',
            // Animate up to make room for the card
            transform: `translateY(${brandY}px)`,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            zIndex: 20,
          }}
        >
          <motion.div
            style={{
              fontWeight: 700,
              color: 'var(--text-primary)',
              letterSpacing: '-0.5px',
              fontFamily: 'Yatra One, cursive',
              lineHeight: 1.1,
              fontSize: `${brandFontSize}px`,
              transition: 'none', // Managed by scroll interpolation
            }}
          >
            {t.appName}
          </motion.div>
          <motion.div
            style={{
              fontSize: 14,
              color: 'var(--text-tertiary)',
              marginTop: 8,
              lineHeight: 1.4,
              opacity: taglineOpacity,
            }}
          >
            {t.tagline}
          </motion.div>
        </motion.div>

        {/* Scroll indicator — subtle hint */}
        {!reducedMotion && (
          <motion.div
            style={{
              position: 'absolute',
              bottom: 32,
              left: '50%',
              transform: 'translateX(-50%)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 8,
              color: 'var(--text-tertiary)',
              fontSize: 11,
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
              pointerEvents: 'none',
              opacity: interpolate(scrollProgress, [0, 0.2], [1, 0], { clamp: true }),
            }}
            initial={false}
            animate={{ y: [0, 8, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          >
            Scroll
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.5 }}>
              <path d="M12 5v14M19 12l-7 7-7-7" />
            </svg>
          </motion.div>
        )}

        {/* Login Card — fades in and slides up during scroll */}
        <motion.div
          style={{
            position: 'absolute',
            width: '100%',
            maxWidth: 380,
            padding: '0 24px',
            zIndex: 10,
            // Offset downward so it sits correctly below the finalized brand position
            marginTop: 140,
            opacity: cardOpacity,
            transform: `translateY(${cardY}px)`,
          }}
        >
          <motion.div
            className="card"
            style={{ padding: '32px' }}
          >
          {/* Mode toggle */}
          <div style={{
            display: 'flex',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '3px',
            marginBottom: '28px',
          }}>
            {['login', 'register'].map(m => (
              <button
                key={m}
                onClick={() => { setMode(m); setError(''); }}
                style={{
                  flex: 1,
                  padding: '7px 0',
                  fontSize: 13,
                  fontWeight: mode === m ? 600 : 400,
                  background: mode === m ? 'var(--bg-card)' : 'transparent',
                  color: mode === m ? 'var(--text-primary)' : 'var(--text-tertiary)',
                  border: mode === m ? '1px solid var(--border)' : '1px solid transparent',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  boxShadow: mode === m ? 'var(--shadow-sm)' : 'none',
                  transition: 'all 150ms',
                }}
              >
                {m === 'login' ? t.login : t.register}
              </button>
            ))}
          </div>

          <form onSubmit={submit}>
            <div style={{ marginBottom: 16 }}>
              <label className="label">{t.investigatorId}</label>
              <input
                className="input"
                type="text"
                placeholder={t.idPlaceholder}
                value={id}
                onChange={e => setId(e.target.value)}
                required
                id="auth-id"
              />
            </div>

            <div style={{ marginBottom: mode === 'register' ? 16 : 24 }}>
              <label className="label">{t.password}</label>
              <input
                className="input"
                type="password"
                placeholder="••••••••"
                value={pw}
                onChange={e => setPw(e.target.value)}
                required
                id="auth-password"
              />
            </div>

            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: mode === 'register' ? 'auto' : 0, opacity: mode === 'register' ? 1 : 0 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              style={{ overflow: 'hidden', marginBottom: 24 }}
            >
              <label className="label">{t.confirmPassword}</label>
              <input
                className="input"
                type="password"
                placeholder="••••••••"
                value={pw2}
                onChange={e => setPw2(e.target.value)}
                id="auth-password2"
              />
            </motion.div>

            {/* Error */}
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -4, height: 0, marginBottom: 0 }}
                  animate={{ opacity: 1, y: 0, height: 'auto', marginBottom: 16 }}
                  exit={{ opacity: 0, y: -4, height: 0, marginBottom: 0 }}
                  style={{
                    fontSize: 13,
                    color: 'var(--danger)',
                    background: 'var(--danger-bg)',
                    border: '1px solid #FECACA',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 12px',
                    overflow: 'hidden',
                  }}
                >
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            <button
              type="submit"
              className="btn btn-primary btn-lg"
              style={{ width: '100%', justifyContent: 'center' }}
              disabled={loading}
              id="auth-submit"
            >
              {loading ? '…' : (mode === 'login' ? t.login : t.register)}
            </button>
          </form>
        </motion.div>

        <p style={{ marginTop: 20, fontSize: 13, color: 'var(--text-tertiary)', textAlign: 'center' }}>
          {mode === 'login' ? t.noAccount : t.hasAccount}{' '}
          <button
            onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}
            style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 13, fontWeight: 500, padding: 0 }}
          >
            {mode === 'login' ? t.register : t.login}
          </button>
        </p>
      </motion.div>
      </div>
    </div>
  );
}
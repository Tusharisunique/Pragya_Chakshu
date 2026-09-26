import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { translations } from '../lib/i18n';

// ── Auth (localStorage mock — backend auth is out of sprint scope) ─────────
const AUTH_KEY = 'pc_user';

export function getStoredUser() {
  try { return JSON.parse(localStorage.getItem(AUTH_KEY)) || null; }
  catch { return null; }
}
export function storeUser(user) { localStorage.setItem(AUTH_KEY, JSON.stringify(user)); }
export function clearUser()     { localStorage.removeItem(AUTH_KEY); }

// ── Language context ──────────────────────────────────────────────────────────
const LangCtx = createContext(null);
export function useLang() { return useContext(LangCtx); }

export function LangProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem('pc_lang') || 'en');
  const t = translations[lang] || translations.en;

  const switchLang = useCallback((code) => {
    setLang(code);
    localStorage.setItem('pc_lang', code);
  }, []);

  /* Declare the active language on <html> so assistive technology applies the
     correct pronunciation rules for Devanagari/Tamil, and so script-aware CSS
     (:lang) can tune the wordmark. Without this, lang stays "en" forever. */
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  return <LangCtx.Provider value={{ lang, switchLang, t }}>{children}</LangCtx.Provider>;
}

// ── Investigation context ─────────────────────────────────────────────────────
const InvCtx = createContext(null);
export function useInv() { return useContext(InvCtx); }

export function InvProvider({ children }) {
  const [activeCase, setActiveCase] = useState(null);
  return (
    <InvCtx.Provider value={{ activeCase, setActiveCase }}>
      {children}
    </InvCtx.Provider>
  );
}

// ── Onboarding context ────────────────────────────────────────────────────────
// The tour is route-aware: it holds only whether it is open. Which step is
// showing is derived from the screen the user is actually on, so that state
// lives with the tour component (which stays mounted across navigation).
const OnboardCtx = createContext(null);
export function useOnboard() { return useContext(OnboardCtx); }

const ONBOARDED_KEY = 'pc_onboarded';

export function OnboardProvider({ children }) {
  const [active, setActive] = useState(false);

  const start = useCallback(() => {
    localStorage.removeItem(ONBOARDED_KEY);
    setActive(true);
  }, []);

  const finish = useCallback(() => {
    setActive(false);
    localStorage.setItem(ONBOARDED_KEY, '1');
  }, []);

  return (
    <OnboardCtx.Provider value={{ active, start, finish }}>
      {children}
    </OnboardCtx.Provider>
  );
}

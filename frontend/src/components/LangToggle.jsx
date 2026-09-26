import { useLang } from '../lib/context';
import { translations } from '../lib/i18n';

const LANGS = [
  { code: 'en', label: 'EN' },
  { code: 'hi', label: 'HI' },
  { code: 'ta', label: 'TA' },
];

export default function LangToggle() {
  const { lang, switchLang, t } = useLang();

  return (
    <div
      id="lang-toggle"
      style={{
        display: 'flex',
        alignItems: 'center',
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-full)',
        padding: '2px',
        gap: '1px',
      }}
      aria-label={t.langLabel || 'Language'}
    >
      {LANGS.map(l => (
        <button
          key={l.code}
          onClick={() => switchLang(l.code)}
          className="btn btn-sm"
          style={{
            borderRadius: 'var(--radius-full)',
            padding: '3px 10px',
            fontSize: '11px',
            fontWeight: lang === l.code ? 600 : 400,
            background: lang === l.code ? 'var(--bg-card)' : 'transparent',
            color: lang === l.code ? 'var(--text-primary)' : 'var(--text-tertiary)',
            border: lang === l.code ? '1px solid var(--border)' : '1px solid transparent',
            boxShadow: lang === l.code ? 'var(--shadow-sm)' : 'none',
          }}
          aria-pressed={lang === l.code}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}

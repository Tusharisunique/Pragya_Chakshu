import { useState, useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

import { getStoredUser, clearUser, useOnboard, useLang } from './lib/context';

import AuthScreen       from './screens/AuthScreen';
import SelectionScreen  from './screens/SelectionScreen';
import IngestionScreen  from './screens/IngestionScreen';
import GraphScreen      from './screens/GraphScreen';
import DashboardScreen  from './screens/DashboardScreen';

import NextStepsBar     from './components/NextStepsBar';
import SummaryFab       from './components/SummaryFab';
import OnboardingTour   from './components/OnboardingTour';

// Screen transition — calm, not flashy
const PAGE_VARIANTS = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1,  y: 0, transition: { duration: 0.28, ease: [0.16, 1, 0.3, 1] } },
  exit:    { opacity: 0,  y: -8, transition: { duration: 0.18 } },
};

function Screen({ children, id }) {
  return (
    <motion.div
      variants={PAGE_VARIANTS}
      initial="initial"
      animate="animate"
      exit="exit"
      style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}
    >
      {children}
    </motion.div>
  );
}

export default function App() {
  const { start: startOnboard } = useOnboard();
  const { t } = useLang();
  const scrollContainerRef = useRef(null);

  // ── App state machine ────────────────────────────────────────────────────
  // 'auth' | 'select' | 'ingest' | 'graph' | 'dash'
  const [screen, setScreen] = useState('auth');
  const [user, setUser]     = useState(() => getStoredUser());
  const [caseData, setCase] = useState(null);

  // On mount: if already logged in, skip auth
  useEffect(() => {
    if (user) setScreen('select');
  }, []);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleAuth = (u) => {
    setUser(u);
    setScreen('select');
    if (u.firstLogin && !localStorage.getItem('pc_onboarded')) {
      setTimeout(() => startOnboard(), 600);
    }
  };

  /**
   * When user selects a case:
   * - NEW case (just created, no personas yet) → ingestion screen first
   * - EXISTING case (already has data) → go straight to dashboard
   * We detect "existing" by checking if the case was returned from the list
   * (i.e. it already has a created_at in the past, not a fresh create response).
   * We use the `isNew` flag passed from SelectionScreen.
   */
  const handleSelectCase = (c, isNew = false) => {
    setCase(c);
    if (isNew) {
      setScreen('ingest');
    } else {
      setScreen('dash');
    }
  };

  const handleIngestionDone = () => setScreen('graph');

  const handleOpenWorkspace = () => setScreen('dash');

  // Dashboard -> graph. The graph is reachable from the workspace at any time
  // once correlation has run, and is re-fetched fresh from the API on entry.
  const handleOpenGraph = () => setScreen('graph');

  // Dashboard re-ingest: open ingest screen, but graph -> dashboard on done
  const handleReIngest = () => setScreen('ingest');

  const handleSignOut = () => {
    clearUser();
    setUser(null);
    setCase(null);
    setScreen('auth');
  };

  const handleBackToSelect = () => {
    setCase(null);
    setScreen('select');
  };

  // ── Next steps screen hint ────────────────────────────────────────────────
  const nextStepsScreen = screen === 'dash' ? 'dashboard'
    : screen === 'graph' ? 'graph'
    : screen === 'ingest' ? 'ingestion'
    : screen === 'select' ? 'selection'
    : 'auth';

  const showFab   = screen === 'dash' && caseData;
  const showNSBar = screen !== 'auth';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Onboarding tour — follows the current screen */}
      <OnboardingTour screen={screen} />

      {/* Page area */}
      <div
        ref={scrollContainerRef}
        style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', paddingBottom: showNSBar ? 40 : 0 }}
      >
        <AnimatePresence mode="wait">
          {screen === 'auth' && (
            <Screen key="auth" id="auth">
              <AuthScreen onAuth={handleAuth} scrollContainerRef={scrollContainerRef} />
            </Screen>
          )}

          {screen === 'select' && user && (
            <Screen key="select" id="select">
              <SelectionScreen
                user={user}
                onSelect={handleSelectCase}
                onSignOut={handleSignOut}
              />
            </Screen>
          )}

          {screen === 'ingest' && caseData && (
            <Screen key="ingest" id="ingest">
              <IngestionScreen
                caseData={caseData}
                user={user}
                onDone={handleIngestionDone}
                onBack={screen === 'ingest' && caseData ? handleBackToSelect : handleOpenWorkspace}
              />
            </Screen>
          )}

          {screen === 'graph' && caseData && (
            <Screen key="graph" id="graph">
              <GraphScreen
                caseData={caseData}
                onDone={handleOpenWorkspace}
              />
            </Screen>
          )}

          {screen === 'dash' && caseData && (
            <Screen key="dash" id="dash">
              <DashboardScreen
                caseData={caseData}
                user={user}
                onBack={handleBackToSelect}
                onSignOut={handleSignOut}
                onReIngest={handleReIngest}
                onOpenGraph={handleOpenGraph}
              />
            </Screen>
          )}
        </AnimatePresence>
      </div>

      {/* Summary FAB (dashboard only) */}
      {showFab && <SummaryFab caseId={caseData.case_id} />}

      {/* Persistent next-steps bar */}
      {showNSBar && (
        <NextStepsBar
          screen={nextStepsScreen}
          caseId={caseData?.case_id}
        />
      )}

      {/* Re-access the walkthrough from anywhere past auth (flow.md section 5) */}
      {screen !== 'auth' && (
        <button
          id="open-tour-btn"
          className="btn btn-secondary btn-sm"
          onClick={startOnboard}
          title={t.tourHelp}
          aria-label={t.tourHelp}
          style={{
            position: 'fixed', bottom: 52, right: 16, zIndex: 900,
            width: 30, height: 30, padding: 0, borderRadius: '50%',
            justifyContent: 'center', fontWeight: 700,
            boxShadow: 'var(--shadow-md)',
          }}
        >
          ?
        </button>
      )}
    </div>
  );
}

/**
 * OnboardingTour — route-aware, DOM-anchored spotlight tour.
 *
 * Steps are grouped by the screen they belong to (see t.steps in lib/i18n.js).
 * The tour follows the user: it always shows the steps for the screen they are
 * actually on, then waits on a non-blocking card until they navigate on. It
 * never covers the controls it is describing, so they stay clickable.
 *
 * If a step's target is not on screen (element not rendered yet), the tooltip
 * falls back to a centred card instead of pointing at nothing.
 */
import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import { useLang, useOnboard } from '../lib/context';

// Order the tour follows. Only routes listed here get steps.
const ROUTE_ORDER = ['select', 'ingest', 'graph', 'dash'];

const PADDING = 10;   // spotlight ring padding in px
const GAP = 14;       // tooltip gap from the target

function getAnchor(targetId) {
  if (!targetId) return null;
  const el = document.getElementById(targetId);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  // A zero-size or offscreen element is not a usable anchor.
  if (rect.width <= 0 || rect.height <= 0) return null;
  return rect;
}

// The tooltip wrapper is width:100% with 16px side padding, so the card's real
// left edge sits PADX px right of the wrapper's `left`. These helpers return
// wrapper coordinates with no CSS transform, which keeps clamping honest -- the
// old version mixed transform-based anchoring with transform-free clamps and
// pushed the card off-screen for wide targets such as the graph canvas.
const PADX = 16;
const TW   = Math.min(400, window.innerWidth - 40) - PADX * 2; // card width
const TH   = 220;                                              // approx height
const EDGE = 12;                                              // viewport margin

const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi));

function tooltipPosition(rect, placement, vw, vh) {
  // Off-route: sit at the bottom edge. Centring here would park the card on top
  // of whatever the user just opened (the new-investigation form, a modal),
  // which is the one thing the tour must not cover.
  if (!rect) {
    return { left: vw / 2 - PADX - TW / 2, top: vh - TH - EDGE };
  }

  const cardW = Math.min(TW, vw - EDGE * 2);
  const minL = EDGE, maxL = vw - cardW - EDGE;
  const minT = EDGE, maxT = vh - TH - EDGE;
  // Wrapper bounds must account for the card sitting PADX inside the wrapper.
  const toWrapper = cardLeft =>
    clamp(cardLeft - PADX, EDGE - PADX, vw - cardW - EDGE - PADX);
  const midY = clamp(rect.top + rect.height / 2 - TH / 2, minT, maxT);

  // Prefer the requested side, fall back to the opposite one when the target
  // is too close to that edge, and only clamp if neither side fits.
  const sides = {
    below: () => [rect.left + rect.width / 2 - cardW / 2, rect.bottom + GAP],
    above: () => [rect.left + rect.width / 2 - cardW / 2, rect.top - TH - GAP],
    right: () => [rect.right + GAP, rect.top + rect.height / 2 - TH / 2],
    left:  () => [rect.left - cardW - GAP, rect.top + rect.height / 2 - TH / 2],
  };
  const opposite = { below: 'above', above: 'below', right: 'left', left: 'right' };

  const fits = ([x, y]) =>
    x >= minL && x <= maxL && y >= minT && y <= maxT;

  // Prefer the requested side, then the opposite side, then above/below. A
  // full-width row (an actor row, the search field) leaves no room on either
  // side, so the vertical fallbacks have to be tried before clamping.
  const order = [...new Set([placement, opposite[placement], 'below', 'above'])];
  for (const side of order) {
    const pos = sides[side] && sides[side]();
    if (pos && fits(pos)) return { left: toWrapper(pos[0]), top: pos[1] };
  }
  const fallback = sides[placement] ? sides[placement]() : [vw / 2 - cardW / 2, vh / 2 - TH / 2];
  return { left: toWrapper(fallback[0]), top: clamp(fallback[1], minT, maxT) };
}

export default function OnboardingTour({ screen }) {
  const { t } = useLang();
  const { active, finish } = useOnboard();

  const stepGroups = t.steps || {};
  const flatSteps = useMemo(
    () => ROUTE_ORDER.flatMap(route => (stepGroups[route] || []).map(s => ({ ...s, route }))),
    [stepGroups],
  );
  const total = flatSteps.length;

  // Index into flatSteps of the first step for the current route, or -1.
  const routeStart = useCallback(
    route => flatSteps.findIndex(s => s.route === route),
    [flatSteps],
  );

  // The step we are on. Derived from the route so it tracks navigation.
  const [index, setIndex] = useState(0);

  // Collapsed to a launcher chip. Kept separate from `finish` so a stray click
  // never throws away the analyst's place in the tour.
  const [minimised, setMinimised] = useState(false);
  const tipRef = useRef(null);

  // Follow the user onto a route that has steps, but never drag them backwards
  // through the tour once they have moved past it.
  useEffect(() => {
    if (!active) return;
    const start = routeStart(screen);
    if (start === -1) return;
    setIndex(prev => {
      const prevRouteIdx = ROUTE_ORDER.indexOf(flatSteps[prev]?.route);
      const nextRouteIdx = ROUTE_ORDER.indexOf(screen);
      // Already on or past this route: leave the current step alone.
      if (nextRouteIdx <= prevRouteIdx) return prev;
      return start;
    });
  }, [screen, active, routeStart, flatSteps]);

  // Restart cleanly whenever the tour is opened.
  useEffect(() => {
    if (active) {
      setIndex(routeStart(screen) === -1 ? 0 : routeStart(screen));
      setMinimised(false);
    }
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  const isLast = index === total - 1;
  const current = flatSteps[index] || null;
  const onRoute = !!current && current.route === screen;

  // Clicking away from the tour collapses it to the launcher chip. Clicking the
  // element the step is describing is the tour doing its job, not a dismissal,
  // so that interaction is left alone.
  useEffect(() => {
    if (!active || minimised) return;
    const onDown = e => {
      if (tipRef.current && tipRef.current.contains(e.target)) return;
      if (current && current.targetId) {
        const anchor = document.getElementById(current.targetId);
        if (anchor && anchor.contains(e.target)) return;
      }
      setMinimised(true);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [active, minimised, current]);

  const [pos, setPos] = useState({ spotlight: null, tooltip: null });

  const recompute = useCallback(() => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const rect = current && current.route === screen ? getAnchor(current.targetId) : null;

    setPos({
      spotlight: rect
        ? {
            left:   rect.left   - PADDING,
            top:    rect.top    - PADDING,
            width:  rect.width  + PADDING * 2,
            height: rect.height + PADDING * 2,
          }
        : null,
      tooltip: tooltipPosition(rect, current?.placement, vw, vh),
    });
  }, [current, screen]);

  // Recompute on step/route change, on resize, and while the layout settles.
  useEffect(() => {
    if (!active) return;
    recompute();
    const settle = setTimeout(recompute, 120);
    const late   = setTimeout(recompute, 420);
    window.addEventListener('resize', recompute);
    window.addEventListener('scroll', recompute, true);
    return () => {
      clearTimeout(settle);
      clearTimeout(late);
      window.removeEventListener('resize', recompute);
      window.removeEventListener('scroll', recompute, true);
    };
  }, [active, index, screen, recompute]);

  // Clicking the highlighted control performs the step, so step past it. Without
  // this the tooltip keeps covering whatever that control just revealed (opening
  // the "new investigation" form put the tooltip straight over its Create
  // button). Matching on the element itself -- not a descendant -- keeps
  // exploratory clicks inside a target (a node in the graph, a row in the actor
  // list) from skipping the step.
  useEffect(() => {
    if (!active || !onRoute) return;
    const el = current && document.getElementById(current.targetId);
    if (!el) return;
    const advance = (e) => {
      if (e.target === el) setIndex(i => Math.min(total - 1, i + 1));
    };
    el.addEventListener('click', advance);
    return () => el.removeEventListener('click', advance);
  }, [active, onRoute, current, total]);

  if (!active || !current) return null;

  const { spotlight, tooltip } = pos;
  const stepNo = index + 1;

  if (minimised) {
    return (
      <motion.button
        initial={{ opacity: 0, y: 10, scale: 0.94 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        onClick={() => setMinimised(false)}
        title={t.tourResumeTitle}
        style={{
          position: 'fixed', right: 24, bottom: 24, zIndex: 1003,
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 16px', borderRadius: 999,
          background: 'var(--bg-card, #fff)', color: 'var(--text-primary)',
          border: '1px solid var(--border)', cursor: 'pointer',
          fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
          boxShadow: '0 6px 20px rgba(28,25,23,0.18)',
        }}
      >
        <span style={{
          width: 20, height: 20, borderRadius: '50%', display: 'grid',
          placeItems: 'center', background: 'var(--accent)', color: '#fff',
          fontSize: 11, lineHeight: 1,
        }}>{stepNo}</span>
        {t.tourResume}
      </motion.button>
    );
  }

  return (
    <>
      {/* Scrim — dims the page but never intercepts clicks, so the controls
          being described stay usable. The hole is the spotlight ring. */}
      <motion.div
        key="scrim"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(28,25,23,0.55)',
          pointerEvents: 'none',
        }}
      />

      {/* Spotlight ring — a transparent cut-out over the target */}
      {spotlight && (
        <motion.div
          key={`ring-${current.id}`}
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          style={{
            position: 'fixed',
            left:   spotlight.left,
            top:    spotlight.top,
            width:  spotlight.width,
            height: spotlight.height,
            border: '2px solid var(--accent)',
            borderRadius: 8,
            zIndex: 1001,
            pointerEvents: 'none',
            boxShadow: '0 0 0 4px rgba(22,101,52,0.18)',
          }}
        />
      )}

      {/* Tooltip card — the only part that takes pointer events */}
      <motion.div
        key={`tip-${current.id}`}
        initial={{ opacity: 0, y: 8, scale: 0.96 }}
        animate={{ opacity: 1, y: 0,  scale: 1 }}
        exit={{ opacity: 0, y: -8, scale: 0.96 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        style={{
          position: 'fixed',
          left:      tooltip?.left,
          top:       tooltip?.top,
          zIndex:    1002,
          width:     '100%',
          maxWidth:  400,
          padding:   '0 16px',
          boxSizing: 'border-box',
        }}
      >
        <div ref={tipRef} className="card" style={{ padding: '24px 24px 20px', pointerEvents: 'auto' }}>
          {/* Header row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <span style={{
              fontSize: 11, fontWeight: 600, color: 'var(--accent)',
              textTransform: 'uppercase', letterSpacing: '0.08em',
            }}>
              {t.step} {stepNo} {t.of} {total}
            </span>
            {/* Dot progress */}
            <div style={{ display: 'flex', gap: 4, marginLeft: 4 }}>
              {flatSteps.map((s, i) => (
                <div key={s.id} style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: i <= index ? 'var(--accent)' : 'var(--border)',
                  transition: 'background 200ms',
                }} />
              ))}
            </div>
            <button
              className="btn btn-ghost btn-sm"
              style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-tertiary)' }}
              onClick={finish}
            >
              {t.onboardSkip}
            </button>
          </div>

          <h3 style={{ fontSize: 17, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>
            {current.title}
          </h3>
          <p style={{ fontSize: 13, lineHeight: 1.65, color: 'var(--text-secondary)', marginBottom: 20 }}>
            {onRoute ? current.body : t.tourWaiting}
          </p>

          {/* Navigation */}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            {index > 0 && (
              <button className="btn btn-secondary btn-sm" onClick={() => setIndex(i => Math.max(0, i - 1))}>
                {t.onboardPrev}
              </button>
            )}
            <button
              className="btn btn-primary btn-sm"
              id={isLast ? 'onboard-done' : 'onboard-next'}
              onClick={() => (isLast ? finish() : setIndex(i => Math.min(total - 1, i + 1)))}
            >
              {isLast ? t.onboardDone : t.onboardNext}
            </button>
          </div>
        </div>
      </motion.div>
    </>
  );
}

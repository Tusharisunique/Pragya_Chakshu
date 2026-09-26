const BASE = 'http://localhost:8000/api';

async function req(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

export const api = {
  // Cases
  /** @param {string} [ownerId] filter to this investigator only */
  getCases:   (ownerId) => req('GET', ownerId ? `/cases?owner_id=${encodeURIComponent(ownerId)}` : '/cases'),
  createCase: (data)    => req('POST', '/cases', data),
  getCase:    (id)      => req('GET',  `/cases/${id}`),
  deleteCase: (id)      => req('DELETE', `/cases/${id}`),
  updateCase: (id, data)=> req('PATCH', `/cases/${id}`, data),

  // Personas / actors (with identifiers embedded)
  getPersonas: (caseId) => req('GET', `/cases/${caseId}/personas`),

  // Ingestion - POST /api/cases/{id}/ingest  body: { limit, source }
  loadSlice: (caseId, maxEvents) => req('POST', `/cases/${caseId}/ingest`, { limit: maxEvents || 500, source: 'all' }),
  getIngestionStatus: (caseId)   => req('GET',  `/cases/${caseId}/replay/status`),

  // Correlation / Graph
  /** Start background correlation job - returns immediately */
  runCorrelation:       (caseId) => req('POST', `/cases/${caseId}/correlation/run`),
  /** Poll correlation job progress: { done, computed, total, found, progress_pct, message } */
  getCorrelationStatus: (caseId) => req('GET',  `/cases/${caseId}/correlation/status`),
  getGraph:             (caseId) => req('GET',  `/cases/${caseId}/graph`),

  // Timeline per persona
  getTimeline: (caseId, personaId) => req('GET', `/cases/${caseId}/personas/${personaId}/timeline`),

  // Next steps
  getNextSteps: (caseId) => req('GET', `/cases/${caseId}/next-steps`),

  // Infrastructure indicators
  getInfrastructure: (caseId) => req('GET', `/cases/${caseId}/infrastructure`),

  // Search
  search: (caseId, query) => req('GET', `/cases/${caseId}/search?q=${encodeURIComponent(query)}`),

  // Notes
  getNotes: (caseId)       => req('GET',  `/cases/${caseId}/notes`),
  addNote:  (caseId, data) => req('POST', `/cases/${caseId}/notes`, data),

  // Summary & Export
  getSummary:   (caseId) => req('GET', `/cases/${caseId}/summary`),
  // These return URLs for direct browser navigation/download. The dossier is
  // rendered server-side, so the active language has to travel with the request.
  exportJSON:   (caseId) => `${BASE}/cases/${caseId}/export/json`,
  exportReport: (caseId, lang = 'en') =>
    `${BASE}/cases/${caseId}/export/dossier?lang=${encodeURIComponent(lang)}`,
  exportCSV:    (caseId) => `${BASE}/cases/${caseId}/export/csv`,
};

# Pragya Chakshu (प्रज्ञा चक्षु)

### Controlled Cybersecurity Research, Attribution & Forensic Intelligence Workstation

[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19.0-61DAFB.svg?logo=react&logoColor=black)](https://react.dev)
[![Cytoscape.js](https://img.shields.io/badge/Cytoscape.js-3.30-EA580C.svg)](https://js.cytoscape.org/)
[![Tailwind CSS v4](https://img.shields.io/badge/Tailwind_CSS-v4.0-38BDF8.svg?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![SQLite / Neo4j](https://img.shields.io/badge/Graph%20%26%20Relational-Dual--Engine-4F46E5.svg)](https://neo4j.com)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://python.org)

**Pragya Chakshu** (_Sanskrit: "The Eye of Wisdom"_) is a controlled cybersecurity research and forensic investigation platform designed to analyze threat actor operations, cross-platform pseudonym continuity, longitudinal behavioral rhythms, and shared hosting infrastructure across historical darknet archives.

The system integrates relational event storage, graph network analysis, natural language processing (NLP) stylometry, asynchronous time-cursor event replay, and cryptographic case dossier export into a dark-themed intelligence analyst workstation.
## The Tripartite Provenance Model

To prevent analytical bias, hallucination, and data contamination, every record, node, indicator, and relationship strictly enforces one of three provenance tags:

| Provenance      | Definition                                                                                         | Scope in System                                                                                                                  |
| :-------------- | :------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------- |
| **`RESEARCH`**  | Authentic historical research archives from darknet markets and forums.                            | Forum posts, timestamps, marketplace vendor listings, PGP public keys, interaction edges, and ground-truth references.           |
| **`DERIVED`**   | Algorithmic analytics, statistical models, and attribution hypotheses computed from research data. | Stylometric $K$ constants, diurnal histograms, multi-factor correlation scores, coordination strength %, and evaluation metrics. |
| **`SYNTHETIC`** | Controlled, safely simulated infrastructure indicators.                                            | Bulletproof hosting subnets, synthetic TLS certificates (JARM hashes), SSH host keys, and simulated hidden services.             |
## Core Capabilities

### Capability 1: Controlled Synthetic Infrastructure Attribution

Darknet operations route through Tor onion routing, which intentionally obscures origin server IPs and physical network topology. To demonstrate forensic infrastructure correlation safely without illegal active scanning:

- Generates realistic bulletproof hosting netblocks, ASN pools, and synthetic origin servers.
- Creates simulated TLS certificates with **JARM fingerprints** and SSH host keys (RSA/ED25519).
- Implements **co-hosting correlation (`CO_HOSTED_SERVER`)**: detects distinct `.onion` services sharing identical TLS certificates or SSH keys pointing back to a single physical server node.

### Capability 2: Actor Tracking, Profiling & Evaluation Mode

Correlates pseudonymous actors across disparate forums and marketplaces:

- **Authentic NLP Stylometry**:
  - **Yule’s Characteristic Constant $K$**: Computes vocabulary richness and word-recurrence invariance:
    $$K = 10^4 \cdot \frac{\sum m^2 V_m - N}{N^2}$$
  - **Lexical Diversity**: Type-Token Ratio (TTR) and word-length distributions.
  - **Punctuation Vector**: Normalized frequencies of commas, periods, exclamation, semicolons, and ellipses.
  - **Character 4-Grams**: Relative frequency distributions compared via cosine similarity.
  - **Language Verification**: English verification using function words and letter distributions.
- **Longitudinal Behavioral Profiling**:
  - Constructs **24-hour diurnal posting histograms (UTC 0..23)** from post timestamps.
  - Detects posting bursts ($\le 1\text{ hour}$), mean inactivity spans, and cadence.
  - Measures temporal curve compatibility via diurnal cosine similarity; flags schedules differing by $\ge 8\text{ hours}$ as schedule conflicts.
- **Multi-Factor Correlation Engine**:
  - Evaluates candidate pairs across weighted evidence signals:
    - Cryptographic PGP Key Match: **`+40.0`**
    - Handle Lexical Continuity: **`+25.0`**
    - NLP Stylometric Alignment: **`+25.0`** / Divergence: **`-20.0`**
    - Diurnal Temporal Overlap: **`+15.0`** / Conflicting Schedules: **`-25.0`**
    - Shared Crypto / Onion Indicators: **`+20.0`**
- **Human-in-the-Loop Evidence Challenge Workflow**:
  - Investigators can dispute specific evidence items (e.g., boilerplate greetings or shared VPNs).
  - The backend dynamically recalculates the relationship score and updates the graph edge.
  - Every challenge or restoration is permanently recorded in the `evidence_challenges` audit table.
- **Evaluation Mode & Benchmark Dashboard**:
  - Compares analytical attribution hypotheses against the hidden ground truth (`user-matching.tsv`).
  - Calculates contingency metrics: **True Positives (TP)**, **False Positives (FP)**, **False Negatives (FN)**, **Precision %**, **Recall %**, and **$F_1$ Score**.
  - Dynamic confidence threshold slider ($\tau \in [0, 100]$) to analyze precision-recall curves.
  - **Strict Boundary:** Ground truth is isolated from Investigator Mode to prevent circular attribution.

### Capability 3: Coordinated Activity Discovery

Identifies multi-actor collusion, astroturfing, and coordinated darknet campaigns:

- Detects multi-persona thread co-participation across historical forum discussions.
- Integrates interaction edge networks (`edges-2014-1.tsv`).
- Analyzes response latency ($\Delta t$) and rapid reply cadences ($\Delta t < 60\text{s}$).
- Categorizes coordination patterns: `HIGHLY_SYNCHRONIZED_CASCADE`, `FREQUENT_CO_PARTICIPATION`, and `OCCASIONAL_THREAD_INTERACTION`.
- Renders dashed cyan `COORDINATED_WITH` edges showing coordination percentage.

### Capability 4: Investigator Field Notes & Case Annotations

Enables intelligence analysts to document observations, forensic rationales, and hypotheses directly within the investigation graph:

- **Entity-Bound Notes**: Attach timestamps and notes to specific personas, posts, identifiers, or correlation edges.
- **Audited Provenance**: Every note records investigator ID, ISO UTC timestamp, entity label, and type.
- **Dossier & Chain of Custody Integration**: Field notes automatically compile into **Section 2** of the Printable Forensic Dossier and machine-readable JSON exports with SHA-256 seal integrity.
## Time-Cursor Replay Engine (SSE)

Pragya Chakshu features an asynchronous chronological replay engine:

- State machine with `RUNNING`, `PAUSED`, and `STOPPED` playback states.
- Configurable speed multipliers: **1x**, **5x**, **20x**, and **60x**.
- Advances historical time cursor chronologically through authentic dataset timestamps (`timestamp_occurred`).
- Emits real-time Server-Sent Events (`GET /api/cases/{case_id}/replay/stream`) to update the live graph canvas and event feed without polling.
## Forensic Case Dossier & Cryptographic Seal

Case documentation is exportable in two formats:

- **Printable Forensic HTML Dossier (`GET /api/cases/{case_id}/export/dossier`)**: Formatted for print or PDF generation, featuring case summary, KPIs, persona attribution inventory, **analyst field notes & annotations**, human challenge audit history, and provenance breakdown.
- **Structured JSON Export (`GET /api/cases/{case_id}/export/json`)**: Machine-readable forensic dossier.
- **Digital SHA-256 Seal**: The entire case state is serialized and hashed with SHA-256 to create an immutable cryptographic fingerprint locking the forensic state at the time of export.
## Interactive Graph Canvas

The Cytoscape-powered graph canvas is engineered for high readability and eliminates hairball clutter:

- **View Presets**:
  - **Core Investigation**: Focuses on Personas, Active Correlations, Coordination, Identifiers, and Infrastructure. Automatically filters out raw message boxes and structural `PART_OF` lines.
  - **Actor Attribution**: Focuses strictly on cross-platform identity links (`CORRELATED_WITH`) and PGP/BTC keys.
  - **Coordinated Activity**: Displays coordinated posting cliques and latency links.
  - **Infrastructure**: Displays physical servers, JARM TLS certificates, and Tor hidden services.
  - **Full Raw**: Unfiltered forensic topology.
- **Interactive Neighborhood Spotlight**: Clicking or hovering any node or edge dims all unrelated elements to **10% opacity**, isolating that entity's direct network.
- **Live Search & Locate**: Auto-pans and zooms to any persona handle, IP address, or onion URL.
- **Layout Switcher**: Force-Directed (Spaced CoSE with collision avoidance), Concentric (degree rings), Hierarchical Tree, and Circular layouts.
- **Interactive Legend**: Floating guide explaining entity colors and relationship line styles.
## Repository Structure

```
c:/projects/PC/
├── dataset/
│   └── sample/                     # Bundled Standalone Curated Dataset (~2.96 MB)
│       ├── forum/                  # Sample forum posts & user records
│       ├── market/                 # Sample vendor profiles & listings
│       ├── network/                # Sample interaction edges
│       └── user-matching.tsv       # Hidden ground-truth attribution pairs
│
├── backend/                        # FastAPI Python Backend
│   ├── adapters/                   # Streaming TSV Adapters & Normalizers
│   │   ├── evolution_forum.py      # Streams post.tsv & user.tsv (with dynamic offset)
│   │   ├── evolution_market.py     # Streams vendors.tsv & listings.tsv
│   │   ├── normalizer.py           # Regex extraction (PGP, BTC, .onion) & provenance
│   │   └── user_matching.py        # Ingests ground-truth user-matching.tsv
│   ├── analytics/                  # Core Forensic & Machine Learning Analytics
│   │   ├── behavioral.py           # 24h diurnal UTC histograms & scheduling comparison
│   │   ├── coordination.py         # Coordinated thread activity & reply latency (Δt)
│   │   ├── correlation.py          # Multi-signal persona correlation & human challenge
│   │   ├── evaluation.py           # Benchmark engine (Precision, Recall, F1 against GT)
│   │   └── stylometry.py           # NLP engine (Yule's K, TTR, 4-grams, punctuation)
│   ├── database/                   # Relational & Graph Storage
│   │   ├── neo4j_client.py         # Neo4j client with persistent NetworkX fallback
│   │   └── sqlite.py               # SQLite schema (10 relational tables)
│   ├── replay/                     # Asynchronous Replay Engine
│   │   ├── replay_engine.py        # Synchronous batch ingestion & entity creation
│   │   └── sse_stream.py           # Time-cursor SSE streaming state machine
│   ├── routers/                    # FastAPI REST & SSE Endpoints
│   │   ├── analytics.py            # Stylometry & behavioral profile endpoints
│   │   ├── cases.py                # Case CRUD endpoints
│   │   ├── coordination.py         # Coordinated activity detection endpoints
│   │   ├── correlation.py          # Persona correlation & challenge/restore endpoints
│   │   ├── evaluation.py           # Evaluation mode benchmark endpoints
│   │   ├── export.py               # Printable HTML dossier & JSON export
│   │   ├── graph.py                # Cytoscape-formatted graph query API
│   │   ├── infrastructure.py       # Controlled synthetic infrastructure endpoints
│   │   ├── notes.py                # Investigator field notes & annotations API
│   │   └── replay.py               # Replay control & SSE stream endpoint
│   ├── synthetic/                  # Controlled Synthetic Module
│   │   └── infrastructure.py       # Synthetic bulletproof servers, JARM & Tor services
│   ├── config.py                   # Central config (automatic sample/raw dataset fallback)
│   ├── main.py                     # FastAPI application factory & CORS setup
│   ├── requirements.txt            # Python dependencies
│   └── run.py                      # Uvicorn entry point (backend-only hot reload)
│
├── frontend/                       # Vite + React 19 + Tailwind CSS Frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── CorrelationInspector.jsx # Score breakdown, challenge modals, audit timeline
│   │   │   ├── EntityNotes.jsx          # Live investigator notes & annotation panel
│   │   │   ├── EventFeed.jsx            # Chronological live feed with provenance tags
│   │   │   ├── GraphCanvas.jsx          # Cytoscape canvas with presets & neighborhood spotlight
│   │   │   ├── Landing.jsx              # Case selection & initialization
│   │   │   ├── NodeInspector.jsx        # Multi-tab forensic entity inspector
│   │   │   └── Workspace.jsx            # 3-panel intelligence workstation layout
│   │   ├── api.js                  # Frontend API integration client
│   │   ├── App.jsx                 # Client-side router
│   │   ├── index.css               # Tailwind CSS imports
│   │   └── main.jsx                # Application root
│   ├── package.json
│   └── vite.config.js              # Vite dev server with /api proxy to port 8000
│
├── scratch/                        # Automated Integration Test Suites
│   ├── test_phase6.py              # Synthetic infrastructure attribution tests
│   ├── test_phase7.py              # Coordinated activity discovery tests
│   ├── test_phase8.py              # Evaluation mode benchmark tests
│   ├── test_phase8_matches.py      # Precision/recall ground-truth tests
│   └── test_phase9.py              # Case dossier export & SHA-256 seal tests
│
└── README.md                       # System documentation
```
## Quickstart & Setup Guide

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** and `npm`
- _(Optional)_ **Neo4j 5.0+** (The system automatically activates a persistent NetworkX JSON fallback if Neo4j is offline).
- **Zero Data Setup Needed**: The repository comes pre-bundled with `dataset/sample/` (~2.96 MB). The system detects and uses this automatically without requiring the 1.8 GB raw archive.

### 1. Clone the Repository

```bash
git clone https://github.com/Sneha07k/Pragya-Chakshu.git
cd Pragya-Chakshu
```

### 2. Backend Setup

Create and activate a virtual environment, install requirements, and launch the API server:

```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt

# Start Backend (Port 8000)
python -m backend.run
```

- Backend API documentation will be available at: **`http://localhost:8000/docs`**

### 3. Frontend Setup

In a separate terminal, install node dependencies and launch the Vite development server:

```bash
cd frontend
npm install
npm run dev
```

- Open your browser at: **`http://localhost:5173`**
## Verification & Test Suite

Run the automated integration test suite against the running backend:

```bash
# Capability 1: Controlled Synthetic Infrastructure
python scratch/test_phase6.py

# Capability 3: Coordinated Activity Discovery
python scratch/test_phase7.py

# Capability 2: Evaluation Mode Benchmark
python scratch/test_phase8_matches.py

# Forensic Dossier & SHA-256 Digital Seal Export
python scratch/test_phase9.py
```
## Ethical Boundary & Research Disclaimer

- **No Live Crawling**: Pragya Chakshu does not crawl, scan, probe, or connect to active darknet hidden services or live external networks.
- **Controlled Demonstration**: Infrastructure indicators for Capability 1 are synthetically simulated with explicit `SYNTHETIC` provenance tags.
- **Analytical Hypotheses**: Persona correlation scores reflect mathematical statistical alignment across available signals. They represent investigative hypotheses and do not constitute proof of real-world legal identity.

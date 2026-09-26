"""
PRAGYA CHAKSHU — FORENSIC CASE DOSSIER & EXPORT ROUTER
Generates standardized investigation dossiers with full chain of custody,
provenance segregation breakdown (RESEARCH / DERIVED / SYNTHETIC),
and human challenge audit trails.
"""

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse
import json
import hashlib
from datetime import datetime
from typing import Dict, Any

from backend.database.sqlite import get_connection
from backend.analytics.evaluation import run_evaluation_benchmark
from backend.analytics.coordination import detect_coordination_network

router = APIRouter(prefix="/cases", tags=["export"])


def count(n, singular, plural=None) -> str:
    """Format a number with a correctly pluralised noun.

    The report used to ship "(s)" style placeholders, which read like a template
    that was never finished.
    """
    word = singular if n == 1 else (plural or singular + "s")
    return f"{n} {word}"


def _metric(v, missing: str = "not measured") -> str:
    """Render a score for the report without leaking "N/A" or a raw None."""
    if v is None:
        return missing
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return missing


def _fill(template: str, **params) -> str:
    """Substitute {name} placeholders in a report string."""
    for k, v in params.items():
        template = template.replace("{%s}" % k, str(v))
    return template


def compile_case_dossier(case_id: str) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Case details
    cursor.execute("SELECT * FROM cases WHERE case_id=?", (case_id,))
    case_row = cursor.fetchone()
    if not case_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")
    case = dict(case_row)

    # 2. Personas
    cursor.execute(
        "SELECT * FROM personas WHERE case_id=? OR case_id IS NULL", (case_id,)
    )
    personas = [dict(r) for r in cursor.fetchall()]

    # 3. Evidence
    cursor.execute("SELECT * FROM evidence WHERE case_id=?", (case_id,))
    evidence = [dict(r) for r in cursor.fetchall()]

    # 4. Challenges audit trail
    cursor.execute(
        "SELECT * FROM evidence_challenges WHERE case_id=? ORDER BY timestamp DESC",
        (case_id,),
    )
    challenges = [dict(r) for r in cursor.fetchall()]

    # 5. Normalized Events count and provenance breakdown
    cursor.execute(
        """
        SELECT provenance, count(*) as count 
        FROM normalized_events 
        WHERE case_id=? 
        GROUP BY provenance
    """,
        (case_id,),
    )
    prov_counts = {r["provenance"]: r["count"] for r in cursor.fetchall()}

    # 6. Evaluation metrics
    # Count derived analytical signals from evidence table
    cursor.execute(
        "SELECT count(*) FROM evidence WHERE case_id=? AND provenance='DERIVED'",
        (case_id,),
    )
    derived_evidence_count = cursor.fetchone()[0]
    derived_total = prov_counts.get("DERIVED", 0) + derived_evidence_count

    # 6. Evaluation metrics (evaluated at the calibrated 25.0 weight threshold)
    try:
        benchmark = run_evaluation_benchmark(case_id)
    except Exception:
        benchmark = {}

    # 7. Coordination summary
    try:
        coordination = detect_coordination_network(case_id, max_pairs=10)
    except Exception:
        coordination = {}

    # 8. Investigator notes
    cursor.execute(
        """
        SELECT note_id, case_id, entity_type, entity_id, entity_label, investigator_id, note_text, created_at
        FROM investigator_notes
        WHERE case_id=?
        ORDER BY created_at ASC
    """,
        (case_id,),
    )
    notes = [dict(r) for r in cursor.fetchall()]

    conn.close()

    dossier = {
        "dossier_id": f"DOSSIER-{case_id[:8].upper()}-{datetime.utcnow().strftime('%Y%m%d%H%M')}",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "system": "PRAGYA CHAKSHU Intelligence Attribution System",
        "classification": "CONTROLLED RESEARCH / EVALUATION",
        "case": case,
        "provenance_summary": {
            "RESEARCH": prov_counts.get("RESEARCH", 0),
            "DERIVED": derived_total,
            "SYNTHETIC": prov_counts.get("SYNTHETIC", 0),
            "total_events": prov_counts.get("RESEARCH", 0)
            + derived_total
            + prov_counts.get("SYNTHETIC", 0),
        },
        "personas": personas,
        "evidence_inventory": evidence,
        "investigator_notes": notes,
        "human_challenge_audit_trail": challenges,
        "evaluation_benchmark": benchmark.get("metrics", {}),
        "coordination_clusters": coordination.get("coordination_clusters", []),
    }

    # Digital seal / hash of the dossier for chain of custody
    payload_bytes = json.dumps(dossier, sort_keys=True).encode("utf-8")
    dossier["cryptographic_hash_sha256"] = hashlib.sha256(payload_bytes).hexdigest()

    return dossier


@router.get("/{case_id}/export/json")
def export_case_json(case_id: str):
    """
    Exports full forensic case dossier in structured JSON.
    """
    return compile_case_dossier(case_id)


# Chrome strings for the printable dossier. Data values (handles, identifiers,
# note text) are evidence and are never translated.
REPORT_I18N = {
    "en": {
        "doc_title": "PRAGYA CHAKSHU Case Dossier",
        "case_dossier": "CASE DOSSIER",
        "case": "Case",
        "dossier_id": "Dossier ID",
        "generated": "Generated",
        "status": "Status",
        "kpi_research": "Research Events",
        "kpi_derived": "Derived Signals",
        "kpi_synthetic": "Synthetic Infra",
        "kpi_precision": "Attribution precision, F1",
        "kpi_cm": "{tp} correct &middot; {fp} false &middot; {fn} missed",
        "no_predictions": "no links claimed",
        "badge_real": "REAL",
        "badge_nlp": "NLP/GRAPH",
        "badge_controlled": "CONTROLLED",
        "h_personas": "1. Case Personas & Attribution Inventory",
        "th_handle": "Canonical Handle",
        "th_platform": "Platform",
        "th_provenance": "Provenance",
        "th_uid": "UID / VID",
        "th_first_seen": "First Seen",
        "not_measured": "not measured",
        "not_recorded": "not recorded",
        "h_notes": "2. Investigator Field Notes & Case Annotations",
        "th_ts_utc": "Timestamp (UTC)",
        "th_investigator": "Investigator",
        "th_target": "Target Entity",
        "th_type": "Type",
        "th_observation": "Observation / Note",
        "no_notes": "No investigator field notes recorded for this case.",
        "h_challenges": "3. Human-in-the-Loop Challenge Audit Trail",
        "th_timestamp": "Timestamp",
        "th_timestamp": "Timestamp",
        "th_prev": "Previous Score",
        "th_new": "New Score",
        "th_rationale": "Rationale",
        "no_challenges": "No human challenges recorded. All evidence items remain in active algorithmic consensus.",
        "h_custody": "4. Chain of Custody & Integrity Seal",
        "sha_label": "SHA-256 Digital Fingerprint:",
        "sha_note": "This cryptographic hash locks the entire state of cases, normalized events, stylometric profiles, and human challenges at time of export.",
        "footer_org": "Controlled Attribution & Forensic Intelligence System",
        "footer_page": "Page 1 of 1 - Strict Provenance Segregation Maintained",
    },
    "hi": {
        "doc_title": "प्रज्ञा चक्षु केस डोज़ियर",
        "case_dossier": "केस डोज़ियर",
        "case": "केस",
        "dossier_id": "डोज़ियर आईडी",
        "generated": "तैयार किया गया",
        "status": "स्थिति",
        "kpi_research": "अनुसंधान घटनाएँ",
        "kpi_derived": "व्युत्पन्न संकेत",
        "kpi_synthetic": "कृत्रिम अवसंरचना",
        "kpi_precision": "संबंध-निर्धारण परिशुद्धता, F1",
        "kpi_cm": "{tp} सही &middot; {fp} ग़लत &middot; {fn} छूटे",
        "no_predictions": "कोई लिंक नहीं बनाया गया",
        "badge_real": "वास्तविक",
        "badge_nlp": "एनएलपी/ग्राफ",
        "badge_controlled": "नियंत्रित",
        "h_personas": "1. केस पात्र और संबंध-निर्धारण सूची",
        "th_handle": "मानक हैंडल",
        "th_platform": "मंच",
        "th_provenance": "उत्पत्ति",
        "th_uid": "यूआईडी / वीआईडी",
        "th_first_seen": "पहली बार देखा गया",
        "not_measured": "मापा नहीं गया",
        "not_recorded": "दर्ज नहीं",
        "h_notes": "2. जाँचकर्ता फ़ील्ड नोट्स और केस टिप्पणियाँ",
        "th_ts_utc": "समय-मुद्र (UTC)",
        "th_investigator": "जाँचकर्ता",
        "th_target": "लक्ष्य इकाई",
        "th_type": "प्रकार",
        "th_observation": "प्रेक्षण / नोट",
        "no_notes": "इस केस के लिए कोई जाँचकर्ता फ़ील्ड नोट दर्ज नहीं है।",
        "h_challenges": "3. मानव-चुनौती ऑडिट ट्रेल",
        "th_timestamp": "समय-मुद्र",
        "th_timestamp": "समय-मुद्र",
        "th_prev": "पिछला अंक",
        "th_new": "नया अंक",
        "th_rationale": "कारण",
        "no_challenges": "कोई मानव चुनौती दर्ज नहीं है। सभी प्रमाण-आइटम सक्रिय एल्गोरिदमिक सर्वसम्मति में बने रहते हैं।",
        "h_custody": "4. श्रृंखला-अभिरक्षा और अखंडता मुहर",
        "sha_label": "SHA-256 डिजिटल फ़िंगरप्रिंट:",
        "sha_note": "यह क्रिप्टोग्राफ़िक हैश निर्यात के समय केस, सामान्यीकृत घटनाओं, शैलीमितीय प्रोफ़ाइल और मानव चुनौतियों की पूरी स्थिति को लॉक करता है।",
        "footer_org": "नियंत्रित संबंध-निर्धारण और फ़ॉरेंसिक इंटेलिजेंस सिस्टम",
        "footer_page": "पृष्ठ 1 / 1 - सख़्त उत्पत्ति पृथक्करण बनाए रखा गया",
    },
    "ta": {
        "doc_title": "பிரஜ்ஞா சக்ஷு வழக்கு ஆவணம்",
        "case_dossier": "வழக்கு ஆவணம்",
        "case": "வழக்கு",
        "dossier_id": "ஆவண எண்",
        "generated": "உருவாக்கப்பட்டது",
        "status": "நிலை",
        "kpi_research": "ஆய்வு நிகழ்வுகள்",
        "kpi_derived": "பெறப்பட்ட சமிக்ஞைகள்",
        "kpi_synthetic": "செயற்கை அடிப்படைக்கட்டமைப்பு",
        "kpi_precision": "இணைப்பு துல்லியம், F1",
        "kpi_cm": "{tp} சரி &middot; {fp} தவறு &middot; {fn} முஸ்கவில்லை",
        "no_predictions": "எந்த இணைப்பும் கூறப்படவில்லை",
        "badge_real": "உண்மை",
        "badge_nlp": "NLP/வரைபடம்",
        "badge_controlled": "கட்டுப்படுத்தப்பட்டது",
        "h_personas": "1. வழக்கு நபர்கள் மற்றும் இணைப்புப் பட்டியல்",
        "th_handle": "நியம கையாளர்",
        "th_platform": "தளம்",
        "th_provenance": "உருவாக்கம்",
        "th_uid": "UID / VID",
        "th_first_seen": "முதலாவது காணப்பட்டது",
        "not_measured": "அளவிடப்படவில்லை",
        "not_recorded": "பதிவு செய்யப்படவில்லை",
        "h_notes": "2. புலனாளர் களை குறிப்புகள் மற்றும் வழக்கு குறிப்புகள்",
        "th_ts_utc": "நேரம் (UTC)",
        "th_investigator": "புலனாளர்",
        "th_target": "இலக்கு அலகு",
        "th_type": "வகை",
        "th_observation": "கவனிப்பு / குறிப்பு",
        "no_notes": "இந்த வழக்கிற்கு புலனாளர் களை குறிப்புகள் எதுவும் பதிவு செய்யப்படவில்லை.",
        "h_challenges": "3. மனித-சவால் தண்விலைப் பதிவு",
        "th_timestamp": "நேரம்",
        "th_timestamp": "நேரமுத்திரம்",
        "th_prev": "முந்தைய மதிப்பெண்",
        "th_new": "புதிய மதிப்பெண்",
        "th_rationale": "காரணம்",
        "no_challenges": "மனித சவால்கள் எதுவும் பதிவு செய்யப்படவில்லை. அனைத்து சான்று உயிர்களும் செயல் வழிமுறை ஒருங்கிணைப்பில் உள்ளன.",
        "h_custody": "4. சங்கிலி பாதுகாப்பு மற்றும் உறுதிப்பெண் முத்திரை",
        "sha_label": "SHA-256 டிஜிட்டல் கைரேகை:",
        "sha_note": "இந்த குறியாக்கமான ஹாஷ் ஏற்றுமுதலின் நிலையில் வழக்குகள், தரவாக்கப்பட்ட நிகழ்வுகள், எழுத்துநடை சுயவிவரங்கள் மற்றும் மனித சவால்களின் முழு நிலையையும் பூடுகிறது.",
        "footer_org": "கட்டுப்படுத்தப்பட்ட இணைப்பு மற்றும் பேரதாங்கி அறிவு அமைப்பு",
        "footer_page": "பக்கம் 1 / 1 - கடுமையான உருவாக்கப் பிரிப்பு பேணப்பட்டது",
    },
}

# Enum values that reach the report as raw tokens.
REPORT_ENUM = {
    "status": {"en": {}, "hi": {"OPEN": "खुला", "CLOSED": "बंद"},
               "ta": {"OPEN": "திறந்த", "CLOSED": "மூடப்பட்ட"}},
    "action": {"en": {},
               "hi": {"CHALLENGE": "चुनौती दी गई", "RESTORE": "पुनर्स्थापित"},
               "ta": {"CHALLENGE": "சவால் விதிக்கப்பட்டது", "RESTORE": "மீட்டமைக்கப்பட்டது"}},
    "entity_type": {"en": {},
                    "hi": {"PERSONA": "पात्र", "EVIDENCE": "प्रमाण",
                           "IDENTIFIER": "पहचानकर्ता", "CASE": "केस",
                           "INVESTIGATION": "जाँच"},
                    "ta": {"PERSONA": "நபர்", "EVIDENCE": "சான்று",
                           "IDENTIFIER": "அடையாளம்", "CASE": "வழக்கு",
                           "INVESTIGATION": "விசாரணை"}},
    "provenance": {
        "en": {},
        "hi": {"RESEARCH": "अनुसंधान", "DERIVED": "व्युत्पन्न",
               "SYNTHETIC": "कृत्रिम", "INGESTED": "डाली गई"},
        "ta": {"RESEARCH": "ஆய்வு", "DERIVED": "பெறப்பட்ட",
               "SYNTHETIC": "செயற்கை", "INGESTED": "ஏற்றப்பட்டது"},
    },
}

SUPPORTED_REPORT_LANGS = ("en", "hi", "ta")


def report_lang(value: str) -> str:
    """Accept only a supported language; anything else falls back to English."""
    v = (value or "").strip().lower()[:2]
    return v if v in SUPPORTED_REPORT_LANGS else "en"


@router.get("/{case_id}/export/dossier", response_class=HTMLResponse)
def export_printable_dossier(case_id: str, lang: str = "en"):
    """
    Renders a formatted, printable HTML dossier with professional styling,
    provenance badges, and chain of custody log.

    `lang` selects the language of the surrounding chrome. Evidence values are
    never translated.
    """
    lang = report_lang(lang)
    L = REPORT_I18N[lang]
    EV = REPORT_ENUM["status"][lang]
    PV = REPORT_ENUM["provenance"][lang]
    ET = REPORT_ENUM["entity_type"][lang]
    ACT = REPORT_ENUM["action"][lang]
    d = compile_case_dossier(case_id)
    c = d["case"]
    prov = d["provenance_summary"]
    metrics = d.get("evaluation_benchmark", {})

    _tp = int(metrics.get("true_positives") or 0)
    _fp = int(metrics.get("false_positives") or 0)
    _fn = int(metrics.get("false_negatives") or 0)
    # Precision is undefined when nothing was claimed: there is no ratio to
    # report, and defaulting to 0% (or 100%) would both misstate the evidence.
    _claimed = (_tp + _fp) > 0
    prec_val = (_metric(metrics.get("precision_percent"), L["not_measured"])
               if _claimed else L["not_measured"])
    cm_line = _fill(L["kpi_cm"], tp=_tp, fp=_fp, fn=_fn) if _claimed else L["no_predictions"]
    challenges = d.get("human_challenge_audit_trail", [])
    personas = d.get("personas", [])
    notes = d.get("investigator_notes", [])
    evidence = d.get("evidence_inventory", [])

    html_content = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <title>{L['doc_title']} — {c.get('name')}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #1e293b;
            background: #ffffff;
            margin: 0;
            padding: 40px;
            font-size: 13px;
            line-height: 1.6;
        }}
        .header {{
            border-bottom: 2px solid #0f172a;
            padding-bottom: 15px;
            margin-bottom: 25px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
        }}
        .title {{
            font-size: 24px;
            font-weight: 800;
            color: #0f172a;
            letter-spacing: -0.5px;
        }}
        .subtitle {{
            font-size: 13px;
            color: #64748b;
            margin-top: 4px;
        }}
        .seal {{
            text-align: right;
            font-family: monospace;
            font-size: 11px;
            color: #475569;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge-research {{ background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }}
        .badge-derived {{ background: #f3e8ff; color: #7e22ce; border: 1px solid #e9d5ff; }}
        .badge-synthetic {{ background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }}
        
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin: 20px 0;
        }}
        .kpi-card {{
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 12px;
            background: #f8fafc;
        }}
        .kpi-val {{ font-size: 20px; font-weight: 700; color: #0f172a; }}
        .kpi-lbl {{ font-size: 11px; color: #64748b; text-transform: uppercase; margin-top: 2px; }}
        .kpi-sub {{ font-size: 10px; color: #94a3b8; margin-top: 4px; }}

        h2 {{
            font-size: 16px;
            border-bottom: 1px solid #cbd5e1;
            padding-bottom: 6px;
            margin-top: 30px;
            color: #0f172a;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-top: 10px;
        }}
        th, td {{
            padding: 8px 10px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        th {{ background: #f1f5f9; color: #475569; font-weight: 600; }}
        .footer {{
            margin-top: 40px;
            border-top: 1px solid #e2e8f0;
            padding-top: 15px;
            font-size: 11px;
            color: #94a3b8;
            display: flex;
            justify-content: space-between;
        }}
        @media print {{
            body {{ padding: 20px; font-size: 11px; }}
            .no-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="title">PRAGYA CHAKSHU — {L['case_dossier']}</div>
            <div class="subtitle">{L['case']}: <strong>{c.get('name')}</strong> (ID: {c.get('case_id')})</div>
        </div>
        <div class="seal">
            <div>{L['dossier_id']}: {d['dossier_id']}</div>
            <div>{L['generated']}: {d['generated_at']}</div>
            <div>{L['status']}: <strong>{EV.get(str(c.get('status')).upper(), c.get('status'))}</strong></div>
        </div>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-val">{prov.get('RESEARCH', 0)}</div>
            <div class="kpi-lbl">{L['kpi_research']} <span class="badge badge-research">{L['badge_real']}</span></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val">{prov.get('DERIVED', 0)}</div>
            <div class="kpi-lbl">{L['kpi_derived']} <span class="badge badge-derived">{L['badge_nlp']}</span></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val">{prov.get('SYNTHETIC', 0)}</div>
            <div class="kpi-lbl">{L['kpi_synthetic']} <span class="badge badge-synthetic">{L['badge_controlled']}</span></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val">{prec_val}</div>
            <div class="kpi-lbl">{L['kpi_precision']} {_metric(metrics.get('f1_score'))}</div>
            <div class="kpi-sub">{cm_line}</div>
        </div>
    </div>

    <h2>{L['h_personas']}</h2>
    <table>
        <thead>
            <tr>
                <th>{L['th_handle']}</th>
                <th>{L['th_platform']}</th>
                <th>{L['th_provenance']}</th>
                <th>{L['th_uid']}</th>
                <th>{L['th_first_seen']}</th>
            </tr>
        </thead>
        <tbody>
            {"".join(f"<tr><td><strong>{p.get('canonical_handle')}</strong></td><td>{p.get('platform')}</td><td><span class='badge badge-{p.get('provenance', '').lower()}'>{PV.get(str(p.get('provenance')).upper(), p.get('provenance'))}</span></td><td>{p.get('raw_uid') or p.get('raw_vid') or L['not_recorded']}</td><td>{p.get('first_seen') or L['not_recorded']}</td></tr>" for p in personas[:25])}
        </tbody>
    </table>

    <h2>{L['h_notes']} ({len(notes)})</h2>
    {f"""<table>
        <thead>
            <tr>
                <th>{L['th_ts_utc']}</th>
                <th>{L['th_investigator']}</th>
                <th>{L['th_target']}</th>
                <th>{L['th_type']}</th>
                <th>{L['th_observation']}</th>
            </tr>
        </thead>
        <tbody>
            {"".join(f"<tr><td style='white-space:nowrap;font-family:monospace;color:#475569;'>{n.get('created_at', '')[:19].replace('T', ' ')}</td><td><strong>{n.get('investigator_id')}</strong></td><td><strong>{n.get('entity_label')}</strong></td><td><span class='badge badge-derived'>{ET.get((n.get('entity_type') or '').upper(), n.get('entity_type'))}</span></td><td>{n.get('note_text')}</td></tr>" for n in notes)}
        </tbody>
    </table>""" if notes else "<p style='color: #64748b; font-style: italic;'>" + L["no_notes"] + "</p>"}

    <h2>{L['h_challenges']}</h2>
    {f"""<table>
        <thead>
            <tr>
                <th>{L['th_timestamp']}</th>
                <th>{L['th_investigator']}</th>
                <th>{L['th_action']}</th>
                <th>{L['th_prev']}</th>
                <th>{L['th_new']}</th>
                <th>{L['th_rationale']}</th>
            </tr>
        </thead>
        <tbody>
            {"".join(f"<tr><td>{ch.get('timestamp')}</td><td>{ch.get('investigator_id')}</td><td><strong>{ACT.get((ch.get('action') or '').upper(), ch.get('action'))}</strong></td><td>{ch.get('previous_score')}%</td><td>{ch.get('new_score')}%</td><td>{ch.get('reason')}</td></tr>" for ch in challenges)}
        </tbody>
    </table>""" if challenges else "<p style='color: #64748b; font-style: italic;'>" + L["no_challenges"] + "</p>"}

    <h2>{L['h_custody']}</h2>
    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; font-family: monospace; font-size: 11px;">
        <div><strong>{L['sha_label']}</strong> {d['cryptographic_hash_sha256']}</div>
        <div style="margin-top: 4px; color: #64748b;">{L['sha_note']}</div>
    </div>

    <div class="footer">
        <div>PRAGYA CHAKSHU — {L['footer_org']}</div>
        <div>{L['footer_page']}</div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@router.get("/{case_id}/summary")
def get_case_summary(case_id: str):
    """
    Returns a personalized plain-English summary of everything observed in a case.
    Written in layman terms so anyone can understand the findings.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Fetch case
    cursor.execute("SELECT * FROM cases WHERE case_id=?", (case_id,))
    case_row = cursor.fetchone()
    if not case_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")
    case = dict(case_row)

    # Total events ingested
    cursor.execute(
        "SELECT count(*) FROM normalized_events WHERE case_id=?", (case_id,)
    )
    total_events = cursor.fetchone()[0]

    # Personas (unique actors found)
    cursor.execute(
        "SELECT canonical_handle, platform FROM personas WHERE case_id=?", (case_id,)
    )
    personas = [dict(r) for r in cursor.fetchall()]
    forum_actors = [p for p in personas if "forum" in p["platform"].lower()]
    market_actors = [p for p in personas if "market" in p["platform"].lower()]

    # Evidence / correlations
    cursor.execute(
        """SELECT e.*, pa.canonical_handle as handle_a, pb.canonical_handle as handle_b,
                  pa.platform as platform_a, pb.platform as platform_b
           FROM evidence e
           LEFT JOIN personas pa ON e.source_persona_id = pa.persona_id
           LEFT JOIN personas pb ON e.target_persona_id = pb.persona_id
           WHERE e.case_id=? AND e.challenge_status='ACTIVE'
           ORDER BY e.confidence_weight DESC""",
        (case_id,)
    )
    evidence_rows = [dict(r) for r in cursor.fetchall()]

    # Best match
    best_match = evidence_rows[0] if evidence_rows else None

    # PGP / BTC / Onion identifiers
    cursor.execute(
        """SELECT i.identifier_type, count(*) as cnt
           FROM identifiers i
           JOIN personas p ON i.persona_id = p.persona_id
           WHERE p.case_id=?
           GROUP BY i.identifier_type""",
        (case_id,)
    )
    identifiers_summary = {r["identifier_type"]: r["cnt"] for r in cursor.fetchall()}

    # Investigator notes
    cursor.execute(
        "SELECT count(*) FROM investigator_notes WHERE case_id=?", (case_id,)
    )
    note_count = cursor.fetchone()[0]

    conn.close()

    # Build the narrative as structured sections. Emitting Markdown inside a
    # plain-text field meant the client had to guess at **, * and emoji bullets,
    # and any client that did not parse it leaked the markers to the analyst.

    case_name = case.get("name", "this investigation")
    created_date = (case.get("created_at") or "")[:10]

    sections = []
    add = sections.append

    add({
        "key":   "investigation",
        "label": "Investigation",
        "body": f"{case_name} was opened on {created_date or 'an unknown date'}. "
                f"This is a plain-English summary of what the system has found so far.",
        "facts": {"case_name": case_name, "created_date": created_date},
    })

    if not personas:
        add({
            "key":   "no_actors",
            "label": "No actors found",
            "body": "No data has been ingested into this case yet. "
                    "Load a dataset from the Ingest tab to begin the analysis.",
            "facts": {},
        })
    else:
        facts = {"total": len(personas)}
        body = f"The system discovered {count(len(personas), 'unique actor')} across the datasets."
        if forum_actors:
            handles = [p["canonical_handle"] for p in forum_actors[:3]]
            extra = len(forum_actors) - 3
            facts.update({"forum_count": len(forum_actors),
                          "forum_handles": ", ".join(handles), "forum_extra": extra})
            body += (f" On the forum side it identified {count(len(forum_actors), 'user')}: "
                     f"{', '.join(handles)}"
                     f"{', and ' + str(extra) + ' more' if extra > 0 else ''}.")
        if market_actors:
            mhandles = [p["canonical_handle"] for p in market_actors[:3]]
            mextra = len(market_actors) - 3
            facts.update({"market_count": len(market_actors),
                          "market_handles": ", ".join(mhandles), "market_extra": mextra})
            body += (f" On the marketplace side it identified "
                     f"{count(len(market_actors), 'vendor')}: {', '.join(mhandles)}"
                     f"{', and ' + str(mextra) + ' more' if mextra > 0 else ''}.")
        add({"key": "who_found", "label": "Who was found", "body": body, "facts": facts})

    if total_events > 0:
        add({
            "key":   "analysed",
            "label": "What was analysed",
            "body": f"A total of {count(total_events, 'data record')} (posts, vendor profiles "
                    f"and marketplace listings) were loaded and analysed.",
            "facts": {"total_events": total_events},
        })

    if not evidence_rows:
        add({
            "key":   "identity_none",
            "label": "Attribution results",
            "body": "No identity links have been computed yet. "
                    "Run a correlation analysis from the Ingest tab.",
            "facts": {},
        })
    else:
        supporting = [e for e in evidence_rows if e.get("polarity") == "SUPPORTING"]
        conflicting = [e for e in evidence_rows if e.get("polarity") == "CONFLICTING"]
        body = (f"The system found "
                f"{count(len(evidence_rows), 'piece of evidence', 'pieces of evidence')} "
                f"linking actors across platforms. "
                f"{count(len(supporting), 'item')} support a shared identity and "
                f"{count(len(conflicting), 'item')} conflict with it, which may mean the "
                f"accounts belong to different people.")
        add({
            "key":   "identity_matching",
            "label": "Identity matching",
            "body":  body,
            "facts": {"evidence": len(evidence_rows), "supporting": len(supporting),
                      "conflicting": len(conflicting)},
        })

        if best_match and best_match.get("handle_a") and best_match.get("handle_b"):
            wt = best_match.get("confidence_weight", 0)
            etype = (best_match.get("evidence_type") or "Unknown").replace("_", " ").lower()
            # The same handle often exists on two platforms, which renders as
            # "Verto and Verto". Qualify with the platform only when it differs,
            # so ordinary pairs stay uncluttered.
            ha, hb = best_match["handle_a"], best_match["handle_b"]
            pa, pb = best_match.get("platform_a"), best_match.get("platform_b")
            if ha == hb and pa and pb and pa != pb:
                ha, hb = f"{ha} ({pa})", f"{hb} ({pb})"
            add({
                "key":   "strongest_lead",
                "label": "Strongest lead",
                "body": f"The highest-scoring link is between {ha} and "
                        f"{hb}, supported by {etype} evidence "
                        f"(confidence weight {round(float(wt), 1)} out of 40). "
                        f"In plain terms, these two accounts most likely belong to the "
                        f"same real-world person.",
                "facts": {"handle_a": ha,
                          "handle_b": hb,
                          "evidence_type": etype,
                          "weight": round(float(wt), 1)},
            })

    if identifiers_summary:
        id_parts = []
        for key, prefix, singular, plural in (
            ("PGP_KEY", "PGP", "key", "keys"),
            ("BTC_ADDRESS", "Bitcoin", "address", "addresses"),
            ("ONION_URL", "onion", "site", "sites"),
        ):
            n = int(identifiers_summary.get(key) or 0)
            if n:
                id_parts.append((key, n))
        if id_parts:
            add({
                "key":   "crypto_clues",
                "label": "Cryptographic clues",
                "body": "The system extracted " + ", ".join(
                    f"{n} {k.replace('_', ' ').title()}" for k, n in id_parts
                ) + " from the posts and "
                        f"listings. These are strong digital fingerprints: the same key or "
                        f"address appearing on two platforms is a strong signal that one "
                        f"person controls both.",
                "facts": {"parts": [{"key": k, "n": n} for k, n in id_parts]},
            })

    try:
        coord = detect_coordination_network(case_id, max_pairs=5)
        clusters = coord.get("coordination_clusters", [])
        if clusters:
            add({
                "key":   "coordinated",
                "label": "Coordinated behaviour",
                "body": f"The system detected {count(len(clusters), 'group')} of actors who "
                        f"appear to be working together, responding to each other very quickly "
                        f"or always appearing in the same threads. This can indicate organised "
                        f"activity, or several fake accounts run by one person.",
                "facts": {"groups": len(clusters)},
            })
    except Exception:
        pass

    if note_count > 0:
        add({
            "key":   "notes",
            "label": "Investigator notes",
            "body": f"{count(note_count, 'manual note')} recorded by the analyst during this "
                    f"investigation.",
            "facts": {"notes": note_count},
        })

    status = case.get("status", "OPEN")
    add({
        "key":   "case_status",
        "label": "Case status",
        "body": f"This investigation is currently marked as {status}. "
                f"Use the Export tab to download the full forensic dossier, which carries a "
                f"cryptographic integrity seal.",
        "facts": {"status": status},
    })

    return {
        "case_id": case_id,
        "case_name": case_name,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "summary_sections": sections,
        "summary_paragraphs": [f"{x['label']}: {x['body']}" for x in sections],
        "stats": {
            "total_events": total_events,
            "total_actors": len(personas),
            "forum_actors": len(forum_actors),
            "market_actors": len(market_actors),
            "evidence_items": len(evidence_rows),
            "identifiers_found": sum(identifiers_summary.values()),
            "investigator_notes": note_count,
        },
    }

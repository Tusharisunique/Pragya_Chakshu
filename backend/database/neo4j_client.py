import os
import json
import logging
import re
import tempfile
from neo4j import GraphDatabase, exceptions
import networkx as nx
from backend.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, BASE_DIR

logger = logging.getLogger(__name__)

GRAPH_FALLBACK_PATH = str(BASE_DIR / "backend" / "data" / "graph_fallback.json")
_driver = None
_nx_graph = None
_use_fallback = False

# Post/Listing node ids are derived from dataset-local record ids (post:133), so
# they used to collide across every case that ingested the same slice, which
# leaked other investigations' actors into a case graph. They are now scoped by
# case as post:<case_id>:<pid>. These constants drive the cache migration below.
_ARTIFACT_PREFIX = {"Post": "post:", "Listing": "listing:"}
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _unscoped_artifact(node_id, attrs, case_ids):
    """Return (prefix, record_id) if this Post/Listing node still uses a
    case-agnostic id, else None."""
    prefix = _ARTIFACT_PREFIX.get(attrs.get("type"))
    if not prefix or not node_id.startswith(prefix):
        return None
    rest = node_id[len(prefix):]
    if ":" in rest:
        head, _, tail = rest.partition(":")
        # post:<case_id>:<record_id> is the scoped form. Trust a known case id
        # first so this does not depend on the id being a uuid.
        if head in case_ids or _UUID_RE.match(head):
            return None
        return prefix, tail
    return prefix, rest


def _scope_cached_artifact_nodes(nx_graph):
    """Rewrite persisted Post/Listing node ids to their case-scoped form.

    Each previously-shared node is split into one copy per owning case and every
    edge is re-pointed at the copy that belongs to the case on the other end, so
    each case graph contains only its own records. Idempotent: nodes that are
    already scoped are left untouched.
    """
    if nx_graph is None:
        return False

    artifacts = {}
    case_ids = {n for n, d in nx_graph.nodes(data=True) if d.get("type") == "Case"}
    for node_id, attrs in list(nx_graph.nodes(data=True)):
        parts = _unscoped_artifact(node_id, attrs, case_ids)
        if parts:
            artifacts[node_id] = parts
    if not artifacts:
        return False

    # Which case owns each node. A Case node owns itself, personas, posts and
    # listings carry PART_OF, and identifiers inherit from the persona using them.
    owning_case = {c: c for c in case_ids}
    for u, v, data in list(nx_graph.edges(data=True)):
        if data.get("label") == "PART_OF":
            owning_case.setdefault(u, v)
    for u, v, data in list(nx_graph.edges(data=True)):
        if data.get("label") == "USES_IDENTIFIER" and u in owning_case:
            owning_case.setdefault(v, owning_case[u])

    # One scoped copy of each artifact node per case that claims it.
    copies = {}
    for node_id, (prefix, record_id) in artifacts.items():
        owners = {
            v
            for _, v, data in nx_graph.edges(node_id, data=True)
            if data.get("label") == "PART_OF"
        }
        copies[node_id] = {c: f"{prefix}{c}:{record_id}" for c in owners}

    # Materialise the copies first, carrying the original attributes across.
    # Re-pointing edges below can otherwise create a copy as a bare node.
    for node_id in artifacts:
        attrs = dict(nx_graph.nodes[node_id])
        for new_id in copies[node_id].values():
            nx_graph.add_node(new_id, **attrs)

    def _copy_of(node_id, peer_id):
        """The copy of an artifact node that belongs to the same case as its peer."""
        if node_id not in copies:
            return node_id
        return copies[node_id].get(owning_case.get(peer_id), node_id)

    for u, v, data in list(nx_graph.edges(data=True)):
        label = data.get("label")
        if label == "PART_OF":
            new_u, new_v = _copy_of(u, v), v
        elif label in ("AUTHORED", "PUBLISHED"):
            new_u, new_v = u, _copy_of(v, u)
        elif label == "MENTIONS_IDENTIFIER":
            new_u, new_v = _copy_of(u, v), v
        else:
            continue
        if new_u != u or new_v != v:
            nx_graph.add_edge(new_u, new_v, **data)
            nx_graph.remove_edge(u, v)

    for node_id in artifacts:
        if nx_graph.has_node(node_id):
            nx_graph.remove_node(node_id)

    return True


def _write_graph_atomic(data):
    """Persist the fallback graph so readers never observe a half-written file.

    Writing straight to GRAPH_FALLBACK_PATH truncates it first, so a concurrent
    reader (or a crash mid-dump) sees invalid JSON. Dumping to a sibling temp
    file and renaming is atomic on POSIX, so the path only ever holds a
    complete document.
    """
    directory = os.path.dirname(GRAPH_FALLBACK_PATH) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".graph_fallback-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, GRAPH_FALLBACK_PATH)
    except Exception:
        # Never leave a stray temp file behind on failure.
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def init_neo4j():
    global _driver, _nx_graph, _use_fallback
    os.makedirs(os.path.dirname(GRAPH_FALLBACK_PATH), exist_ok=True)
    try:
        _driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), connection_timeout=1.0
        )
        _driver.verify_connectivity()
        logger.info("Successfully connected to Neo4j.")
    except Exception as e:
        logger.warning(
            f"Failed to connect to Neo4j. Falling back to NetworkX. Error: {e}"
        )
        _use_fallback = True
        if os.path.exists(GRAPH_FALLBACK_PATH):
            try:
                with open(GRAPH_FALLBACK_PATH, "r") as f:
                    data = json.load(f)
                _nx_graph = nx.node_link_graph(data)
                if _scope_cached_artifact_nodes(_nx_graph):
                    logger.info("Scoped legacy Post/Listing node ids in fallback cache.")
                    _write_graph_atomic(nx.node_link_data(_nx_graph))
            except Exception as e:
                # Keep the unreadable file for recovery instead of silently
                # starting empty, which the next save would then overwrite.
                logger.error(f"Failed to load fallback graph: {e}")
                corrupt_path = GRAPH_FALLBACK_PATH + ".corrupt"
                try:
                    os.replace(GRAPH_FALLBACK_PATH, corrupt_path)
                    logger.error(f"Moved unreadable fallback graph to {corrupt_path}")
                except OSError:
                    logger.error("Could not preserve the unreadable fallback graph.")
                _nx_graph = nx.DiGraph()
        else:
            _nx_graph = nx.DiGraph()


def _save_fallback_graph():
    if _use_fallback and _nx_graph is not None:
        try:
            _write_graph_atomic(nx.node_link_data(_nx_graph))
        except Exception as e:
            logger.error(f"Failed to persist fallback graph: {e}")


def _ensure_init():
    if _driver is None and not _use_fallback:
        init_neo4j()


def merge_case_node(case_id, name, status):
    _ensure_init()
    if _use_fallback:
        _nx_graph.add_node(case_id, type="Case", label=name, name=name, status=status)
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (c:Case {id: $case_id}) " "SET c.name = $name, c.status = $status",
            case_id=case_id,
            name=name,
            status=status,
        )


def merge_persona_node(persona_id, handle, platform, provenance, case_id):
    _ensure_init()
    if _use_fallback:
        _nx_graph.add_node(
            persona_id,
            type="Persona",
            label=handle,
            handle=handle,
            platform=platform,
            provenance=provenance,
        )
        _nx_graph.add_edge(persona_id, case_id, label="PART_OF")
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (p:Persona {id: $persona_id}) "
            "SET p.handle = $handle, p.platform = $platform, p.provenance = $provenance "
            "MERGE (c:Case {id: $case_id}) "
            "MERGE (p)-[:PART_OF]->(c)",
            persona_id=persona_id,
            handle=handle,
            platform=platform,
            provenance=provenance,
            case_id=case_id,
        )


def merge_post_node(
    pid, tid, seq_id, timestamp_str, text_snippet, provenance, persona_id, case_id
):
    _ensure_init()
    post_id = f"post:{case_id}:{pid}"
    if _use_fallback:
        _nx_graph.add_node(
            post_id,
            type="Post",
            label=f"Post #{pid}",
            tid=tid,
            seq_id=seq_id,
            timestamp=timestamp_str,
            text_snippet=text_snippet,
            provenance=provenance,
        )
        _nx_graph.add_edge(persona_id, post_id, label="AUTHORED")
        _nx_graph.add_edge(post_id, case_id, label="PART_OF")
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (po:Post {id: $post_id}) "
            "SET po.tid = $tid, po.seq_id = $seq_id, po.timestamp = $timestamp_str, po.text_snippet = $text_snippet, po.provenance = $provenance "
            "MERGE (p:Persona {id: $persona_id}) "
            "MERGE (c:Case {id: $case_id}) "
            "MERGE (p)-[:AUTHORED]->(po) "
            "MERGE (po)-[:PART_OF]->(c)",
            post_id=post_id,
            tid=tid,
            seq_id=seq_id,
            timestamp_str=timestamp_str,
            text_snippet=text_snippet,
            provenance=provenance,
            persona_id=persona_id,
            case_id=case_id,
        )


def merge_identifier_node(
    identifier_id, id_type, value, provenance, persona_id, post_pid=None, case_id=None
):
    _ensure_init()
    if _use_fallback:
        display_val = value[:20] + "..." if len(value) > 20 else value
        _nx_graph.add_node(
            identifier_id,
            type="Identifier",
            label=f"{id_type}: {display_val}",
            identifier_type=id_type,
            value=value,
            provenance=provenance,
        )
        _nx_graph.add_edge(persona_id, identifier_id, label="USES_IDENTIFIER")
        if post_pid and case_id:
            post_id = f"post:{case_id}:{post_pid}"
            _nx_graph.add_edge(post_id, identifier_id, label="MENTIONS_IDENTIFIER")
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (i:Identifier {id: $identifier_id}) "
            "SET i.type = $id_type, i.value = $value, i.provenance = $provenance "
            "MERGE (p:Persona {id: $persona_id}) "
            "MERGE (p)-[:USES_IDENTIFIER]->(i)",
            identifier_id=identifier_id,
            id_type=id_type,
            value=value,
            provenance=provenance,
            persona_id=persona_id,
        )
        if post_pid and case_id:
            session.run(
                "MERGE (po:Post {id: $post_id}) "
                "MERGE (i:Identifier {id: $identifier_id}) "
                "MERGE (po)-[:MENTIONS_IDENTIFIER]->(i)",
                post_id=f"post:{case_id}:{post_pid}",
                identifier_id=identifier_id,
            )


def merge_listing_node(
    lid, vid, title, price, product_class, provenance, persona_id, case_id
):
    _ensure_init()
    listing_id = f"listing:{case_id}:{lid}"
    if _use_fallback:
        display_title = title[:30] + "..." if len(title) > 30 else title
        _nx_graph.add_node(
            listing_id,
            type="Listing",
            label=f"Listing #{lid}: {display_title}",
            title=title,
            price=price,
            product_class=product_class,
            provenance=provenance,
        )
        _nx_graph.add_edge(persona_id, listing_id, label="PUBLISHED")
        _nx_graph.add_edge(listing_id, case_id, label="PART_OF")
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (l:Listing {id: $listing_id}) "
            "SET l.title = $title, l.price = $price, l.product_class = $product_class, l.provenance = $provenance "
            "MERGE (p:Persona {id: $persona_id}) "
            "MERGE (c:Case {id: $case_id}) "
            "MERGE (p)-[:PUBLISHED]->(l) "
            "MERGE (l)-[:PART_OF]->(c)",
            listing_id=listing_id,
            title=title,
            price=price,
            product_class=product_class,
            provenance=provenance,
            persona_id=persona_id,
            case_id=case_id,
        )


def merge_correlation_edge(
    persona_a_id, persona_b_id, score, confidence, relationship_id, case_id
):
    _ensure_init()
    if _use_fallback:
        _nx_graph.add_edge(
            persona_a_id,
            persona_b_id,
            label="CORRELATED_WITH",
            score=score,
            confidence=confidence,
            relationship_id=relationship_id,
            case_id=case_id,
        )
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (a:Persona {id: $persona_a_id}) "
            "MERGE (b:Persona {id: $persona_b_id}) "
            "MERGE (a)-[r:CORRELATED_WITH]->(b) "
            "SET r.score = $score, r.confidence = $confidence, r.relationship_id = $relationship_id, r.case_id = $case_id",
            persona_a_id=persona_a_id,
            persona_b_id=persona_b_id,
            score=score,
            confidence=confidence,
            relationship_id=relationship_id,
            case_id=case_id,
        )


def merge_coordination_link(
    source_persona_id, target_persona_id, score, weight, latency_sec, pattern, case_id
):
    _ensure_init()
    if _use_fallback:
        _nx_graph.add_edge(
            source_persona_id,
            target_persona_id,
            label="COORDINATED_WITH",
            score=score,
            weight=weight,
            latency_sec=latency_sec,
            pattern=pattern,
            provenance="DERIVED",
            case_id=case_id,
        )
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (a:Persona {id: $source_id}) "
            "MERGE (b:Persona {id: $target_id}) "
            "MERGE (a)-[r:COORDINATED_WITH]->(b) "
            "SET r.score = $score, r.weight = $weight, r.latency_sec = $latency_sec, r.pattern = $pattern, r.provenance = 'DERIVED', r.case_id = $case_id",
            source_id=source_persona_id,
            target_id=target_persona_id,
            score=score,
            weight=weight,
            latency_sec=latency_sec,
            pattern=pattern,
            case_id=case_id,
        )


def merge_server_node(
    server_id, ip, asn, country, ssh_fingerprint, http_banner, provenance, case_id
):
    _ensure_init()
    if _use_fallback:
        _nx_graph.add_node(
            server_id,
            type="Server",
            label=f"Server: {ip}",
            ip=ip,
            asn=asn,
            country=country,
            ssh_fingerprint=ssh_fingerprint,
            http_banner=http_banner,
            provenance=provenance,
        )
        _nx_graph.add_edge(server_id, case_id, label="PART_OF")
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (s:Server {id: $server_id}) "
            "SET s.ip = $ip, s.asn = $asn, s.country = $country, s.ssh_fingerprint = $ssh_fingerprint, s.http_banner = $http_banner, s.provenance = $provenance "
            "MERGE (c:Case {id: $case_id}) "
            "MERGE (s)-[:PART_OF]->(c)",
            server_id=server_id,
            ip=ip,
            asn=asn,
            country=country,
            ssh_fingerprint=ssh_fingerprint,
            http_banner=http_banner,
            provenance=provenance,
            case_id=case_id,
        )


def merge_tls_cert_node(
    cert_id, sha256, subject_cn, issuer, jarm, provenance, server_id, case_id
):
    _ensure_init()
    if _use_fallback:
        _nx_graph.add_node(
            cert_id,
            type="Certificate",
            label=f"TLS: {subject_cn}",
            sha256=sha256,
            subject_cn=subject_cn,
            issuer=issuer,
            jarm=jarm,
            provenance=provenance,
        )
        _nx_graph.add_edge(server_id, cert_id, label="SERVES_CERTIFICATE")
        _nx_graph.add_edge(cert_id, case_id, label="PART_OF")
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (t:Certificate {id: $cert_id}) "
            "SET t.sha256 = $sha256, t.subject_cn = $subject_cn, t.issuer = $issuer, t.jarm = $jarm, t.provenance = $provenance "
            "MERGE (s:Server {id: $server_id}) "
            "MERGE (c:Case {id: $case_id}) "
            "MERGE (s)-[:SERVES_CERTIFICATE]->(t) "
            "MERGE (t)-[:PART_OF]->(c)",
            cert_id=cert_id,
            sha256=sha256,
            subject_cn=subject_cn,
            issuer=issuer,
            jarm=jarm,
            provenance=provenance,
            server_id=server_id,
            case_id=case_id,
        )


def merge_service_node(
    service_id,
    onion_url,
    service_name,
    service_type,
    provenance,
    server_id,
    cert_id,
    case_id,
):
    _ensure_init()
    if _use_fallback:
        _nx_graph.add_node(
            service_id,
            type="HiddenService",
            label=f"{service_name}",
            onion_url=onion_url,
            service_name=service_name,
            service_type=service_type,
            provenance=provenance,
        )
        _nx_graph.add_edge(service_id, server_id, label="HOSTED_ON")
        _nx_graph.add_edge(service_id, case_id, label="PART_OF")
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (hs:HiddenService {id: $service_id}) "
            "SET hs.onion_url = $onion_url, hs.name = $service_name, hs.service_type = $service_type, hs.provenance = $provenance "
            "MERGE (s:Server {id: $server_id}) "
            "MERGE (c:Case {id: $case_id}) "
            "MERGE (hs)-[:HOSTED_ON]->(s) "
            "MERGE (hs)-[:PART_OF]->(c)",
            service_id=service_id,
            onion_url=onion_url,
            service_name=service_name,
            service_type=service_type,
            provenance=provenance,
            server_id=server_id,
            case_id=case_id,
        )


def merge_infrastructure_link(
    service_a_id, service_b_id, link_type, reason, provenance, case_id
):
    _ensure_init()
    if _use_fallback:
        _nx_graph.add_edge(
            service_a_id,
            service_b_id,
            label=link_type,
            reason=reason,
            provenance=provenance,
            case_id=case_id,
        )
        _save_fallback_graph()
        return
    with _driver.session() as session:
        session.run(
            "MERGE (a:HiddenService {id: $service_a_id}) "
            "MERGE (b:HiddenService {id: $service_b_id}) "
            "MERGE (a)-[r:CO_HOSTED_SERVER]->(b) "
            "SET r.reason = $reason, r.provenance = $provenance, r.case_id = $case_id",
            service_a_id=service_a_id,
            service_b_id=service_b_id,
            reason=reason,
            provenance=provenance,
            case_id=case_id,
        )


def get_case_graph(case_id):
    _ensure_init()
    nodes = []
    edges = []

    if _use_fallback:
        # Collect all node IDs that are part of this case
        case_node_ids = set()
        case_node_ids.add(case_id)
        for u, v, data in _nx_graph.edges(data=True):
            if data.get("label") == "PART_OF" and v == case_id:
                case_node_ids.add(u)
        # Also collect nodes connected to case nodes via any relationship
        extended_ids = set(case_node_ids)
        for u, v, data in _nx_graph.edges(data=True):
            if (
                u in case_node_ids
                or v in case_node_ids
                or data.get("case_id") == case_id
            ):
                extended_ids.add(u)
                extended_ids.add(v)

        # Defence in depth: an investigation graph may only surface nodes that
        # belong to this case. Post/Listing/derived-actor ids are already scoped
        # at write time, but this also keeps legacy unscoped nodes out.
        owning_case = {}
        for node_id, node_data in _nx_graph.nodes(data=True):
            if node_data.get("type") == "Case":
                owning_case[node_id] = node_id
        for u, v, data in _nx_graph.edges(data=True):
            if data.get("label") == "PART_OF":
                owning_case.setdefault(u, v)
        for u, v, data in _nx_graph.edges(data=True):
            if data.get("label") == "USES_IDENTIFIER" and u in owning_case:
                owning_case.setdefault(v, owning_case[u])
        for node_id in list(extended_ids):
            if node_id in owning_case:
                if owning_case[node_id] != case_id:
                    extended_ids.discard(node_id)
            elif _nx_graph.nodes[node_id].get("type") in ("Case", "Persona"):
                # An unattributed actor has no place in a case-scoped graph.
                extended_ids.discard(node_id)

        for node_id, data in _nx_graph.nodes(data=True):
            if node_id in extended_ids:
                node_data = dict(data)
                if not node_data.get("type"):
                    node_data["type"] = "Case" if node_id == case_id else "Persona"
                if not node_data.get("label"):
                    node_data["label"] = (
                        node_data.get("canonical_handle")
                        or node_data.get("name")
                        or str(node_id)[:8]
                    )
                nodes.append({"data": {"id": node_id, **node_data}})
        for u, v, data in _nx_graph.edges(data=True):
            if u in extended_ids and v in extended_ids:
                label = data.get("label", "")
                # Skip zero-score or null correlation edges to prevent visual clutter
                if label == "CORRELATED_WITH" and float(data.get("score", 0)) <= 0.0:
                    continue
                edges.append(
                    {
                        "data": {
                            "id": f"{u}-{v}-{label}",
                            "source": u,
                            "target": v,
                            **data,
                        }
                    }
                )
    else:
        with _driver.session() as session:
            # Get all nodes connected to the case
            result = session.run(
                "MATCH (c:Case {id: $case_id})<-[:PART_OF*0..3]-(n) RETURN DISTINCT n",
                case_id=case_id,
            )
            for record in result:
                node = record["n"]
                props = dict(node)
                nodes.append(
                    {"data": {"id": props.get("id", str(node.element_id)), **props}}
                )

            # Get all edges between those nodes
            result = session.run(
                "MATCH (c:Case {id: $case_id})<-[:PART_OF*0..3]-(n) "
                "WITH collect(n) AS case_nodes "
                "UNWIND case_nodes AS a "
                "MATCH (a)-[r]->(b) WHERE b IN case_nodes "
                "RETURN id(r) as rid, type(r) as rtype, a, b",
                case_id=case_id,
            )
            for record in result:
                a_props = dict(record["a"])
                b_props = dict(record["b"])
                edges.append(
                    {
                        "data": {
                            "id": str(record["rid"]),
                            "source": a_props.get("id", ""),
                            "target": b_props.get("id", ""),
                            "label": record["rtype"],
                        }
                    }
                )
    return {"nodes": nodes, "edges": edges}


def delete_case_from_graph(case_id: str):
    """Removes a case and all its connected nodes/edges from the graph engine."""
    global _nx_graph
    _ensure_init()
    if _use_fallback:
        if _nx_graph is None:
            return
        # Collect all node IDs connected to this case
        nodes_to_remove = set()
        nodes_to_remove.add(case_id)
        for u, v, data in list(_nx_graph.edges(data=True)):
            if data.get("label") == "PART_OF" and v == case_id:
                nodes_to_remove.add(u)
        # Also remove nodes that only connect to these nodes
        extended = set(nodes_to_remove)
        for u, v, data in list(_nx_graph.edges(data=True)):
            if u in nodes_to_remove or v in nodes_to_remove or data.get("case_id") == case_id:
                extended.add(u)
                extended.add(v)
        for node_id in extended:
            if _nx_graph.has_node(node_id):
                _nx_graph.remove_node(node_id)
        _save_fallback_graph()
    else:
        with _driver.session() as session:
            session.run(
                "MATCH (c:Case {id: $case_id})<-[:PART_OF*0..3]-(n) DETACH DELETE n, c",
                case_id=case_id,
            )

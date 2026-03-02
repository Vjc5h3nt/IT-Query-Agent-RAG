#!/usr/bin/env python3
"""
Offline retrieval evaluation harness.

Measures Recall@K, MRR, and average latency for the hybrid retrieval
pipeline against a sample of resolved JIRA tickets.

Usage:
    cd backend
    source venv/bin/activate
    python eval_retrieval.py --xml /path/to/export.xml --sample 200 --top-k 5

Algorithm:
    For each sampled resolved ticket:
      1. Build query = summary + " " + description (first 500 chars)
      2. Run full hybrid pipeline (Dense + BM25 → RRF → CrossEncoder)
         OR dense-only if BM25 is unavailable
      3. Check if correct ticket_id appears in top-K results
      4. Compute Recall@K, Recall@10, MRR

Output:
    - Printed table to stdout
    - eval_results.json for per-ticket analysis
"""
import argparse
import json
import logging
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.WARNING,  # suppress noisy INFO logs during eval
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Evaluate hybrid retrieval pipeline on JIRA XML export.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--xml",     required=True, help="Path to JIRA XML export file.")
    p.add_argument("--sample",  type=int, default=200,  help="Number of resolved tickets to evaluate.")
    p.add_argument("--top-k",   type=int, default=5,    help="Recall@K to measure.")
    p.add_argument("--output",  default="eval_results.json", help="Output file for per-ticket results.")
    p.add_argument("--no-rerank", action="store_true",  help="Skip cross-encoder reranking (faster).")
    p.add_argument("--dense-only", action="store_true", help="Disable BM25; use dense retrieval only.")
    return p.parse_args()


# ── Query builder ─────────────────────────────────────────────────────────────

def build_query(ticket: Dict[str, Any], max_chars: int = 500) -> str:
    """Build a realistic query from a ticket's summary and description."""
    parts = [
        ticket.get("summary", ""),
        ticket.get("description", "")[:max_chars],
    ]
    return " ".join(p for p in parts if p).strip()


# ── Retrieval runner ──────────────────────────────────────────────────────────

def run_retrieval(
    query: str,
    top_k: int,
    use_reranking: bool = True,
    dense_only: bool = False,
) -> Tuple[List[str], float]:
    """
    Run the full retrieval pipeline and return (ranked_ticket_ids, latency_ms).
    """
    from services.vector_store import vector_store
    from services.bm25_store import bm25_store
    from services.hybrid_retriever import HybridRetriever, rrf_fusion
    from services.retriever import CrossEncoderRetriever, VectorRetriever

    t0 = time.perf_counter()

    filter_dict = None
    try:
        from services.jira.query_metadata_extractor import extract_query_metadata
        filter_dict = extract_query_metadata(query) or None
    except Exception:
        pass

    use_hybrid = (not dense_only) and bm25_store.is_ready()

    if use_hybrid and use_reranking:
        hybrid = HybridRetriever(vector_store, bm25_store)
        fused = hybrid.retrieve(query, top_k=top_k * 3, filter_dict=filter_dict)
        reranker = CrossEncoderRetriever(vector_store)
        results = reranker.retrieve(
            query, top_k=top_k, filter_dict=filter_dict,
            precomputed_candidates=fused,
        )
    elif use_hybrid:
        hybrid = HybridRetriever(vector_store, bm25_store)
        results = hybrid.retrieve(query, top_k=top_k, filter_dict=filter_dict)
    elif use_reranking:
        reranker = CrossEncoderRetriever(vector_store)
        results = reranker.retrieve(query, top_k=top_k, filter_dict=filter_dict)
    else:
        retriever = VectorRetriever(vector_store)
        results = retriever.retrieve(query, top_k=top_k, filter_dict=filter_dict)

    latency_ms = (time.perf_counter() - t0) * 1000

    # Extract ticket IDs from results
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])
    if docs and isinstance(docs[0], list):
        docs = docs[0]
        metas = metas[0] if metas else []

    ticket_ids = []
    for meta in metas:
        tid = meta.get("ticket_id", "")
        if tid and tid not in ticket_ids:
            ticket_ids.append(tid)

    return ticket_ids, latency_ms


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(results: List[Dict[str, Any]], top_k: int) -> Dict[str, float]:
    """Compute Recall@K, Recall@10, and MRR."""
    total = len(results)
    if total == 0:
        return {}

    recall_k = sum(1 for r in results if r["found_at_k"] is not None and r["found_at_k"] <= top_k)
    recall_10 = sum(1 for r in results if r["found_at_k"] is not None and r["found_at_k"] <= 10)
    mrr = sum(1.0 / r["found_at_k"] for r in results if r["found_at_k"] is not None)
    avg_latency = sum(r["latency_ms"] for r in results) / total

    return {
        f"Recall@{top_k}":  round(recall_k  / total, 4),
        "Recall@10":        round(recall_10  / total, 4),
        "MRR":              round(mrr        / total, 4),
        "avg_latency_ms":   round(avg_latency, 1),
        "total_queries":    total,
        "found":            recall_k,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    print(f"\n{'='*60}")
    print("  JIRA Hybrid Retrieval Evaluation Harness")
    print(f"{'='*60}")
    print(f"  XML:        {args.xml}")
    print(f"  Sample:     {args.sample}")
    print(f"  Top-K:      {args.top_k}")
    print(f"  Reranking:  {'no' if args.no_rerank else 'yes (L-12)'}")
    print(f"  Mode:       {'dense-only' if args.dense_only else 'hybrid (Dense + BM25)'}")
    print(f"{'='*60}\n")

    # ── Load resolved tickets from XML ──────────────────────────────
    print("Loading tickets from XML...", end=" ", flush=True)
    from services.jira.jira_xml_ingestor import parse as parse_xml

    resolved = []
    for ticket in parse_xml(args.xml):
        if ticket.get("resolution_details") or ticket.get("resolution") not in ("", "Unresolved", None):
            resolved.append(ticket)
        if len(resolved) >= args.sample:
            break

    if not resolved:
        print(f"\n❌ No resolved tickets found in {args.xml}")
        sys.exit(1)

    sample = resolved[: args.sample]
    print(f"loaded {len(sample)} resolved tickets.")

    # ── Check BM25 availability ──────────────────────────────────────
    from services.bm25_store import bm25_store
    if not args.dense_only and bm25_store.is_ready():
        print(f"BM25 (OpenSearch): ready — {bm25_store.count():,} indexed tickets")
    else:
        if not args.dense_only:
            print("BM25 (OpenSearch): NOT ready — running dense-only fallback")
        else:
            print("Dense-only mode forced by --dense-only flag")

    # ── Run evaluation ───────────────────────────────────────────────
    print(f"\nEvaluating {len(sample)} queries...\n")
    results = []
    use_reranking = not args.no_rerank

    for i, ticket in enumerate(sample, 1):
        tid = ticket.get("ticket_id", "")
        query = build_query(ticket)

        if not query.strip() or not tid:
            continue

        try:
            ranked_ids, latency_ms = run_retrieval(
                query,
                top_k=max(args.top_k, 10),  # always fetch at least 10 for Recall@10
                use_reranking=use_reranking,
                dense_only=args.dense_only,
            )
        except Exception as e:
            logger.warning(f"Query {i} failed ({tid}): {e}")
            continue

        found_at = None
        for pos, r_tid in enumerate(ranked_ids, 1):
            if r_tid == tid:
                found_at = pos
                break

        results.append({
            "ticket_id":   tid,
            "query":       query[:120],
            "found_at_k":  found_at,
            "latency_ms":  round(latency_ms, 1),
            "ranked_ids":  ranked_ids[:10],
        })

        # Progress bar every 10 tickets
        if i % 10 == 0 or i == len(sample):
            found = sum(1 for r in results if r["found_at_k"] is not None and r["found_at_k"] <= args.top_k)
            pct = found / len(results) * 100 if results else 0
            bar_done = int(i / len(sample) * 30)
            bar = "█" * bar_done + "░" * (30 - bar_done)
            print(f"  [{bar}] {i:>3}/{len(sample)}  Recall@{args.top_k}={pct:.1f}%", end="\r")

    print()  # new line after progress bar

    # ── Compute and print metrics ────────────────────────────────────
    metrics = compute_metrics(results, args.top_k)

    print(f"\n{'='*60}")
    print("  RESULTS")
    print(f"{'='*60}")
    print(f"  Queries evaluated: {metrics['total_queries']}")
    print(f"  Found in top-{args.top_k}:  {metrics['found']} ({metrics[f'Recall@{args.top_k}']:.1%})")
    print(f"  Recall@{args.top_k}:        {metrics[f'Recall@{args.top_k}']:.4f}")
    print(f"  Recall@10:        {metrics['Recall@10']:.4f}")
    print(f"  MRR:              {metrics['MRR']:.4f}")
    print(f"  Avg latency:      {metrics['avg_latency_ms']:.1f} ms")
    print(f"{'='*60}\n")

    # ── Save per-ticket results ──────────────────────────────────────
    output = {
        "config": {
            "xml":        args.xml,
            "sample":     len(sample),
            "top_k":      args.top_k,
            "reranking":  not args.no_rerank,
            "dense_only": args.dense_only,
        },
        "metrics":  metrics,
        "per_ticket": results,
    }
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Per-ticket results saved to: {args.output}\n")


if __name__ == "__main__":
    main()

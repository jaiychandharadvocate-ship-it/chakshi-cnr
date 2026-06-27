"""
Chakshi — live extraction demo (end-to-end)
===========================================

Turn a raw judgment into structured intelligence and a Chakshi Digest, using a
real LLM. This is the smallest end-to-end slice of the refinery: one document
in, ``CaseIntelligence`` + ``ChakshiDigest`` + graph edges out.

Usage
-----
    # Set the key the project already uses (see backend/app.py):
    export OPENAI_API_KEY_MY=sk-...
    # optional: export CHAKSHI_EXTRACTION_MODEL=gpt-4o

    python -m intelligence.run_extraction path/to/judgment.txt \
        --title "Aruna v. State" --court "High Court of Madras" \
        --jurisdiction "Tamil Nadu" --out result.json

If no key is configured the script explains how to set one and exits cleanly
(non-zero) without a traceback.
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from .extraction import ExtractionPipeline
from .llm import build_default_llm_client
from .schemas import CourtLevel, RawDocument, Visibility


def _build_doc(args, text: str) -> RawDocument:
    court_level = CourtLevel(args.court_level) if args.court_level else None
    return RawDocument(
        document_id=args.id,
        doc_type="judgment",
        title=args.title,
        court=args.court,
        court_level=court_level,
        jurisdiction=args.jurisdiction,
        language=args.language,
        text=text,
        visibility=Visibility(args.visibility),
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Chakshi live extraction demo")
    p.add_argument("path", help="Path to a judgment text file (UTF-8).")
    p.add_argument("--id", default="DOC-0001")
    p.add_argument("--title", default=None)
    p.add_argument("--court", default=None)
    p.add_argument("--court-level", dest="court_level", default=None,
                   choices=[c.value for c in CourtLevel])
    p.add_argument("--jurisdiction", default=None)
    p.add_argument("--language", default="en")
    p.add_argument("--visibility", default="public",
                   choices=[v.value for v in Visibility])
    p.add_argument("--no-digest", action="store_true", help="Skip the Chakshi Digest.")
    p.add_argument("--out", default=None, help="Write JSON result here (else stdout).")
    args = p.parse_args(argv)

    llm = build_default_llm_client()
    if llm is None:
        print(
            "No LLM configured. Set OPENAI_API_KEY_MY (or OPENAI_API_KEY) to run "
            "live extraction. Optionally set CHAKSHI_EXTRACTION_MODEL.",
            file=sys.stderr,
        )
        return 2

    try:
        with open(args.path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"Could not read {args.path}: {exc}", file=sys.stderr)
        return 1
    if not text.strip():
        print(f"{args.path} is empty.", file=sys.stderr)
        return 1

    pipeline = ExtractionPipeline(llm=llm)
    doc = _build_doc(args, text)

    print(f"[chakshi] extracting CaseIntelligence from {args.path} ...", file=sys.stderr)
    case = pipeline.extract_case(doc)
    case.extracted_at = datetime.now(timezone.utc)

    result = {"case": case.model_dump(mode="json")}
    result["graph_edges"] = [e.model_dump(mode="json")
                             for e in pipeline.to_graph_edges(case)]

    if not args.no_digest:
        print("[chakshi] building Chakshi Digest ...", file=sys.stderr)
        digest = pipeline.build_digest(case)
        result["digest"] = digest.model_dump(mode="json")

    out = json.dumps(result, indent=2, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"[chakshi] wrote {args.out}", file=sys.stderr)
    else:
        print(out)

    if case.needs_human_review:
        print("[chakshi] NOTE: extraction flagged needs_human_review=True",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

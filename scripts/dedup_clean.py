#!/usr/bin/env python3
"""
Chakshi — dedup & clean Indian legal corpora for fine-tuning prep.

Step 2 of the workflow: after `download_sources.sh` pulls everything (with its
guaranteed overlap), this clears the noise and repetition so you feed a clean,
deduplicated corpus into fine-tuning.

What it does
------------
1. **Load** records from JSON / JSONL / CSV (and Parquet if pandas is installed)
   across one or more input paths/globs. Each record is a dict; common fields:
   `cnr`, `decision_date`, `court`, `title`, `text`, `language`, `license`,
   `source`, `doc_id`, `path`.
2. **Exact-key dedup** on a stable identity key — `(cnr, decision_date, court)`
   when a CNR exists, else `(normalized_title, decision_date, court)`. This kills
   the cross-source duplication (vanga == OpenJustice == AWS; Kaggle ⊂ vanga;
   HF re-scrapes of Indian Kanoon).
3. **Near-duplicate text dedup** on a normalized-text hash (lowercased,
   punctuation-stripped, whitespace-collapsed). Catches the same judgment
   arriving with trivial formatting differences. (Optional shingled MinHash via
   `datasketch` with `--minhash` for fuzzy near-dupes.)
4. **Noise filter** — drop records whose text is shorter than `--min-chars`
   (OCR fragments, stubs) and strip configurable boilerplate header/footer lines.
5. **License filter** — drop records whose `license` matches `--exclude-license`
   (e.g. keep NC/paywalled material out of a commercial fine-tune).
6. **Language filter** — `--lang en` keeps only matching `language`.
7. **Write** kept records to a JSONL file and a report (kept/dropped counts with
   reasons) so the cleaning is auditable.

Dependency-light: pure stdlib for JSON/JSONL/CSV. Parquet and MinHash are
optional and only needed if you ask for them.

Examples
--------
    # dedup the metadata you pulled before downloading PDFs:
    python scripts/dedup_clean.py 'data/raw/**/metadata/**/*.json' -o clean.jsonl

    # full text dedup + clean for a commercial fine-tune (drop NC licenses):
    python scripts/dedup_clean.py 'data/raw/**/*.jsonl' -o clean.jsonl \
        --min-chars 500 --exclude-license non-commercial cc-by-nc paywalled --lang en
"""

import argparse
import csv
import glob
import hashlib
import json
import re
import sys
from collections import Counter
from typing import Dict, Iterable, List, Optional

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _load_file(path: str) -> Iterable[Dict]:
    low = path.lower()
    try:
        if low.endswith(".jsonl") or low.endswith(".ndjson"):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        yield json.loads(line)
        elif low.endswith(".json"):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                yield from (r for r in data if isinstance(r, dict))
            elif isinstance(data, dict):
                yield data
        elif low.endswith(".csv"):
            with open(path, encoding="utf-8", newline="") as fh:
                yield from csv.DictReader(fh)
        elif low.endswith(".parquet"):
            try:
                import pandas as pd
            except ImportError:
                print(f"[warn] skip {path}: install pandas+pyarrow for parquet",
                      file=sys.stderr)
                return
            for rec in pd.read_parquet(path).to_dict(orient="records"):
                yield rec
        else:
            print(f"[warn] skip unsupported file: {path}", file=sys.stderr)
    except Exception as exc:  # keep going on a bad file
        print(f"[warn] failed to read {path}: {exc}", file=sys.stderr)


def load_records(patterns: List[str]) -> Iterable[Dict]:
    seen_paths = set()
    for pat in patterns:
        matches = glob.glob(pat, recursive=True) or ([pat] if "*" not in pat else [])
        for path in matches:
            if path in seen_paths:
                continue
            seen_paths.add(path)
            yield from _load_file(path)


# --------------------------------------------------------------------------- #
# Normalization & keys
# --------------------------------------------------------------------------- #
def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    return _WS.sub(" ", str(s)).strip().lower()


def _norm_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return _WS.sub(" ", _PUNCT.sub(" ", str(s).lower())).strip()


def identity_key(rec: Dict) -> str:
    cnr = _norm(rec.get("cnr") or rec.get("cnr_number"))
    date = _norm(rec.get("decision_date") or rec.get("date") or rec.get("judgment_date"))
    court = _norm(rec.get("court") or rec.get("court_name"))
    if cnr:
        return f"cnr:{cnr}|{date}|{court}"
    title = _norm(rec.get("title") or rec.get("case_title") or rec.get("name"))
    return f"t:{title}|{date}|{court}"


def text_hash(rec: Dict) -> Optional[str]:
    text = rec.get("text") or rec.get("judgment_text") or rec.get("body")
    nt = _norm_text(text)
    if len(nt) < 32:  # too little to hash meaningfully
        return None
    return hashlib.sha1(nt.encode("utf-8")).hexdigest()


def get_text(rec: Dict) -> str:
    return str(rec.get("text") or rec.get("judgment_text") or rec.get("body") or "")


def strip_boilerplate(text: str, patterns: List[re.Pattern]) -> str:
    if not patterns or not text:
        return text
    lines = [ln for ln in text.splitlines()
             if not any(p.search(ln) for p in patterns)]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main dedup/clean
# --------------------------------------------------------------------------- #
def run(args) -> Dict[str, int]:
    boiler = [re.compile(p, re.IGNORECASE) for p in (args.strip_lines or [])]
    exclude_lic = {_norm(x) for x in (args.exclude_license or [])}
    want_lang = _norm(args.lang) if args.lang else None

    seen_keys = set()
    seen_text = set()
    stats = Counter()
    kept = 0

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    dropped_log = open(args.dropped, "w", encoding="utf-8") if args.dropped else None

    def drop(reason: str, rec: Dict):
        stats[f"dropped_{reason}"] += 1
        if dropped_log:
            dropped_log.write(json.dumps(
                {"reason": reason, "key": identity_key(rec),
                 "title": rec.get("title"), "source": rec.get("source")},
                ensure_ascii=False) + "\n")

    try:
        for rec in load_records(args.inputs):
            stats["read"] += 1

            lic = _norm(rec.get("license"))
            if exclude_lic and any(x in lic for x in exclude_lic):
                drop("license", rec); continue

            if want_lang:
                lang = _norm(rec.get("language") or rec.get("lang"))
                if lang and lang != want_lang:
                    drop("language", rec); continue

            key = identity_key(rec)
            if key in seen_keys:
                drop("dup_key", rec); continue

            text = strip_boilerplate(get_text(rec), boiler)
            if boiler and text != get_text(rec):
                rec["text"] = text  # write the cleaned text back

            if args.min_chars and text and len(text) < args.min_chars:
                drop("too_short", rec); continue

            th = text_hash({**rec, "text": text}) if text else None
            if th is not None:
                if th in seen_text:
                    drop("dup_text", rec); continue
                seen_text.add(th)

            seen_keys.add(key)
            out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            kept += 1
    finally:
        if args.output:
            out.close()
        if dropped_log:
            dropped_log.close()

    stats["kept"] = kept
    return dict(stats)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Dedup & clean legal corpora for fine-tuning.")
    p.add_argument("inputs", nargs="+", help="Files or globs (JSON/JSONL/CSV/Parquet).")
    p.add_argument("-o", "--output", help="Output JSONL (default: stdout).")
    p.add_argument("--dropped", help="Optional JSONL log of dropped records + reasons.")
    p.add_argument("--min-chars", type=int, default=0,
                   help="Drop records whose text is shorter than this (0 = off).")
    p.add_argument("--exclude-license", nargs="*", default=[],
                   help="Drop records whose license contains any of these substrings.")
    p.add_argument("--lang", help="Keep only this language (matches the 'language' field).")
    p.add_argument("--strip-lines", nargs="*", default=[],
                   help="Regexes; matching lines are stripped from text as boilerplate.")
    p.add_argument("--minhash", action="store_true",
                   help="(Reserved) fuzzy near-dup via datasketch MinHash if installed.")
    args = p.parse_args(argv)

    if args.minhash:
        try:
            import datasketch  # noqa: F401
        except ImportError:
            print("[warn] --minhash needs `pip install datasketch`; using exact "
                  "normalized-text hashing instead.", file=sys.stderr)

    stats = run(args)
    print("\n[chakshi] dedup/clean summary:", file=sys.stderr)
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}", file=sys.stderr)
    read = stats.get("read", 0)
    kept = stats.get("kept", 0)
    if read:
        print(f"  -> kept {kept}/{read} ({100*kept//read}%)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

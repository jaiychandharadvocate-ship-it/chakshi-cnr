# Corpus download & cleaning (fine-tuning prep)

Three steps: **download all → clear noise/repetition → feed for fine-tuning.**

```
1.  bash scripts/download_sources.sh metadata    # small: HC+SC parquet metadata
2.  python scripts/dedup_clean.py 'data/raw/**/metadata/**/*.parquet' -o clean.jsonl
3.  # decide what's worth the heavy PDF pull, then:
    bash scripts/download_sources.sh sc          # ~52 GB
    bash scripts/download_sources.sh hc          # ~1.25 TiB (only if you need it)
```

## Why dedup matters here (the repetition is real)

The open Indian-law sources overlap heavily — the same judgments arrive through
multiple doors:

- **vanga HC/SC == OpenJustice == AWS Open Data registry** — identical data.
- **Kaggle SC (adarshsingh0903) ⊂ vanga SC** — a subset.
- **Most HuggingFace "indian law" datasets are re-scrapes of Indian Kanoon.**

Download once (AWS as the base), then dedup across everything.

## `download_sources.sh`

`bash scripts/download_sources.sh {metadata|hc|sc|hf|kaggle|all}`
Set `CHAKSHI_DATA_DIR` to change the destination (default `./data/raw`).
Needs `awscli` (no credentials — uses `--no-sign-request`), and optionally
`huggingface_hub[cli]` / `kaggle` for those sources.

## `dedup_clean.py`

Reads JSON / JSONL / CSV (and Parquet if `pandas`+`pyarrow` installed) and removes:

1. **exact-key dupes** — `(cnr, decision_date, court)`, else `(title, date, court)`
2. **near-duplicate text** — normalized-text SHA hash (lowercase, de-punct, de-space)
3. **noise** — `--min-chars` drops OCR stubs; `--strip-lines` removes boilerplate
4. **license** — `--exclude-license non-commercial cc-by-nc paywalled` (keep NC/paywalled out of a commercial fine-tune)
5. **language** — `--lang en`

Writes kept records to JSONL and an optional `--dropped` audit log (reason per record).

```bash
python scripts/dedup_clean.py 'data/raw/**/*.jsonl' -o clean.jsonl \
    --min-chars 500 --exclude-license non-commercial cc-by-nc --lang en \
    --dropped dropped.jsonl
```

Tip: run it on the **parquet metadata first** so you dedup before moving terabytes.

See [`../docs/INDIAN_LEGAL_DATA_SOURCES.md`](../docs/INDIAN_LEGAL_DATA_SOURCES.md)
for the full source catalog with licenses.

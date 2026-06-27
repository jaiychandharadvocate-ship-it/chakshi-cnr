#!/usr/bin/env bash
#
# Chakshi — bulk download of open Indian legal corpora for fine-tuning prep.
#
# Workflow this supports:
#   1. download all   (this script)
#   2. clear noise / repetition   (scripts/dedup_clean.py)
#   3. feed for fine-tuning
#
# IMPORTANT — overlap (download ONCE, not three times):
#   * vanga HC/SC  ==  OpenJustice  ==  AWS Open Data registry  -> SAME data.
#   * Kaggle SC (adarshsingh0903)  is a SUBSET of vanga SC.
#   * Most HuggingFace "indian law" datasets are re-scrapes of Indian Kanoon.
#   So: take the AWS sets as the base, then run dedup_clean.py across everything.
#
# Tip: pull the *metadata/parquet* first and dedup BEFORE downloading the heavy
# PDFs — you can decide what's worth fetching from a few GB of metadata instead
# of moving 1.25 TiB blind.
#
# Requirements (install what you use):
#   awscli           : pip install awscli            (S3, no credentials needed)
#   huggingface_hub  : pip install -U "huggingface_hub[cli]"
#   kaggle           : pip install kaggle  + ~/.kaggle/kaggle.json
#
# Usage:
#   bash scripts/download_sources.sh metadata   # just the parquet/json metadata (small)
#   bash scripts/download_sources.sh hc         # High Court full set (~1.25 TiB!)
#   bash scripts/download_sources.sh sc         # Supreme Court full set (~52 GB)
#   bash scripts/download_sources.sh hf         # convenient HuggingFace text sets
#   bash scripts/download_sources.sh kaggle     # Kaggle SC (subset of sc)
#   bash scripts/download_sources.sh all        # everything below
#
set -euo pipefail

DEST="${CHAKSHI_DATA_DIR:-./data/raw}"
mkdir -p "$DEST"
echo "[chakshi] download destination: $DEST"

# AWS Open Data buckets (public, --no-sign-request = no account/credentials).
HC_BUCKET="s3://indian-high-court-judgments"
SC_BUCKET="s3://indian-supreme-court-judgments"

dl_metadata() {
  echo "[chakshi] HC + SC metadata (parquet) — dedup on this BEFORE pulling PDFs"
  aws s3 sync --no-sign-request "$HC_BUCKET/metadata/parquet/" "$DEST/hc/metadata/parquet/"
  aws s3 sync --no-sign-request "$SC_BUCKET/metadata/parquet/" "$DEST/sc/metadata/parquet/"
  echo "[chakshi] (browse a bucket with: aws s3 ls --no-sign-request $HC_BUCKET/ )"
}

dl_hc() {
  echo "[chakshi] High Court judgments — LARGE (~1.25 TiB). Ctrl-C to abort."
  aws s3 sync --no-sign-request "$HC_BUCKET/" "$DEST/hc/"
}

dl_sc() {
  echo "[chakshi] Supreme Court judgments (~52 GB)."
  aws s3 sync --no-sign-request "$SC_BUCKET/" "$DEST/sc/"
}

dl_hf() {
  echo "[chakshi] HuggingFace judgment/text datasets (convenient, smaller)."
  # --repo-type dataset; these overlap with the AWS sets -> dedup afterwards.
  for ds in \
    "opennyaiorg/InJudgements_dataset" \
    "vihaannnn/Indian-Supreme-Court-Judgements-Chunked" \
    "harshitv804/Indian_Penal_Code" \
    "viber1/indian-law-dataset"; do
    safe="${ds//\//__}"
    echo "  - $ds"
    huggingface-cli download --repo-type dataset "$ds" --local-dir "$DEST/hf/$safe" || \
      echo "    (skip: $ds — check name/availability/license)"
  done
  echo "[chakshi] Indic-language pretraining (optional, multilingual):"
  echo "          huggingface-cli download --repo-type dataset ai4bharat/sangraha --local-dir $DEST/hf/sangraha"
}

dl_kaggle() {
  echo "[chakshi] Kaggle SC 1950-2024 (subset of the AWS SC set; verify license)."
  kaggle datasets download -p "$DEST/kaggle" --unzip \
    adarshsingh0903/legal-dataset-sc-judgments-india-19502024 || \
    echo "  (needs ~/.kaggle/kaggle.json)"
}

case "${1:-help}" in
  metadata) dl_metadata ;;
  hc)       dl_hc ;;
  sc)       dl_sc ;;
  hf)       dl_hf ;;
  kaggle)   dl_kaggle ;;
  all)      dl_metadata; dl_sc; dl_hf; dl_kaggle; dl_hc ;;
  *) sed -n '1,40p' "$0"; exit 0 ;;
esac

echo "[chakshi] done. Next: python scripts/dedup_clean.py --help"

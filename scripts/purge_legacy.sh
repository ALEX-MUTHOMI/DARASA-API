#!/usr/bin/env bash
set -eo pipefail

LEGACY_PATHS=(
  "finance"
  "billing"
  "checkout"
  "payments"
  "payment"
  "invoices"
  "invoice"
  "ledger"
  "receipts"
  "receipt"
  "M-Pesa"
  "Mpesa"
  "Daraja"
  "reconciliation"
  "webhooks"
)

echo "Purging forbidden legacy finance-related app directories"

for path in "${LEGACY_PATHS[@]}"; do
  if [ -e "${path}" ]; then
    rm -rf "${path}"
    echo "Removed ${path}"
  else
    echo "Skipped ${path}"
  fi
done

echo "Legacy purge complete"

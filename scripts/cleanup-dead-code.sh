#!/usr/bin/env bash
#
# cleanup-dead-code.sh
# ────────────────────
# Removes legacy/orphaned files that are no longer wired into the app after the
# connect-TranzAct-first onboarding refactor. Run from the repo root.
#
# These files were the old "direct from the browser → /api/tranzact/* → TranzAct"
# explorer path. Data now flows through the FastAPI connections + pipelines
# layer instead, so this cluster is dead:
#
#   • apps/web/app/dashboard/explorer.tsx          (never imported; not a route)
#   • apps/web/app/api/tranzact/login/route.ts     (used only by explorer)
#   • apps/web/app/api/tranzact/report/route.ts    (used only by explorer)
#   • apps/web/lib/tranzact/auth.ts                (used only by the two routes above)
#   • apps/web/components/dashboard/NoConnectionBanner.tsx
#                                                  (replaced by OnboardingGate)
#
# Also clears tracked Python bytecode that should never have been committed.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "Removing orphaned frontend files…"
git rm -f --ignore-unmatch \
  apps/web/app/dashboard/explorer.tsx \
  apps/web/app/api/tranzact/login/route.ts \
  apps/web/app/api/tranzact/report/route.ts \
  apps/web/lib/tranzact/auth.ts \
  apps/web/components/dashboard/NoConnectionBanner.tsx

# Drop the now-empty api/tranzact directory if nothing else lives there.
rmdir apps/web/app/api/tranzact 2>/dev/null || true
rmdir apps/web/lib/tranzact 2>/dev/null || true

echo "Untracking committed Python bytecode…"
git rm -r --cached --ignore-unmatch '**/__pycache__' >/dev/null 2>&1 || true
find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

echo "Done. Review with 'git status' then commit."

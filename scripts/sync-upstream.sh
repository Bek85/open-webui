#!/usr/bin/env bash
# Syncs main with upstream/main (fast-forward only), then rebases custom/main on top.
# Usage: ./scripts/sync-upstream.sh [--push]
#
# --push   After a clean rebase, push both branches to origin automatically.
#          Omit to resolve conflicts manually before pushing.

set -euo pipefail

UPSTREAM_REMOTE="upstream"
ORIGIN_REMOTE="origin"
MAIN_BRANCH="main"
CUSTOM_BRANCH="custom/main"
PUSH=false

for arg in "$@"; do
  [[ "$arg" == "--push" ]] && PUSH=true
done

# ── helpers ───────────────────────────────────────────────────────────────────
red()   { printf "\033[0;31m%s\033[0m\n" "$*"; }
green() { printf "\033[0;32m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[0;33m%s\033[0m\n" "$*"; }
info()  { printf "  %s\n" "$*"; }

# ── pre-flight ────────────────────────────────────────────────────────────────
if [[ -n "$(git status --porcelain | grep -v '^\?\?')" ]]; then
  red "Working tree is dirty. Stash or commit your changes first."
  exit 1
fi

CURRENT_BRANCH=$(git symbolic-ref --short HEAD)

# ── step 1: fetch upstream ────────────────────────────────────────────────────
yellow "1/4  Fetching $UPSTREAM_REMOTE..."
git fetch "$UPSTREAM_REMOTE"

UPSTREAM_HEAD=$(git rev-parse "$UPSTREAM_REMOTE/$MAIN_BRANCH")
MAIN_HEAD=$(git rev-parse "$MAIN_BRANCH")
BEHIND=$(git rev-list --count "$MAIN_BRANCH".."$UPSTREAM_REMOTE/$MAIN_BRANCH")

if [[ "$MAIN_HEAD" == "$UPSTREAM_HEAD" ]]; then
  green "     main is already up to date with upstream — nothing to sync."
  exit 0
fi

info "$BEHIND new upstream commit(s) to absorb."

# ── step 2: fast-forward main ─────────────────────────────────────────────────
yellow "2/4  Fast-forwarding $MAIN_BRANCH to $UPSTREAM_REMOTE/$MAIN_BRANCH..."
git checkout "$MAIN_BRANCH"
git merge --ff-only "$UPSTREAM_REMOTE/$MAIN_BRANCH"
green "     $MAIN_BRANCH is now at $(git rev-parse --short HEAD)."

# ── step 3: rebase custom/main ────────────────────────────────────────────────
yellow "3/4  Rebasing $CUSTOM_BRANCH onto $MAIN_BRANCH..."
git checkout "$CUSTOM_BRANCH"

# Create a dated backup before rebasing
BACKUP="backup/$CUSTOM_BRANCH-pre-sync-$(date +%Y%m%d-%H%M)"
git branch "$BACKUP"
info "Backup created: $BACKUP"

if git rebase "$MAIN_BRANCH"; then
  green "     Rebase completed cleanly."
  REBASE_OK=true
else
  red "     Rebase stopped — conflicts need manual resolution."
  info "Resolve conflicts, then run:"
  info "  git add <files> && git rebase --continue"
  info "Once done, push manually:"
  info "  git push $ORIGIN_REMOTE $MAIN_BRANCH"
  info "  git push $ORIGIN_REMOTE $CUSTOM_BRANCH --force-with-lease"
  REBASE_OK=false
fi

# ── step 4: push ─────────────────────────────────────────────────────────────
if $REBASE_OK && $PUSH; then
  yellow "4/4  Pushing to $ORIGIN_REMOTE..."
  git checkout "$MAIN_BRANCH"
  git push "$ORIGIN_REMOTE" "$MAIN_BRANCH"
  git checkout "$CUSTOM_BRANCH"
  git push "$ORIGIN_REMOTE" "$CUSTOM_BRANCH" --force-with-lease
  green "     Both branches pushed."
elif $REBASE_OK; then
  yellow "4/4  Skipping push (run with --push to push automatically, or push manually):"
  info "  git checkout $MAIN_BRANCH && git push $ORIGIN_REMOTE $MAIN_BRANCH"
  info "  git checkout $CUSTOM_BRANCH && git push $ORIGIN_REMOTE $CUSTOM_BRANCH --force-with-lease"
fi

# ── restore original branch ───────────────────────────────────────────────────
git checkout "$CURRENT_BRANCH" 2>/dev/null || true

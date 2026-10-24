#!/bin/sh
# Proven red (P2): run each changed unit-test file against the code from
# BEFORE the range (worktree at the fork point) and fail when a test passes
# there. A test that has never failed does not demonstrate it can catch a
# bug. The output names whether each red was an assertion or a missing
# symbol.
#
#   scripts/proven-red.sh <base> [head]
#
# Exit 0: every changed test was red on the old code. Exit 1: a changed
# test passed on the old code, or source changed with no test change.
# Exit 2: the gate could not run.
set -u
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$DIR/.."
base=${1:?usage: proven-red.sh <base> [head]}
head=${2:-HEAD}

fork=$(git merge-base "$base" "$head") || { echo "proven-red: no merge-base" >&2; exit 2; }

changed=$(git diff --name-only "$fork".."$head")
[ -n "$changed" ] || { echo "proven-red: empty range; nothing to prove"; exit 0; }

is_source() {
    case "$1" in
        tests/*|scripts/*|AGENTS*|issues/*|docs/*|*.md|Makefile|.gitignore|\
        .ratchet-*|pyproject.toml|README.md|discovery.md) return 1;;
        *) return 0;;
    esac
}

source_changed=0
for f in $changed; do is_source "$f" && source_changed=1; done

tests_changed=$(printf '%s\n' $changed | grep -E '^tests/test_.*\.py$' | grep -v '^$' || true)
if [ -z "$tests_changed" ]; then
    if [ "$source_changed" -eq 0 ]; then
        echo "proven-red: skip - only gates/docs/instruction files changed"
        exit 0
    fi
    echo "proven-red: FAIL - source changed but no unit test did:" >&2
    printf '%s\n' $changed | while read -r f; do is_source "$f" && echo "  $f" >&2; done
    exit 1
fi

WT=$(mktemp -d /tmp/proven-red.XXXXXX)
trap 'git worktree remove --force "$WT" >/dev/null 2>&1; rm -rf "$WT"' EXIT
git worktree add --detach "$WT" "$fork" >/dev/null 2>&1 || {
    echo "proven-red: could not create worktree at $fork" >&2; exit 2; }

fail=0
for t in $tests_changed; do
    [ -f "$t" ] || continue
    mkdir -p "$WT/$(dirname "$t")"
    cp "$t" "$WT/$t"
    out=$(cd "$WT" && env -u LD_LIBRARY_PATH python3 -m pytest -q "$t" 2>&1)
    if [ $? -eq 0 ]; then
        # An announced skip excuses a pass: the file carries a marker line
        # `# proven-red: allow-pass: <reason>` at HEAD. Gate-relaxation
        # edits cannot be red by nature; the red for the change must be
        # carried by another test in the same range.
        reason=$(grep -m1 'proven-red: allow-pass:' "$t" | sed 's/.*allow-pass: *//')
        if [ -n "$reason" ]; then
            echo "proven-red: ok $t allow-pass(announced: $reason)"
        else
            echo "proven-red: FAIL $t passed on the pre-change code" >&2
            fail=1
        fi
    else
        if echo "$out" | grep -qE '(AssertionError|assert )'; then
            echo "proven-red: ok $t red(assertion)"
        else
            echo "proven-red: ok $t red(missing-symbol/import)"
        fi
    fi
done

[ "$fail" -eq 0 ] && echo "proven-red: ok - every changed test is red on the pre-change code"
exit "$fail"

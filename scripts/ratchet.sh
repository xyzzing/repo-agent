#!/bin/sh
# Ratchet (C2/C7): measured counts must hold or shrink vs .ratchet-baseline.
# Prints what it measured (M2): the numbers describe the whole tree, and a
# count the script cannot compute is an error, not a pass.
set -eu
cd "$(dirname "$0")/.."
BASE=.ratchet-baseline
[ -f "$BASE" ] || { echo "ratchet: missing $BASE" >&2; exit 2; }

fail=0
measured() {
    # measured <name> <count> — compares against the baseline entry
    name=$1 count=$2
    want=$(awk -v n="$name" '$1 == n { print $2 }' "$BASE")
    if [ -z "$want" ]; then
        echo "ratchet: no baseline entry for '$name'" >&2; fail=1; return
    fi
    echo "ratchet: $name = $count (baseline $want)"
    if [ "$count" -gt "$want" ]; then
        echo "ratchet: FAIL $name grew: $count > $want" >&2; fail=1
    fi
}

over=$(find repo_agent scripts tests -name '*.py' -type f 2>/dev/null | xargs wc -l 2>/dev/null | awk '$1 > 400 && $2 != "total" { n++ } END { print n + 0 }')
measured files_over_400 "$over"

bare=$(grep -rE '^\s*except(\s*:|\s+Exception\s*:)\s*$' repo_agent --include='*.py' -A1 2>/dev/null | grep -cE '^\S+.*-\s+pass\s*$' || true)
measured bare_except_pass "$bare"

deps=$(env -u LD_LIBRARY_PATH python3 - <<'EOF'
import tomllib
with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
print(len(data["project"]["dependencies"]))
EOF
)
measured runtime_deps "$deps"

mocks=$(grep -rE 'unittest\.mock|from mock import|import mock$' repo_agent tests --include='*.py' 2>/dev/null | wc -l)
measured mocked_internal_modules "$mocks"

shells=$(grep -rE 'shell\s*=\s*True' repo_agent --include='*.py' 2>/dev/null | wc -l)
measured shell_true "$shells"

[ "$fail" -eq 0 ] && echo "ratchet: ok"
exit "$fail"

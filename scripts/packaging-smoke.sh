#!/bin/sh
# RA-011 packaging smoke (PRD §16: "Fresh wheel installed outside
# repository | Required runtime resources exist and commands function").
#
# Builds a wheel from the checkout, installs it into a fresh venv, and
# exercises the installed CLI from a scratch directory OUTSIDE the
# source tree: drift check against an unrendered fixture must exit 1,
# the written render must then check clean, task validation and doctor
# must answer with reason-coded JSON. Exit 0 only if every step held.
set -eu
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SRC=$(cd "$DIR/.." && pwd)
WORK=$(mktemp -d /tmp/repo-agent-smoke.XXXXXX)
trap 'rm -rf "$WORK"' EXIT

echo "smoke: building wheel from $SRC"
python3 -m pip wheel --no-deps --wheel-dir "$WORK/dist" "$SRC" >/dev/null
WHEEL=$(ls "$WORK"/dist/*.whl)
echo "smoke: wheel $(basename "$WHEEL")"

python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet "$WHEEL"

cd "$WORK"
INSTALLED="$WORK/venv/bin/repo-agent"
[ -x "$INSTALLED" ] || { echo "smoke: FAIL - console script missing"; exit 1; }

echo "smoke: --version"
"$INSTALLED" --version >/dev/null

echo "smoke: fixture repo + packet"
cp -r "$SRC/tests/fixtures/smoke-repo" "$WORK/target"
PACKET="$SRC/tests/fixtures/smoke-packet.yaml"
"$INSTALLED" task validate "$PACKET" >/dev/null

echo "smoke: render --check on an unrendered fixture must exit 1 (drift)"
set +e
"$INSTALLED" render "$WORK/target" --check >/dev/null 2>&1
drift=$?
set -e
[ "$drift" -eq 1 ] || {
    echo "smoke: FAIL - drift check exited $drift, expected 1"; exit 1;
}

echo "smoke: render --write then --check must exit 0"
"$INSTALLED" render "$WORK/target" --write >/dev/null
"$INSTALLED" render "$WORK/target" --check >/dev/null

echo "smoke: inspect"
"$INSTALLED" inspect "$WORK/target" >/dev/null

echo "smoke: doctor (no --live) must answer with its JSON report"
set +e
"$INSTALLED" doctor "$WORK/target" >"$WORK/doctor.json" 2>/dev/null
doctor_rc=$?
set -e
case "$doctor_rc" in
    0|1|3) ;;  # ok / checks-failed / blocked are all honest answers
    *) echo "smoke: FAIL - doctor exited $doctor_rc"; exit 1 ;;
esac
python3 - "$WORK/doctor.json" <<'PYEOF'
import json, sys
report = json.load(open(sys.argv[1]))
assert report.get("command") == "doctor", report
assert isinstance(report.get("checks"), list) and report["checks"], report
PYEOF

echo "smoke: ok - fresh wheel install functions outside the checkout"

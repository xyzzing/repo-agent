PY := env -u LD_LIBRARY_PATH python3

.PHONY: gates test lint ratchet

gates: test lint ratchet

test:
	$(PY) -m pytest -q

lint:
	ruff check .

ratchet:
	sh scripts/ratchet.sh

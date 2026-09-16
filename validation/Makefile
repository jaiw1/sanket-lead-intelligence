# Validation pack — pre-registered acceptance criteria.
#
# This Makefile lives inside validation/ so the lane owns exactly one directory.
# Every target runs from the repository root, whichever directory you invoke it
# from:
#
#     make -C validation validate          # from the repo root
#     make -f validation/Makefile validate # equivalent
#
# When a repo-root Makefile appears, add:  include validation/Makefile

# Relative, not $(abspath ...): make's path functions split on whitespace and
# this repo lives under a directory whose name contains a space.
REPO_ROOT := $(dir $(lastword $(MAKEFILE_LIST)))..
PY        ?= python3
CRITERIA  ?= validation/criteria.yaml
OUT       ?= validation/report/

.PHONY: validate validate-strict criteria-test list deps clean-report help

## validate: run every implemented runner, grade against criteria.yaml, write the report
validate:
	cd "$(REPO_ROOT)" && $(PY) -m validation.run --criteria $(CRITERIA) --out $(OUT)

## validate-strict: the G7 gate form — pending and warn count as failures too
validate-strict:
	cd "$(REPO_ROOT)" && $(PY) -m validation.run --criteria $(CRITERIA) --out $(OUT) --strict

## criteria-test: check the pre-registration contract itself (schema, ids, thresholds)
criteria-test:
	cd "$(REPO_ROOT)" && $(PY) -m pytest validation/tests -q

## list: print the registered criteria without running anything
list:
	cd "$(REPO_ROOT)" && $(PY) -m validation.run --criteria $(CRITERIA) --list

## deps: the only third-party packages this pack needs by itself
deps:
	$(PY) -m pip install "pydantic>=2,<3" PyYAML pytest

## clean-report: delete generated output (report/ is gitignored, never committed by hand)
clean-report:
	rm -rf "$(REPO_ROOT)/$(OUT)"

help:
	@grep -E '^## ' $(lastword $(MAKEFILE_LIST)) | sed 's/^## /  /'

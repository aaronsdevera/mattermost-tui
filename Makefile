# Release helpers (run from repo root; requires git, uv).
#
# Typical flow:
#   1. make release-branch RELEASE=0.2.0    # from clean main: fetch, branch release/v0.2.0
#   2. Bump version in pyproject.toml (and cli version_option if needed), commit, merge to main.
#   3. git checkout main && git pull
#   4. make release-publish RELEASE=0.2.0 # test, annotated tag v0.2.0, push tag (triggers CI binaries)

ORIGIN ?= origin
MAIN ?= main

.PHONY: test
test:
	uv sync --group dev
	uv run pytest

.PHONY: release-check
release-check:
	@if [ -z "$(RELEASE)" ]; then \
		echo 'Set RELEASE=major.minor.patch (example: make release-branch RELEASE=0.2.0)'; \
		exit 1; \
	fi

.PHONY: release-branch
release-branch: release-check
	git fetch $(ORIGIN) $(MAIN)
	git checkout $(MAIN)
	git pull $(ORIGIN) $(MAIN)
	git checkout -b release/v$(RELEASE)

.PHONY: release-tag
release-tag: release-check test
	git tag -a "v$(RELEASE)" -m "Release v$(RELEASE)"

.PHONY: push-tag
push-tag: release-check
	git push $(ORIGIN) "v$(RELEASE)"

# Single recipe so `make -j` cannot push before the tag exists.
.PHONY: release-publish
release-publish: release-check test
	git tag -a "v$(RELEASE)" -m "Release v$(RELEASE)"
	git push $(ORIGIN) "v$(RELEASE)"

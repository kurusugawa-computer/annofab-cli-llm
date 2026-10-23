GITLEAKS_VERSION := v8.30.1
GITLEAKS_DOCKER_CONFIG ?=

ifndef SOURCE_FILES
	export SOURCE_FILES:=acl
endif
ifndef TEST_FILES
	export TEST_FILES:=tests
endif
.PHONY: docs lint test format publish_test publish

format:
	uv run ruff format ${SOURCE_FILES} ${TEST_FILES}
	uv run ruff check ${SOURCE_FILES} ${TEST_FILES} --fix-only --exit-zero --unsafe-fixes

lint:
	uv run ruff format ${SOURCE_FILES} ${TEST_FILES} --check
	uv run ruff check ${SOURCE_FILES} ${TEST_FILES}
	uv run mypy ${SOURCE_FILES} ${TEST_FILES}

test:
	uv run pytest --cov=${SOURCE_FILES} --cov-report=html ${TEST_FILES}

docs:
	cd docs && uv run make html

.PHONY: gitleaks

gitleaks:
	@if command -v gitleaks >/dev/null 2>&1; then \
		gitleaks git --redact=100 --verbose --log-opts="-m HEAD" .; \
	elif command -v docker >/dev/null 2>&1; then \
		if [ -n "${GITLEAKS_DOCKER_CONFIG}" ]; then \
			mkdir -p "${GITLEAKS_DOCKER_CONFIG}"; \
			export DOCKER_CONFIG="${GITLEAKS_DOCKER_CONFIG}"; \
		fi; \
		docker run --rm \
			-v "$$(pwd):$$(pwd):ro" \
			-v "$$(git rev-parse --path-format=absolute --git-common-dir):$$(git rev-parse --path-format=absolute --git-common-dir):ro" \
			-w "$$(pwd)" ghcr.io/gitleaks/gitleaks:${GITLEAKS_VERSION} git --redact=100 --verbose --log-opts="-m HEAD" .; \
	else \
		echo "gitleaksまたはdockerをインストールしてください。" >&2; \
		exit 127; \
	fi

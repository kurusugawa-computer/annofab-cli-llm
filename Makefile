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

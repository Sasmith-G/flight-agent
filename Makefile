.PHONY: install test lint demo docker

install:
	pip install -e ".[dev]"

test:
	pytest -v

lint:
	ruff check src tests

demo:
	disruption-agent demo

docker:
	docker build -t disruption-agent . && docker run --rm disruption-agent

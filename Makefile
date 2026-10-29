# Common tasks. Python commands use the active virtualenv; see README for setup.
.PHONY: help install test web-install web-dev web-test web-build lint benchmark export-web check

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-13s %s\n", $$1, $$2}'

install:  ## Install Python dependencies
	pip install -r requirements.txt

test:  ## Run the Python test suite
	python -m pytest

web-install:  ## Install frontend dependencies
	cd web && npm ci

web-dev:  ## Start the app at http://localhost:5173
	cd web && npm run dev

web-test:  ## Run the frontend tests (parity with the Python reference)
	cd web && npm test

web-build:  ## Production build into web/dist
	cd web && npm run build

lint:  ## Lint the frontend
	cd web && npm run lint

benchmark:  ## Score the shipped move-judging model on the fixed benchmark
	python -m ep_model.benchmark.run score --model shipped=ep_model/models_board

export-web:  ## Export models and parity fixtures for the browser app
	python -m ep_model.scripts.export_web

check: test lint web-test web-build  ## Everything CI runs

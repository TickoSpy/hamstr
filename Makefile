PYTHON     := python3
VENV       := backend/.venv
PIP        := $(VENV)/bin/pip
PYTEST     := $(VENV)/bin/pytest
RUFF       := $(VENV)/bin/ruff
UVICORN    := $(VENV)/bin/uvicorn

.PHONY: setup dev-backend dev-frontend dev lint test build clean

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -q -r backend/requirements-dev.txt
	npm install --prefix frontend

dev-backend:
	STORAGE_ROOT=storage DATABASE_URL="sqlite+aiosqlite:///storage/hamstr.db" \
	$(UVICORN) app.main:app --reload --reload-dir backend/app --app-dir backend --host 0.0.0.0 --port 8000

dev-frontend:
	npm run dev --prefix frontend

dev:
	@echo "Starting backend and frontend in parallel…"
	@$(MAKE) -j2 dev-backend dev-frontend

lint:
	$(RUFF) check backend/app
	$(RUFF) format --check backend/app
	npm run lint --prefix frontend 2>/dev/null || true

test:
	cd backend && $(abspath $(PYTEST)) app/tests -v

build:
	npm run build --prefix frontend

docker-up:
	docker compose up --build

docker-down:
	docker compose down

clean:
	rm -rf backend/.venv frontend/node_modules frontend/dist

.PHONY: check backend frontend dev setup start

setup:          ## install backend and frontend dependencies and git hooks
	cd backend && uv sync
	cd frontend && npm install
	cd backend && uv run pre-commit install --config ../.pre-commit-config.yaml

check:          ## run every lint, type and test gate
	./scripts/check.sh

backend:        ## run the API on http://127.0.0.1:8000 with reload
	cd backend && uv run tradedisha

frontend:       ## run the Vite dev server on http://localhost:5173
	cd frontend && npm run dev

dev:            ## run both (backend in background; Ctrl-C stops the frontend)
	$(MAKE) backend & $(MAKE) frontend

start:          ## build the web app and serve everything from http://127.0.0.1:8000
	cd frontend && npm run build
	cd backend && TRADEDISHA_SERVE_FRONTEND=true TRADEDISHA_RELOAD=false uv run tradedisha

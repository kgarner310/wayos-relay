.PHONY: install server poller run test seed clean

# Install dependencies (editable)
install:
	pip install -e ".[dev]"

# Run FastAPI web server only
server:
	uvicorn app.main:app --reload --port 8000

# Run IMAP email poller only
poller:
	python poller.py

# Run both server and poller together (Ctrl+C stops both)
run:
	@echo "Starting ServiceInbox server + IMAP poller..."
	@echo "Press Ctrl+C to stop both."
	@uvicorn app.main:app --reload --port 8000 & \
		UVICORN_PID=$$!; \
		python poller.py & \
		POLLER_PID=$$!; \
		trap "kill $$UVICORN_PID $$POLLER_PID 2>/dev/null; exit" INT TERM; \
		wait

# Run tests
test:
	pytest tests/ -v

# Load seed data via API
seed:
	curl -s -X POST http://localhost:8000/api/seed | python -m json.tool

# Remove database
clean:
	rm -f serviceinbox.db

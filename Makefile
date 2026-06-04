.PHONY: install check-ports free-ports up registry orchestrator rag-agent mcp-agent down

install:
	pip install -r requirements.txt

check-ports:
	@bash scripts/check-ports.sh

free-ports:
	@bash scripts/free-ports.sh

# One-command boot: launches all 4 services in the background.
# Each service writes to logs/<name>.log. Use `make down` to stop them.
up: check-ports
	@mkdir -p logs
	@echo "Starting registry on :8000..."
	@nohup uvicorn registry.main:app --host 0.0.0.0 --port 8000 > logs/registry.log 2>&1 & echo $$! > logs/registry.pid
	@sleep 1
	@echo "Starting orchestrator on :8001..."
	@nohup uvicorn orchestrator.main:app --host 0.0.0.0 --port 8001 > logs/orchestrator.log 2>&1 & echo $$! > logs/orchestrator.pid
	@echo "Starting rag-agent on :8002..."
	@nohup uvicorn agents.rag_agent.main:app --host 0.0.0.0 --port 8002 > logs/rag-agent.log 2>&1 & echo $$! > logs/rag-agent.pid
	@echo "Starting mcp-agent on :8003..."
	@nohup uvicorn agents.mcp_agent.main:app --host 0.0.0.0 --port 8003 > logs/mcp-agent.log 2>&1 & echo $$! > logs/mcp-agent.pid
	@echo "All services starting. Tail with: tail -f logs/*.log"

registry:
	uvicorn registry.main:app --host 0.0.0.0 --port 8000 --reload

down:
	@for f in logs/*.pid; do \
	  if [ -f "$$f" ]; then \
	    pid=$$(cat $$f); \
	    kill $$pid 2>/dev/null && echo "stopped $$f ($$pid)"; \
	    rm -f $$f; \
	  fi; \
	done

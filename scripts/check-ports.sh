#!/usr/bin/env bash
# Fail fast if any of the A2A ports are already taken.
set -u
PORTS=(8000 8001 8002 8003)
LABELS=("registry" "orchestrator" "rag-agent" "mcp-agent")
status=0
for i in "${!PORTS[@]}"; do
  port="${PORTS[$i]}"
  label="${LABELS[$i]}"
  pid=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)
  if [[ -n "$pid" ]]; then
    pname=$(ps -p "$pid" -o comm= 2>/dev/null | tr -d ' ')
    echo "❌ port $port ($label) — IN USE by PID $pid ($pname)"
    status=1
  else
    echo "✅ port $port ($label) — FREE"
  fi
done
exit $status

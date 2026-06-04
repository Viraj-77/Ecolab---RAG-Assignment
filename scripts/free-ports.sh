#!/usr/bin/env bash
# Show what is on the A2A ports and offer to kill those processes.
set -u
PORTS=(8000 8001 8002 8003)
PIDS=()
for port in "${PORTS[@]}"; do
  pid=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)
  if [[ -n "$pid" ]]; then
    pname=$(ps -p "$pid" -o comm= 2>/dev/null | tr -d ' ')
    echo "port $port → PID $pid ($pname)"
    PIDS+=("$pid")
  fi
done
if [[ ${#PIDS[@]} -eq 0 ]]; then
  echo "All A2A ports are free."
  exit 0
fi
read -r -p "Kill these processes? [y/N] " ans
if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
  echo "Aborted."
  exit 1
fi
for pid in "${PIDS[@]}"; do
  kill "$pid" 2>/dev/null && echo "kill $pid sent"
done
sleep 1
for pid in "${PIDS[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then
    echo "PID $pid still alive — sending SIGKILL"
    kill -9 "$pid" 2>/dev/null
  fi
done
echo "Done."

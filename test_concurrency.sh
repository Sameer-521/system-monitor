#!/bin/bash
# test_concurrency.sh - Concurrent streaming for two clients with different filters
# Saves output to JSON Lines files, auto-stops after 15 seconds

set -euo pipefail

BASE_URL="http://127.0.0.1:8000"
ENABLE_DELAY=false
DELAY_SECONDS=2

echo "=== Issuing tickets ==="

TICKET_SAMEER=$(curl -s -X POST "$BASE_URL/stream/ticket/Sameer" | jq -r '.ticket.id')
TICKET_JOHN=$(curl -s -X POST "$BASE_URL/stream/ticket/John" | jq -r '.ticket.id')

if [[ -z "$TICKET_SAMEER" || -z "$TICKET_JOHN" ]]; then
  echo "ERROR: Failed to get tickets"
  exit 1
fi

echo "Sameer's ticket: $TICKET_SAMEER"
echo "John's ticket:   $TICKET_JOHN"
echo "=== Streaming for 15 seconds... ==="

# Sameer: cpu, memory, disk
curl -s -N -H "Accept: text/event-stream" \
  "$BASE_URL/stream/all/Sameer?ticket=$TICKET_SAMEER&cpu=true&memory=true&disk=true" |
  sed -n 's/^data: //p' >sameer_stream.jsonl &
PID_SAMEER=$!

if [[ "$ENABLE_DELAY" == "true" ]]; then
  echo "Delaying $DELAY_SECONDS seconds before next worker..."
  sleep "$DELAY_SECONDS"
fi

# John: network, processes, containers
curl -s -N -H "Accept: text/event-stream" \
  "$BASE_URL/stream/all/John?ticket=$TICKET_JOHN&network=true&processes=true&containers=true" |
  sed -n 's/^data: //p' >john_stream.jsonl &
PID_JOHN=$!

sleep 15

kill $PID_SAMEER $PID_JOHN 2>/dev/null || true
wait $PID_SAMEER $PID_JOHN 2>/dev/null || true

echo ""
echo "=== Done ==="
echo "Sameer stream events: $(wc -l <sameer_stream.jsonl)"
echo "John stream events:   $(wc -l <john_stream.jsonl)"
echo "Output saved to: sameer_stream.jsonl, john_stream.jsonl"

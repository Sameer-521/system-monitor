#!/usr/bin/env fish
# Orchestrates one capture experiment:
#   start server -> SSE capture (cpu + alerts only) -> burn all cores mid-capture
#   -> wait for capture -> stop server -> print results
#
# Usage: fish scripts/run_experiment.fish [--duration 300] [--spike-delay 30] [--spike-seconds 120] [--warmup 330]

argparse 'd/duration=' 's/spike-delay=' 'p/spike-seconds=' 'w/warmup=' 'h/help' -- $argv
or exit 1

if set -q _flag_help
    echo "usage: fish scripts/run_experiment.fish [-d 300] [-s 30] [-p 120] [-w 330]"
    exit 0
end

set -l duration $_flag_duration
set -l delay $_flag_spike_delay
set -l spike $_flag_spike_seconds
set -l warmup $_flag_warmup
test -n "$duration"; or set duration 300
test -n "$delay"; or set delay 30
test -n "$spike"; or set spike 120
test -n "$warmup"; or set warmup 330

cd (path resolve (status dirname)/..)

set -l script_dir (status dirname)
set -l server_log $script_dir/server.log
set -l capture_log $script_dir/capture.log

function cleanup --on-event fish_exit
    pkill -f "uvicorn app[.]main" 2>/dev/null
    pkill -f "capture_plot[.]py" 2>/dev/null
    pkill -f "cpu_spike[.]py" 2>/dev/null
end

echo "== starting server =="
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 > $server_log 2>&1 &
set -l server_pid $last_pid

set -l up 0
for i in (seq 1 20)
    if curl -s -m 2 http://127.0.0.1:8000/ > /dev/null 2>&1
        set up 1
        break
    end
    sleep 1
end
if test $up -eq 0
    echo "ERROR: server failed to start (see $server_log)"
    exit 1
end
echo "server up (pid $server_pid)"

set -l total (math $warmup + $duration)
echo "== starting capture now ($total s total: $warmup s warm-up + $duration s experiment) =="
uv run python scripts/capture_plot.py --duration $total > $capture_log 2>&1 &
set -l capture_pid $last_pid

echo "== warming up $warmup s (let alert baseline arm) =="
sleep $warmup

echo "== sleeping $delay s before spike =="
sleep $delay

echo "== burning all cores for $spike s =="
uv run python scripts/cpu_spike.py $spike

echo "== waiting for capture to finish =="
wait $capture_pid

kill $server_pid 2>/dev/null

echo "== capture log =="
cat $capture_log
echo "== done. jsonl: scripts/capture.jsonl, plot: scripts/capture_plot.png =="

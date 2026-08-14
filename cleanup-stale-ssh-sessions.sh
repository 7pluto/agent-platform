#!/usr/bin/env bash
set -euo pipefail

current_session_pid="${PPID}"
removed=0

while read -r pid ppid etimes; do
  [[ -n "$pid" ]] || continue
  [[ "$etimes" -gt 60 ]] || continue
  [[ "$pid" != "$current_session_pid" ]] || continue

  if pgrep -P "$pid" >/dev/null 2>&1; then
    continue
  fi

  sudo kill "$pid"
  removed=$((removed + 1))
done < <(ps -eo pid=,ppid=,etimes=,args= | awk '$0 ~ /sshd: ubuntu@notty$/ {print $1, $2, $3}')

echo "removed_stale_sessions=${removed}"
ps -eo args= | grep -c '^sshd: ubuntu@notty$' | awk '{print "remaining_notty_sessions=" $1}'

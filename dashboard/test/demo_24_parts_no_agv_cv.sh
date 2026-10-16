#!/usr/bin/env bash
# CV integration copy. Original demo_24_parts_no_agv.sh remains untouched.
set -e
exec "$(cd -- "$(dirname -- "$0")/../.." && pwd)/thesis_cv/cvctl" run no-agv "$@"

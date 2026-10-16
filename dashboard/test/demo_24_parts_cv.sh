#!/usr/bin/env bash
# CV integration copy. Original demo_24_parts.sh remains untouched.
set -e
exec "$(cd -- "$(dirname -- "$0")/../.." && pwd)/thesis_cv/cvctl" run agv "$@"

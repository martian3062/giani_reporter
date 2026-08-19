#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
core="${script_dir}/assemble_video.py"

python_command=""
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  python_command="python3"
elif command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  python_command="python"
fi
if [[ -z "${python_command}" ]]; then
  echo "ERROR: A working Python 3.10+ interpreter was not found on PATH. Install Python and retry." >&2
  exit 2
fi
if [[ ! -f "${core}" ]]; then
  echo "ERROR: Assembly core is missing: ${core}" >&2
  exit 2
fi

exec "${python_command}" "${core}" "$@"

#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Use an installed Python 3.12+ interpreter.
python_cmd=""
for candidate in python3.12 python3.13 python3.14 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && \
       "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 12))' >/dev/null 2>&1; then
        python_cmd="$candidate"
        break
    fi
done

if [[ -z "$python_cmd" ]]; then
    echo "Python 3.12+ required. Install it and re-run." >&2
    exit 1
fi

if [[ ! -d .venv ]]; then
    "$python_cmd" -m venv .venv
fi

venv_python=".venv/bin/python"
if [[ ! -x "$venv_python" ]]; then
    echo "The existing .venv is not a macOS/Linux virtual environment. Remove it and re-run." >&2
    exit 1
fi
if ! "$venv_python" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
    echo "The existing .venv needs Python 3.12+. Remove it and re-run." >&2
    exit 1
fi

"$venv_python" -m pip install --upgrade pip
"$venv_python" -m pip install -r requirements.txt

echo "Done. Activate with: source .venv/bin/activate"

#!/bin/bash
# Cloud sessions only: install graphify so `graphify query/path/explain/update` work (CLAUDE.md "graphify").
# On the owner's PC graphify is already installed; this exits straight away there.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

GRAPHIFY_VERSION="0.9.61"  # same as the owner's PC (graphify-out/cache/ast/v0.9.61-*): a different version rewrites the whole cache

if command -v graphify >/dev/null 2>&1; then
  exit 0
fi

if command -v uv >/dev/null 2>&1; then
  uv tool install --quiet "graphifyy==${GRAPHIFY_VERSION}"
else
  python3 -m pip install --quiet --user "graphifyy==${GRAPHIFY_VERSION}"
fi

# uv/pip --user put the command in ~/.local/bin; make sure the session can find it.
echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "${CLAUDE_ENV_FILE:-/dev/null}"

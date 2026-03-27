"""
run_proxy.py — Forion LiteLLM Proxy launcher

Calls litellm.run_server() via Python directly (not via litellm.exe)
so that sys.path is controlled here and the LOCAL litellm source
(containing litellm.proxy.forion.*) is used, not the pip-installed copy.

Usage:
    python run_proxy.py --config forion_config.yaml --port 4000
"""
import sys
import os

# Insert THIS directory at the front of sys.path so Python resolves
# `import litellm` to the LOCAL source (with ForionCustomLogger),
# not the pip-installed copy in site-packages.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Verify we're using the correct litellm
import litellm as _lt
_src = getattr(_lt, '__file__', '')
if _HERE not in _src:
    print(f"[WARN] litellm resolved to pip copy: {_src}")
    print(f"[WARN] Expected local source at: {_HERE}/litellm/")
else:
    print(f"[OK]  litellm resolved to local source: {_src}")

# Run the proxy using the official entry point
from litellm import run_server
run_server()

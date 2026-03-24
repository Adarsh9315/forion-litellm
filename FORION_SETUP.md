# FORION — LiteLLM Proxy Setup Guide

Complete guide to setting up and running the FORION integration layer on top of the LiteLLM proxy.

---

## Prerequisites

| Requirement | Minimum Version | Check Command |
|---|---|---|
| Python | 3.10+ | `python3 --version` |
| Poetry | 1.7+ | `poetry --version` |
| Git | any | `git --version` |
| pip | 21+ | `pip --version` |

### API Keys (at least one required)

- **OpenAI** — [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **Anthropic** — [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)

Optional providers: Azure OpenAI, Groq, Together AI, Mistral.

---

## 1. Clone the Repository

```bash
git clone https://github.com/BerriAI/litellm.git
cd litellm
```

---

## 2. Install Dependencies

### Using Poetry (recommended)

```bash
# Install all project dependencies
poetry install

# Install psycopg-binary (required for pytest — not included in lock file)
poetry run pip install psycopg-binary
```

### Using pip + virtualenv (alternative)

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate          # Windows

# Install LiteLLM with proxy extras
pip install "litellm[proxy]"

# Install psycopg-binary for tests
pip install psycopg-binary
```

---

## 3. Configure Environment Variables

Copy the example env file and fill in your API keys:

```bash
cp .env.forion.example .env
```

Edit `.env` with your keys:

```dotenv
# Required — at least one provider key
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx

# Proxy authentication (optional but recommended)
LITELLM_MASTER_KEY=sk-your-proxy-master-key

# Optional providers
# AZURE_API_KEY=
# AZURE_API_BASE=https://YOUR_RESOURCE.openai.azure.com/
# AZURE_API_VERSION=2024-02-15-preview
# GROQ_API_KEY=
# TOGETHER_API_KEY=
# MISTRAL_API_KEY=

# Debug logging (optional)
# LITELLM_LOG_LEVEL=DEBUG
```

Load the variables into your shell:

```bash
set -a && source .env && set +a
```

---

## 4. FORION Configuration (config.yaml)

The proxy config lives at `forion_config.yaml` in the project root. It defines:

- **model_list** — which LLM models the proxy can route to
- **forion** — product-aware routing rules
- **litellm_settings** — registers the FORION callback
- **router_settings** — load balancing strategy

### Config file: `forion_config.yaml`

```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-4o-mini
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY

  - model_name: claude-3-5-sonnet
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
      api_key: os.environ/ANTHROPIC_API_KEY

forion:
  enabled: true
  default_product: "ide"
  model_mapping:
    ide:
      default: "gpt-4o-mini"
      fallback: ["gpt-4o"]
    spark:
      default: "gpt-4o"
      fallback: ["claude-3-5-sonnet"]
    orbit:
      default: "gpt-4o-mini"
      fallback: ["gpt-4o-mini"]

litellm_settings:
  callbacks: ["litellm.proxy.forion.hooks.ForionCustomLogger"]

router_settings:
  routing_strategy: simple-shuffle

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

### FORION Products

| Product | Purpose | Default Model | Fallback |
|---|---|---|---|
| `ide` | Interactive coding (fast responses) | gpt-4o-mini | gpt-4o |
| `spark` | Agent execution (balanced) | gpt-4o | claude-3-5-sonnet |
| `orbit` | Long-running workflows (cost-efficient) | gpt-4o-mini | gpt-4o-mini |

---

## 5. Start the Proxy Server

### With Poetry

```bash
poetry run litellm --config forion_config.yaml --port 4000
```

### With pip/venv

```bash
litellm --config forion_config.yaml --port 4000
```

### With verbose logging

```bash
poetry run litellm --config forion_config.yaml --port 4000 --detailed_debug
```

### What to expect on startup

- Proxy takes ~15–20 seconds to fully initialize (runs Prisma migrations)
- Wait until you see `Uvicorn running on http://0.0.0.0:4000`
- Verify health: `curl http://localhost:4000/health`

---

## 6. Test the Setup

### Health check

```bash
curl http://localhost:4000/health
```

Expected: `{"status":"healthy"}`

### Basic chat completion

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Chat completion with FORION product routing

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello from Spark"}],
    "metadata": {
      "product": "spark",
      "user_id": "user-123",
      "workspace_id": "ws-456"
    }
  }'
```

### List available models

```bash
curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

### Expected response structure

A successful response includes:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "gpt-4o",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you?"
      }
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 8,
    "total_tokens": 18
  }
}
```

---

## 7. Run Tests

### Run all FORION unit tests

```bash
poetry run pytest tests/test_litellm/test_forion/test_forion.py -x -vv
```

### Run with parallel workers

```bash
poetry run pytest tests/test_litellm/test_forion/test_forion.py -x -vv -n 4
```

### Run all LiteLLM unit tests

```bash
poetry run pytest tests/test_litellm/ -x -vv -n 4
```

### Run linter

```bash
cd litellm && poetry run ruff check .
```

### Expected test output

```
32 passed in 0.14s
```

---

## 8. FORION Architecture Overview

```
litellm/proxy/forion/
├── __init__.py     — Package exports
├── config.py       — ForionConfig & load_forion_config (reads forion: YAML section)
├── types.py        — ForionProduct, normalize_product, TypedDict schemas
├── routing.py      — resolve_model_for_product, get_fallback_models
├── hooks.py        — ForionCustomLogger (LiteLLM callback), ForionHookManager
├── logging.py      — log_forion_request (structured logging)
└── example_config.yaml
```

### How it works

1. **Config loading** — `load_forion_config()` reads the `forion:` section from the proxy YAML. If missing or malformed, it silently disables itself.

2. **Product normalization** — `normalize_product()` coerces any string to a valid `ForionProduct` (`ide`, `spark`, `orbit`, or `unknown`).

3. **Routing** — `resolve_model_for_product()` maps a product to its default model only when the caller didn't specify one. Existing model selections are never overridden.

4. **Hooks** — `ForionCustomLogger` plugs into LiteLLM's callback system:
   - **Pre-call**: extracts product/user/workspace metadata from the request
   - **Post-call**: injects `forion_metadata` (product, cost, token usage) into `response._hidden_params`

5. **Hook manager** — `ForionHookManager` allows external systems to register async `before_request` / `after_response` hooks. Failing hooks are logged but never crash the proxy.

---

## 9. Troubleshooting

### `ImportError: no pq wrapper available`

```bash
poetry run pip install psycopg-binary
```

This is needed because the lock file only includes `psycopg` without the binary wheel.

### Config YAML syntax errors

Validate your YAML:

```bash
python3 -c "import yaml; yaml.safe_load(open('forion_config.yaml'))"
```

### Environment variables not loaded

Verify they are set:

```bash
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY
```

If empty, reload:

```bash
set -a && source .env && set +a
```

### Port 4000 already in use

Kill the existing process:

```bash
lsof -ti:4000 | xargs kill -9
```

Or use a different port:

```bash
poetry run litellm --config forion_config.yaml --port 4001
```

### API key errors (401 / AuthenticationError)

- Verify the key is valid at the provider's dashboard
- Ensure the `.env` key names match exactly what `forion_config.yaml` references (e.g. `OPENAI_API_KEY`)
- Keys must not have leading/trailing spaces

### Proxy starts but requests hang

- Check the proxy is fully started (wait for the health endpoint)
- Verify the model names in your request match `model_name` in `forion_config.yaml`

### `poetry install` fails with lock file error

```bash
poetry lock
poetry install
```

---

## 10. Quick Reference — All Commands

```bash
# --- Setup ---
git clone https://github.com/BerriAI/litellm.git
cd litellm
poetry install
poetry run pip install psycopg-binary
cp .env.forion.example .env
# Edit .env with your API keys

# --- Run ---
set -a && source .env && set +a
poetry run litellm --config forion_config.yaml --port 4000

# --- Test ---
curl http://localhost:4000/health
poetry run pytest tests/test_litellm/test_forion/test_forion.py -x -vv

# --- Lint ---
cd litellm && poetry run ruff check .
```

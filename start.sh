#!/bin/bash
# Start the LiteLLM proxy with Forion config
set -a && source .env && set +a
poetry run litellm --config forion_config.yaml --port 4000

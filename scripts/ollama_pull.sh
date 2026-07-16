#!/bin/sh
# scripts/ollama_pull.sh
# Pull required models on Ollama container first start.
# This runs inside the ollama container after the server is ready.

set -e

echo "Pulling embedding model: nomic-embed-text ..."
ollama pull nomic-embed-text

echo "Pulling LLM: llama3 ..."
ollama pull llama3

echo "All Ollama models ready."

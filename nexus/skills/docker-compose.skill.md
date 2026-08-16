---
name: docker-compose
description: Unified Docker Compose configuration with profiles
version: 1.0.0
category: infrastructure
tags: [docker, compose, infrastructure, deployment, containers]
---

# Docker Compose

Unified Docker Compose configuration with 4 profiles and 7 services, replacing 19 previous definitions.

## Profiles
| Profile | Services | Use Case |
|---------|----------|----------|
| `core` | redis, freqtrade | Minimum trading setup |
| `full` | redis, freqtrade, streamlit, mcp-server | Full stack |
| `dev` | redis, freqtrade, streamlit, mcp-server, chromadb | Development |

## Services
- `redis` — Signal bus message broker
- `freqtrade` — Core trading engine
- `streamlit` — Bloomberg-inspired UI
- `mcp-server` — Finance data MCP server
- `chromadb` — Vector store for learning loop

## Trigger Phrases
- "start docker compose", "restart services"
- "deploy with compose", "check container logs"

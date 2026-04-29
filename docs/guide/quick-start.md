# AI Video Platform -- Quick Start Guide

## Prerequisites
- Docker running (PostgreSQL)
- Node.js 22+
- Python 3.12 with venv
- .env file with API keys configured

## Quick Start (3 steps)
1. Start services: `docker compose up -d postgres && cd /path/to/AI_vedio && source .venv/bin/activate && uvicorn src.api:app --reload --port 8001` (Terminal 1) then `cd web && npm run dev` (Terminal 2)
2. Open http://localhost:3001
3. Select scenario, enter product, choose duration, click "Configure & Start"

## Step-by-Step Mode
- Toggle "Step by Step" in the scenario panel
- Click "Run" on each step sequentially
- Edit any step output before continuing
- Regenerate a step to invalidate all downstream steps

## Auto Mode
- Toggle "Auto" in the scenario panel
- Click "Configure & Start" -- all 12 steps run automatically
- Results appear in tabs: Briefs, Scripts, Videos, Thumbnails, Media, Quality

## Language
- Click the locale toggle button (CN/EN) in the navigation bar
- All product names and USPs are auto-translated to English for video generation
- UI switches between Chinese and English on demand

## Duration
- Choose from 5 tiers: 5-15s, 15-30s, 30-45s, 45-60s, 60-90s
- Content strategy determines actual duration within the range

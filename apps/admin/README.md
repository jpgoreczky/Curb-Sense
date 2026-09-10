# Curb Sense — Admin Ops Tool

**Status:** Reserved / not yet scaffolded.

## Purpose
Internal tool for the ops team to push manual Tier 1 data overrides
(e.g., city-wide or district-wide snow-emergency routes, emergency
street-sweeping changes) that bypass the standard municipal ETL feeds.
Also hosts the anomaly-review queue for crowdsourced early-warning
flags (see `GAM-6.5`).

## Planned Stack
- Vite + React + TypeScript (SPA)
- Mapbox GL JS for polygon-drawing UI (district/area override selection)
- Calls the existing FastAPI backend (`/apps/api`) — no separate backend

## Scaffolding Status
Not yet built. This app will be scaffolded as the first sub-task under
`BACK-2.7: Internal manual ingestion (ops) tool`, once the three-tier
data model (`BACK-2.1`–`BACK-2.3`) exists for it to write against.

Decision rationale: a server-rendered (Jinja2/FastAPI) admin tool was
considered and rejected — it would not scale to the polygon-drawing
requirement without a later migration. A full SPA was also considered
and deferred, to avoid scaffolding dependencies and CI/CD steps for a
tool with no backend to integrate against yet.
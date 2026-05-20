---
order: 100
---
# CamouFlow

CamouFlow is a desktop app for running browser automation scenarios (Camoufox/Playwright) across a list of profiles.

## Features

- Stores profiles (accounts) and their assigned proxies.
- Imports profiles in bulk using a configurable account template.
- Uses tags to group profiles and run scenarios for the selected tag.
- Edits scenarios as a chain of steps (transitions, nested scenarios, variables).
- Supports shared variables to exchange data across profiles/runs.
- Manages proxy pools with health checks, selection, release and removal actions.
- Keeps execution logs.

## Data locations

- Profiles: `settings/accounts.json`
- Scenarios: `scenaries/*.json`
- Settings: `settings/settings.json`
- Browser profile folders: `profiles/`
- Scenario outputs (write_file): `outputs/`
- Logs: `logs/`

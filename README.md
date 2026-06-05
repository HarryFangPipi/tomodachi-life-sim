# Tomodachi World

Kairosoft-style pixel social simulation inspired by Tomodachi Life. Residents walk around town, manage needs, remember conversations, build relationships, and can use a local Ollama model for dialogue.

## Requirements

- Python with `requirements.txt` installed
- Node.js for Playwright visual checks
- Optional: Ollama running at the configured `ollama_url`

## Start

Use the stable scripts:

```bat
start_server.bat
```

Then open:

```text
http://127.0.0.1:8000/
```

Do not close the server command window while playing.

## Stop / Restart

```bat
stop_server.bat
restart_server.bat
```

## Configuration

Runtime settings live in `config.json`:

- `host`, `port`
- `ollama_url`
- `preferred_models`
- `tick_seconds`
- `game_hours_per_tick`
- `max_agents`
- `save_path`
- `autoload_save`
- `autosave_seconds`

## Save Data

Save data is written to `data/savegame.json`.

Available APIs:

- `POST /api/save`
- `POST /api/load`
- `POST /api/reset-save`

## Visual Check

Playwright is installed for automated screenshots and canvas checks:

```bash
npm run visual:check
```

Outputs:

- `screenshots/desktop.png`
- `screenshots/mobile.png`
- `screenshots/visual_report.json`


- # SmartTScope
    

- A software to steer a Celestron C8 telescope.
    

- ## Purpose
    

- This software shall allow handling the complex hardware setup in a smart way allowing the user to get great pictures of moon, planets, stars, deep space objects and even the ISS.
    
    

- ## Folder structure
    

- ```
    
- raw/ -- source documents (immutable -- never modify these)
    
- docs/ -- markdown pages maintained by Claude

- resources/ -- external information or adapters to be used by this project
    
- resources/hlrequirements -- high level requirements. Integrate into the todo list when asked by the user

- wiki/index.md -- table of contents for the entire wiki
    
- wiki/log.md -- append-only record of all operations
    
- ```
    

- ## Ingest workflow
    

- When the user adds a new source to `resources/hlrequirements/` or `docs/` and asks you to ingest it:
    

- 1. Read the full document
    
- 2. Discuss key takeaways with the user before writing anything
    
- 3. Create or update an prioritized existing todo list `todo.md` in `docs/`

- 4. Plan the development of the top todos by defining test cases

- 5. Request user approval

- 6. Develop the next todo until the tests pass
    
- 7. Append an entry to `wiki/log.md` with the date, source name, and what changed and update the todo list

- 8. ask user for pushing to git and push git in case

    
- ## External modules

- `resources/camera_adapter/` is maintained by an external party.

- - Never edit files inside `resources/camera_adapter/` directly.
- - When a new release arrives, run `bash scripts/sync_camera_adapter.sh` to copy owned files into `smart_telescope/`.
- - `SYNC.md` at the project root tracks the sync state, active SYNC-OVERRIDEs, and pending external requirements.
- - If a new feature requires changes to an external-owned file, record it in `SYNC.md` under "Pending external requirements" and wait for the external party to deliver. Do NOT implement it locally.
- - External-owned files in `smart_telescope/` are listed in `SYNC.md`. Smart_telescope-owned files (`config.py`, `runtime.py`, all `api/`) consume those APIs and are ours to modify.

- ## Code

- 1. Develop based on Python 3.13

- 2. Application to run under a Raspberry 5 based on Trixie 64

- 1. Testing under Windows 11 using mock devices

- ## Pi deployment

- - Pi runs from source at `~/astro_sw/SmartTScope/` using `bash ~/astro_sw/astro_start.sh` (no systemd service).
- - To update the Pi: `git fetch origin && git reset --hard origin/main`, then restart via `bash ~/astro_sw/astro_start.sh`.
- - Pi hardware config lives at `~/.SmartTScope/config.toml` (outside the repo — not touched by git reset).

- ## Rules
    

- - Never modify anything in the `raw/` folder
    
- - Always update `wiki/index.md` and `wiki/log.md` after changes
    
- - Keep page names lowercase with hyphens (e.g. `machine-learning.md`)
    
- - Write in clear, plain language
    
- - When uncertain about how to categorize something, ask the user
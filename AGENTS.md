# AGENTS.md

## Cursor Cloud specific instructions

### Architecture overview
This is a single-repo, multi-service media automation app with:
- **Python backend** (FastAPI/Uvicorn on port 8777) — core automation, webhook handling, Selenium browser automation
- **Nuxt 4 frontend** "Darth Vadarr" (port 3777) — Vue 3 SSR dashboard with Nitro server API routes that query MySQL directly
- **MySQL 8.0** (port 3306) — primary data store for config, logs, media, queue state

All three must run for the dashboard to function. The Nuxt server-side API routes (`server/api/*.ts`) connect to MySQL directly; the frontend also proxies some calls to the Python backend.

### Starting services

1. **MySQL**: `sudo mkdir -p /var/run/mysqld && sudo chown mysql:mysql /var/run/mysqld && sudo mysqld --user=mysql --datadir=/var/lib/mysql &` — wait ~5s, then verify with `sudo mysqladmin ping`.
2. **Python backend**: Source the `.env` file vars, then run `uvicorn main:app --host 0.0.0.0 --port 8777 --workers 1 &` from the workspace root. Required env vars are listed in `.env.example`.
3. **Nuxt frontend**: `NUXT_SOCKET=0 npx nuxt dev --port 3777 --host 0.0.0.0 &` from the workspace root, with the same DB env vars plus the backend URL env var pointing to `http://localhost:8777`.

All DB credentials are in the `.env` file in the workspace root (see `.env.example` for the template).

### Key dev commands
- **Lint**: `npx eslint .` (note: no `.eslintrc` config file exists in repo yet; `npm run lint` will fail until one is added)
- **TypeScript check**: `npx nuxi typecheck` (existing TS errors in codebase; nuxt.config.ts disables typeCheck for dev)
- **Build**: `npm run build`
- **Dev**: `npm run dev` (wraps `cross-env NUXT_SOCKET=0 nuxt dev --port 3777 --host 0.0.0.0`)

### Important caveats
- The `.env` file must use `DB_HOST=127.0.0.1` (not `localhost`) and `DB_PORT=3306` for local MySQL — the socket file may have permission issues but TCP connections work fine.
- Python deps install to `~/.local/bin` — ensure `PATH` includes this directory.
- The backend downloads ChromeDriver on first startup (requires internet). It stores it at `seerr/chromedriver/`.
- `requirements.txt` includes `win32_setctime` which installs cleanly on Linux (no-op).
- The backend's API is mounted at `/api` (e.g., `/api/health`), not at the root.
- The Nuxt frontend redirects from `/` to `/dashboard` (302). The setup wizard is skipped if config is detected in the database.
- `package-lock.json` is present — use `npm install --legacy-peer-deps` (peer dep conflicts exist without the flag).

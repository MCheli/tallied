# Public demo + login page playbook

How Tallied got a public, read-only demo (money-demo.markcheli.com) and a login page that introduces the app, written so the same can be done for another app on the 83RR PowerEdge. Built 2026-10-31; the code referenced below is in this repo.

## The prompt

Paste this into a Claude Code session in the target repo:

> Read `/Users/mcheli-mini/repos/tallied/docs/DEMO-PLAYBOOK.md` and apply it to this app. I want a public, read-only demo at `<app>-demo.markcheli.com` running on made-up data, linked from this app's login page and from www.markcheli.com, and the login page revamped with a hero that shows off the app. Start by reading this repo's docs and auth code, then tell me in a few lines: the persona and what fake data the demo needs, which write routes exist and which calculations (if any) should stay allowed, which outbound integrations must be off, and any page that is slow on the server. Then build it, test it, deploy it, and verify the live demo in a real browser. Standing permissions as usual: commit, deploy, monitor.

## What "done" means

1. A visitor clicks a link, presses one button, and is inside the real app looking at a made-up person's data. No sign-up.
2. Every page works and every feature is visible. Nothing can be changed, saved or sent.
3. The demo can never see real data: separate deployment, separate database, separate secrets.
4. The data looks real and current: believable amounts, dates up to today, pages that agree with each other.
5. The real app's login page links to the demo; www.markcheli.com lists it.
6. The login page sells the app to a stranger in five seconds, and still gets the owner signed in on a phone without scrolling.

## Architecture

- **A second deployment, not a path or a tenant.** Same image, started with `<PREFIX>_DEMO_MODE=true`, on its own Postgres container. A `/demo` path or a demo tenant in the real database is one isolation bug away from publishing real data.
- **Host name:** `<app>-demo.markcheli.com`, flat. The Cloudflare origin certificate and Universal SSL cover one level only, so `demo.<app>.markcheli.com` would not get a certificate.
- **Compose:** `<app>-demo-db` on an `internal: true` network shared only with `<app>-demo`; `<app>-demo` also joins `infrastructure` for NGINX. The demo service lists its environment explicitly and **never** uses `env_file: .env`, so the real AI keys, OAuth secrets and provider credentials never reach it. Its own secrets go in the server `.env` as `<APP>_DEMO_*`. Add the Watchtower label like the real service.
- **Startup guards (fail closed):**
  - Refuse to start if the database holds any user who is not a demo persona (Tallied: email not ending in `@tallied.dev`). This makes pointing the demo at the real database impossible.
  - Refuse to start if AI or SSO secrets are set.
  - See `backend/app/demo.py`, `check_demo_settings` and `check_demo_database`.

## Read-only, enforced on the server

- **Deny by default.** A middleware refuses every POST/PUT/PATCH/DELETE in demo mode except an explicit allowlist: demo sign-in, sign-out, token refresh, and pure calculations that save nothing. For Tallied the calculations are plan what-if, sprint and the read-only SQL runner. A new route is refused without anyone remembering to list it. Answer `403 {"detail": "...", "demo": true}`.
- **Second layer in the database.** Tenant/user sessions run `SET TRANSACTION READ ONLY` in demo mode (`tenant_session(read_only=True)`), so a write that slips past the middleware still fails in Postgres.
- **Audit GET handlers that write or call out.** Look for any GET that caches, creates or fetches. Tallied's stock-price lookup fetched Yahoo and inserted a row; in demo mode it now uses the stored price instead.
- **Outbound integrations off:** AI calls, bank sync, email, webhooks, scheduler jobs. Run the demo web-only (`APP_ROLE=web`) with no scheduler.
- **Per-visitor rate limits.** Everyone shares one demo user, so key limits on the visitor IP (`CF-Connecting-IP`, which NGINX passes through), not the user.
- **`X-Robots-Tag: noindex, nofollow`** on demo responses.
- **Tests that must exist:**
  - **Enumerate every route** with a write method, call each in demo mode, and assert all are refused except the allowlist (`backend/tests/test_demo_mode.py::test_every_write_route_is_refused_in_demo_mode`). Newer FastAPI wraps included routers; walk `original_router.routes`.
  - **The allowlist matches exactly** the intended set.
  - **Sign-in:** demo sign-in works in demo mode and is a 404 outside it.
  - **The startup guards refuse** a real user and the secrets.
  - **An e2e test against real Postgres** showing a read-only session cannot write.

## Sign-in

- `POST /auth/demo`, only when demo mode is on, signs in as the persona with no password. It answers 503 "being rebuilt" if the persona isn't there yet (the nightly reseed window).
- `GET /auth/config` (or the app's equivalent) exposes `demo_mode` and `demo_url`. The real deployment sets `<PREFIX>_DEMO_URL` so its login page can link to the demo.

## The persona and the data

- One obviously fictional persona, already used as the app's test fixture (Tallied: Claudius Banks).
- **The seed is one simulation, not random rows.**
  - Generate the underlying events (paychecks, purchases, vests, task completions) and derive every table from them, so totals agree across pages.
  - **Believable amounts:** Tallied's first seed had $1K/month of spending on $210K of pay.
  - **Dates relative to the day it runs,** up to today, never in the future.
  - **Recurring things on fixed days,** so "coming up" views have content.
  - **Deterministic per day** (`random.seed(constant)`), so screenshots are stable.
- **Fresh every day:** the entrypoint reseeds when demo mode is on, and a server crontab restarts the demo container nightly (`0 8 * * * docker restart <app>-demo`). The site is down for a few seconds during the restart.
- **Before calling the data done, screenshot every page** at full height and look at each one. Empty tiles, flat lines and numbers that disagree between pages are seed bugs.

## Frontend

- Load the config once (`stores/appConfig.ts`).
- **Banner** at the top of every page: "Live demo. <Persona> is a made-up person and every number here is generated. Look around; nothing can be changed." Add a link to www.markcheli.com.
- **Disable, don't hide.** Controls that write get a directive (`v-demo-lock`, `frontend/src/directives/demoLock.ts`):
  - It sets `disabled`, `aria-disabled`, a title "Not available in the demo: nothing can be changed or saved", and a faded style.
  - It swallows clicks with a capture listener, for non-buttons.
  - Lock the button that opens a form, not just the form's submit, so visitors never fill in a form that can't save.
  - The server stays the authority; the directive is only for honesty and polish.
- Calculations that are allowed (what-ifs) stay live; "Save" stays locked.
- Test the directive (`frontend/tests/demo-lock.spec.ts`).

## Login page revamp

Reference: `frontend/src/views/LoginView.vue` and `frontend/src/components/login/HeroVisual.vue`.

- **Layout:** split screen on desktop. On the left (about 55%) is an always-dark hero: a deep navy gradient with indigo and green glows and a faint masked grid. On the right is the sign-in panel, which follows the theme.
- **Hero content:**
  1. Logo mark and app name.
  2. **A headline that says what the app is for**, in about ten words ("Every account, paycheck, vest and plan, in one place you own.").
  3. A one-sentence subhead naming the main features and what makes it different (self-hosted, a database you can query).
  4. **An illustrated collage** of three or four of the app's real tiles: frosted cards, a sparkline that draws in, a ring, a chip.
  5. A row of feature chips.
- **The collage:**
  - Inline SVG with fictional numbers, no API calls, so it renders before sign-in and never leaks data.
  - It floats gently and respects `prefers-reduced-motion`.
  - Use the app's own visual language: Tallied's accent is indigo.
- **Sign-in panel:**
  - **On the real deployment:** the normal sign-in, then a card "Just looking? Try the live demo", with one line on what the visitor will see and "Read-only, no sign-in".
  - **On the demo:** a "Live demo" pill, two sentences on who the persona is and that nothing can change, and one big "Enter the demo" button.
  - "Built by Mark Cheli" with a link at the foot.
- **On a phone:** hide the collage and chips, so the owner's sign-in button is on the first screen.
- **Check it** in light, dark and at 390 px.
- **Copy rules:**
  - Claim only what is true.
  - Say "made-up" plainly.
  - No "no cookies" style promises the app can't guarantee.

## Performance on the server

The PowerEdge runs Python about 6× slower than the Mac mini, so a page that's fine locally can take 10+ seconds live. Tallied's Planning page showed only placeholders on the demo; the live check had moved on before it finished.

- **Measure on production** (Tallied logs `latency_ms` per request in `api_usage_logs`). Profile inside the container: `docker exec ... python -c 'cProfile...'`.
- **Show the cheap part first,** then load the expensive part with a visible "working on it" note.
- **Cache expensive pure results** per process, keyed by a hash of the computed inputs (not the request), so any change to the data recomputes them. gunicorn runs two processes, so the first two visits each pay once.

## Verify like a stranger would

- **Unit and e2e tests,** then `make pre-commit` (or the repo's gate).
- **Locally:** run the backend with demo mode on and the AI/SSO variables blanked, plus a frontend pointed at it. Click "Enter the demo" and visit every route in headless Chrome, recording page errors, console errors and any API status of 400 or above.
- **Try writes from the page** with `fetch` and the demo cookie: creating an API key must get a 403.
- **After deploying,** repeat against the live URL.
  - **Wait for slow pages** (up to 45 seconds) before judging them.
  - **Look at the screenshots** yourself.
  - Load the real app's login page and confirm the demo card is there.
- **Check the API:** `curl https://<app>-demo.markcheli.com/<config endpoint>` shows `demo_mode: true`.

## Rollout on the 83RR PowerEdge

The repo is `~/repos/83rr-poweredge` locally and `~/83rr-poweredge` on the server.

1. App repo: demo mode, tests, docs (PRODUCT/ARCHITECTURE/DEPLOYING plus the requirements ledger if the repo has one). Push and wait for CI to build the image.
2. Server `.env`: generate the `<APP>_DEMO_*` secrets (DB password, JWT secret, any peppers or keys) with `secrets.token_urlsafe`. Back up `.env` first.
3. `docker-compose.yml`:
   - Add `<app>-demo-db` and `<app>-demo` plus the internal network and volume.
   - Add `<PREFIX>_DEMO_URL` to the real service.
   - Commit, push, `git pull` on the server, `docker compose config -q`.
4. NGINX `infrastructure/nginx/conf.d/production.conf`:
   - Add the host to the port-80 redirect list.
   - Add a 443 server block like the real app's: the wildcard certificate, a variable `proxy_pass` so Docker DNS re-resolves, a small `client_max_body_size`.
   - Then `docker exec nginx nginx -t && docker exec nginx nginx -s reload`.
5. DNS: a proxied A record with the same IP as the real app, using `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ZONE_ID` from the server `.env` (`POST /zones/<zone>/dns_records`).
6. `docker compose up -d <app>-demo-db <app>-demo`, and add the demo to the app's deploy script so it's pulled and restarted with the real app.
7. Crontab: the nightly restart.
8. Only once the demo answers: PersonalWebsite.
   - Add a `<app>-demo` entry to `services.json`, a terminal shortcut in `frontend/composables/useTerminal.ts`, and a test case in `frontend/tests/terminal.test.ts`.
   - Push.
   - `docker compose pull personal-website flask-api && docker compose up -d --no-deps personal-website flask-api`.

## Pitfalls we hit

- **The data was too thin:** the first seed looked fake in an obvious way. Budget real time for the data; it's what an interviewer sees.
- **A full-page screenshot is not the page:** a sticky banner looked fine live but overlapped the title in the tour's screenshots. A static banner is simpler.
- **The live check gave up too early:** it waited 2.5 seconds per page and called Planning fine while it was still loading.
- **`cat` in Mark's shell numbers lines:** write files with Python or the Write tool, and read them with `command cat`.

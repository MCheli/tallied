# Monarch Money integration — post-mortem

Written 2026-10-29 when the integration was removed (decision DEC-1 in `docs/REVIEW-2026-10-29.md`).

## What it was

An attempt to pull accounts, balances and transactions from Monarch Money so that Tallied did not need its own bank connections. Monarch has no public API. The integration used the unofficial `monarchmoney` Python package, which reverse-engineers the GraphQL calls the Monarch web app makes, plus `gql` for transport.

Over its life it grew to roughly 2,100 lines: `api/monarch_routes.py` (614), `parsers/monarch.py`, `models/monarch_link.py`, a Monarch branch in `services/sync_scheduler.py`, `scripts/repro_monarch_500.py`, `tests/test_monarch_sync_repro.py`, two migrations, and about 250 lines of script and template in `SettingsView.vue`.

## Why it failed

1. **Bot protection.** Monarch sits behind Cloudflare. Requests from a server were challenged, so the code monkey-patched the library to send a Chrome user agent and other browser-like headers. This worked intermittently and broke without notice.
2. **Session auth.** Login took the user's email, password and MFA code in a Tallied form and stored the resulting session token in plaintext in `monarch_links`. Sessions expired, after which every scheduled sync produced 401s and a `failed` row in `sync_jobs` every 12 hours.
3. **No contract.** With no API to read, each Monarch frontend change was a potential break, and there was no way to know what was supported.
4. **Operational noise.** The `gql` transport logged every GraphQL body at INFO (2.6 MB in 22 seconds on the first sync), which had to be silenced in `main.py`.

The tab was hidden from Settings on the commit "Hide Monarch tab from Settings" and dropped from the scheduler's provider list in "Drop Monarch from the 12h scheduler loop", but all the code stayed behind a one-line re-enable that was never going to be used.

## What was kept

- The account-type and display-group mapping (`ACCOUNT_TYPE_MAP`, `DISPLAY_GROUP_MAP`) moved into the provider-neutral account code; it is useful for any provider.
- The `sync_jobs` table and the scheduler core (job row, `NOTIFY`, advisory lock, watchdog) were built for Monarch and remain the pattern for SimpleFIN and future providers.

## Lesson

Only integrate services that publish an API or a documented bridge (SimpleFIN is a bridge over account aggregators and has a contract). A reverse-engineered client against a consumer web app is a maintenance obligation with no floor. If Monarch ships a real API, add it as a provider under the provider interface; nothing from the old code should be revived.

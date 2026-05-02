"""Standalone scheduler container entrypoint.

Run with: python -m app.scheduler

This process holds:
- The 12h scheduled-sync loop (gated by a Postgres advisory lock so only
  one scheduler runs across the cluster).
- A LISTEN connection on the 'monarch_sync' channel — wakes when the web
  tier inserts a manual sync job and NOTIFY's the schema.

It does NOT serve HTTP. The web tier (gunicorn) only inserts job rows and
fires NOTIFY; the actual long-running Monarch API + DB work happens here,
so worker timeouts don't kill in-flight syncs and request latency stays
predictable during sync.
"""
import asyncio
import logging
import os
import signal
import sys


def _configure_logging() -> None:
    level = os.environ.get("FINANCE_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(level)
    for name in ("tallied", "tallied.sync", "app"):
        logging.getLogger(name).setLevel(level)
    # Same noise-damping policy as the web tier.
    for noisy in ("gql", "gql.transport.aiohttp", "aiohttp", "aiohttp.access",
                  "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def _run() -> None:
    logger = logging.getLogger("tallied.sync")

    # Import here so logging is configured first.
    import app.models  # noqa: F401  — register all SQLAlchemy models
    from app.services.sync_scheduler import (
        claim_orphan_jobs,
        mark_running_jobs_failed,
        notify_listener_loop,
        reap_stuck_jobs,
        _scheduler_loop,
    )

    # 1. Reap any 'running' rows older than the watchdog cutoff — leftovers
    #    from a SIGKILL'd previous run that didn't get to its shutdown hook.
    try:
        reap_stuck_jobs()
    except Exception:
        logger.exception("reap_stuck_jobs failed at scheduler boot")

    # 2. Claim any young 'running' rows — these are most likely manual syncs
    #    the web tier created via NOTIFY while the scheduler was down. Run
    #    them sequentially before joining the steady-state listen loop so
    #    the user's click doesn't get stranded waiting for the next 12h tick.
    try:
        claimed = await claim_orphan_jobs()
        if claimed:
            logger.info("Claimed %d orphan running job(s) at boot", claimed)
    except Exception:
        logger.exception("claim_orphan_jobs failed at scheduler boot")

    # 3. Steady state: 12h scheduler + NOTIFY listener run concurrently.
    scheduler_task = asyncio.create_task(_scheduler_loop(), name="scheduler-loop")
    listener_task = asyncio.create_task(notify_listener_loop(), name="notify-listener")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_signal(signum: int):
        logger.info("Scheduler received signal %d, shutting down", signum)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_signal, sig)
        except NotImplementedError:
            # Windows / non-unix — fall back to default handling.
            pass

    try:
        # Exit when EITHER a signal arrives OR a task crashes unexpectedly.
        done, _pending = await asyncio.wait(
            {asyncio.create_task(stop_event.wait()), scheduler_task, listener_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in done:
            if t in (scheduler_task, listener_task) and t.exception():
                logger.error("Scheduler task crashed: %r", t.exception())
    finally:
        # Graceful shutdown — flip running rows so the UI doesn't show a
        # stale 'syncing' state until the next-boot watchdog catches them.
        try:
            n = mark_running_jobs_failed("worker shutdown")
            if n:
                logger.info("Shutdown: marked %d running job(s) failed", n)
        except Exception:
            logger.exception("mark_running_jobs_failed errored on shutdown")
        for t in (scheduler_task, listener_task):
            if not t.done():
                t.cancel()
        await asyncio.gather(scheduler_task, listener_task, return_exceptions=True)


def main() -> None:
    _configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()

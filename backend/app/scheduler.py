"""Lightweight in-process jobs. Drive backup, EMI auto-post, and Gmail sync check once a minute."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

log = logging.getLogger("vault.scheduler")


async def _loop(stop: asyncio.Event) -> None:
    from app.drive_backup import run_due_backups
    await asyncio.sleep(8)
    while not stop.is_set():
        try:
            await asyncio.to_thread(run_due_backups)
        except Exception:
            log.exception("scheduled job failed")
        try:
            from app.emi import run_due_emis
            await asyncio.to_thread(run_due_emis)
        except Exception:
            log.exception("emi job failed")
        try:
            from app.expense_analyser import run_due_syncs
            await asyncio.to_thread(run_due_syncs)
        except Exception:
            log.exception("expense analyser sync job failed")
        try:
            from app.telegram_notify import run_due_reminder_notifications
            await asyncio.to_thread(run_due_reminder_notifications)
        except Exception:
            log.exception("reminder notification job failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = asyncio.Event()
    task = asyncio.create_task(_loop(stop))
    yield
    stop.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

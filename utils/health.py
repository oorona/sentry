from aiohttp import web
import asyncio
import logging
logger = logging.getLogger(__name__)
import utils.database as udb
from sqlalchemy import text


def _sync_db_check():
    try:
        udb_engine = getattr(udb, 'engine', None)
        if udb_engine is None:
            return False, 'no-engine'
        with udb_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as e:
        return False, str(e)


async def _check_db():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_db_check)


async def health_handler(request):
    ok, err = await _check_db()
    if ok:
        return web.json_response({"status": "ok"}, status=200)
    else:
        logger.warning(f"Health check failed: {err}")
        return web.json_response({"status": "unhealthy", "error": err}, status=503)


async def start_health_server(host: str = "0.0.0.0", port: int = 8080):
    app = web.Application()
    app.router.add_get('/health', health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"Health server running on http://{host}:{port}/health")
    # Keep the coroutine alive
    while True:
        await asyncio.sleep(3600)

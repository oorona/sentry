from aiohttp import web
import asyncio
import logging
logger = logging.getLogger(__name__)
import utils.database as udb
from sqlalchemy import text
from datetime import datetime, timezone
import psutil
import os


def _sync_db_check():
    """Synchronous database health check."""
    try:
        udb_engine = getattr(udb, 'engine', None)
        if udb_engine is None:
            return False, 'no-engine', 0
        
        start_time = datetime.now()
        with udb_engine.connect() as conn:
            # Test basic connectivity
            conn.execute(text("SELECT 1"))
            
            # Try to get event count if log_entries table exists
            try:
                result = conn.execute(text("SELECT COUNT(*) FROM log_entries"))
                event_count = result.scalar() or 0
            except Exception:
                event_count = 0
                
        response_time = (datetime.now() - start_time).total_seconds() * 1000  # ms
        return True, None, event_count, response_time
    except Exception as e:
        return False, str(e), 0, 0


def _get_system_info():
    """Get system resource information."""
    try:
        process = psutil.Process()
        return {
            "cpu_percent": process.cpu_percent(),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "pid": os.getpid(),
            "threads": process.num_threads(),
            "uptime_seconds": (datetime.now() - datetime.fromtimestamp(process.create_time())).total_seconds()
        }
    except Exception as e:
        logger.warning(f"Failed to get system info: {e}")
        return {
            "cpu_percent": 0,
            "memory_mb": 0,
            "pid": os.getpid(),
            "threads": 0,
            "uptime_seconds": 0
        }


async def _check_db():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_db_check)


async def health_handler(request):
    """Enhanced health check endpoint with comprehensive status."""
    # Get database status
    db_result = await _check_db()
    if len(db_result) == 4:
        db_ok, db_err, event_count, db_response_time = db_result
    else:
        # Fallback for old format
        db_ok, db_err = db_result[:2]
        event_count, db_response_time = 0, 0
    
    # Get system information
    system_info = _get_system_info()
    
    # Build comprehensive health response
    health_data = {
        "status": "healthy" if db_ok else "unhealthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {
            "status": "connected" if db_ok else "disconnected",
            "error": db_err if not db_ok else None,
            "response_time_ms": round(db_response_time, 2) if db_ok else None,
            "event_count": event_count if db_ok else None
        },
        "system": {
            "cpu_percent": round(system_info["cpu_percent"], 1),
            "memory_mb": round(system_info["memory_mb"], 1),
            "pid": system_info["pid"],
            "threads": system_info["threads"],
            "uptime_seconds": round(system_info["uptime_seconds"])
        },
        "service": {
            "name": "sentry-discord-bot",
            "version": "1.0.0"
        }
    }
    
    status_code = 200 if db_ok else 503
    
    if not db_ok:
        logger.warning(f"Health check failed - DB: {db_err}")
        
    return web.json_response(health_data, status=status_code)


async def start_health_server(host: str = "0.0.0.0", port: int = 8080):
    app = web.Application()
    app.router.add_get('/health', health_handler)
    app.router.add_get('/health/ready', readiness_handler)
    app.router.add_get('/health/live', liveness_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"Health server running on http://{host}:{port}/health")
    logger.info(f"Endpoints available: /health, /health/ready, /health/live")
    
    # Keep the coroutine alive
    while True:
        await asyncio.sleep(3600)


async def readiness_handler(request):
    """Kubernetes-style readiness probe - checks if service is ready to receive traffic."""
    db_result = await _check_db()
    db_ok = db_result[0] if db_result else False
    
    if db_ok:
        return web.json_response({
            "status": "ready",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status=200)
    else:
        return web.json_response({
            "status": "not_ready", 
            "reason": "database_unavailable",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status=503)


async def liveness_handler(request):
    """Kubernetes-style liveness probe - checks if service is alive (always returns OK if reachable)."""
    system_info = _get_system_info()
    return web.json_response({
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(system_info["uptime_seconds"]),
        "pid": system_info["pid"]
    }, status=200)

# src/main.py
import os
import logging
logger = logging.getLogger(__name__)
import bot
import asyncio
from dotenv import load_dotenv
from utils.database import get_secret


def main():
    # --- Setup Configurable Logging ---
    from logging.handlers import RotatingFileHandler
    from datetime import datetime
    import json as _json

    load_dotenv()

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FILE = os.getenv("LOG_FILE")
    LOG_ROTATE = int(os.getenv("LOG_ROTATE", "0"))
    LOG_BACKUPS = int(os.getenv("LOG_BACKUPS", "3"))
    LOG_JSON = os.getenv("LOG_JSON", "false").lower() in ("1", "true", "yes")

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Console handler
    ch = logging.StreamHandler()
    if LOG_JSON:
        def json_formatter(record):
            payload = {
                "ts": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
                "name": record.name,
                "level": record.levelname,
                "msg": record.getMessage(),
            }
            if record.exc_info:
                payload["exc"] = logging.Formatter().formatException(record.exc_info)
            return _json.dumps(payload)

        ch.setFormatter(logging.Formatter(fmt="%(message)s"))
        ch.format = lambda record: json_formatter(record)
    else:
        ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(ch)

    # Optional rotating file handler
    if LOG_FILE:
        if LOG_ROTATE > 0:
            fh = RotatingFileHandler(LOG_FILE, maxBytes=LOG_ROTATE, backupCount=LOG_BACKUPS)
        else:
            fh = logging.FileHandler(LOG_FILE)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        root_logger.addHandler(fh)

    # Reduce verbosity of noisy libraries by default
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    
    # --- Load sensitive environment variables (after logging config) ---
    token = get_secret("DISCORD_TOKEN", "DISCORD_TOKEN_FILE")


    if not token:
        logging.error("DISCORD_TOKEN not found in environment or DISCORD_TOKEN_FILE. Please set it.")
        return

    # --- Run the Bot with graceful shutdown handlers ---
    import signal

    async def run_bot():
        client = bot.LoggingBot()
        loop = asyncio.get_running_loop()

        async def _on_signal_async():
            logging.info("Signal received, sending shutdown notification...")
            try:
                # Send detailed shutdown notification
                await client._send_notification(
                    title="Sentry Bot", 
                    event="Apagado del Bot", 
                    extra={
                        "Tipo de cierre": "Señal recibida",
                        "Hora de cierre": datetime.utcnow().strftime('%B %d, %Y at %I:%M %p')
                    }
                )
                # Give time for the message to be sent
                await asyncio.sleep(1)
            except Exception as e:
                logging.debug(f"Failed to send shutdown notification: {e}")
            
            logging.info("Closing bot...")
            await client.close()

        def _on_signal():
            logging.info("Signal received, scheduling graceful shutdown...")
            try:
                asyncio.create_task(_on_signal_async())
            except Exception:
                # If loop is already stopping, ignore
                logging.debug("Failed to schedule shutdown from signal handler.")

        # Register signal handlers (Unix-only; safe on Linux)
        try:
            loop.add_signal_handler(signal.SIGINT, _on_signal)
            loop.add_signal_handler(signal.SIGTERM, _on_signal)
        except NotImplementedError:
            logging.warning("Signal handlers not supported in this environment; graceful shutdown may not run.")

        try:
            await client.start(token)
        except asyncio.CancelledError:
            pass
        finally:
            if not client.is_closed():
                await client.close()

    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
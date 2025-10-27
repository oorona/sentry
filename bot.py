# bot.py
import discord
from discord.ext import commands
import logging
import os
import json
import asyncio
from utils.database import init_db
import utils.database as udb
from utils.health import start_health_server
from sqlalchemy import text
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
import os

_SHUTDOWN_TIMEOUT = 5

class LoggingBot(commands.Bot):
    def __init__(self):
        self.config = self.load_config()
        if not self.config:
            logging.error("Failed to load configuration. Exiting.")
            exit()
        # Validate and coerce admin_role_ids to ints (silent-skip invalid entries)
        raw_admin_ids = self.config.get("admin_role_ids", [])
        valid_admin_ids = []
        for rid in raw_admin_ids:
            try:
                valid_admin_ids.append(int(rid))
            except Exception:
                logging.warning(f"Invalid admin_role_id in config.json, skipping: {rid}")
        self.config["admin_role_ids"] = valid_admin_ids
            
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        # Enable message and reaction intents to observe edits/deletes if available
        intents.messages = True
        intents.reactions = True
        super().__init__(command_prefix='!', intents=intents)

        init_db()
        # Track whether we've already notified the configured log channel
        self._notified_ready = False
        # Record the start time for uptime calculation
        self._start_time = datetime.utcnow()
        # In-memory counters for received events (useful for diagnostics)
        from collections import defaultdict
        self._event_counters = defaultdict(int)

    def load_config(self):
        """Load configuration from environment variables (.env) with optional fallback to config.json.

        Environment variables supported:
        - LOG_CHANNEL_ID
        - NOTIFY_CHANNEL_ID
        - ADMIN_ROLE_IDS (comma-separated list of role IDs)
        - GUILD_ID
        - HEALTH_HOST
        - HEALTH_PORT
        - EVENTS (comma-separated list of enabled event keys, e.g. on_member_join,on_message_edit)

        If a config.json exists, its values are used only for keys not set via env.
        """
        cfg = {}
        # First try to load from config.json as fallback
        file_cfg = {}
        try:
            with open('config.json', 'r') as f:
                file_cfg = json.load(f)
        except Exception:
            file_cfg = {}

        # Helper to get from env then file then default
        def _get_env(key, file_key=None, default=None):
            val = os.getenv(key)
            if val is not None and val != "":
                return val
            if file_key is None:
                file_key = key.lower()
            return file_cfg.get(file_key, default)

        # IDs
        def _parse_int(val):
            try:
                return int(val)
            except Exception:
                return None

        cfg["log_channel_id"] = _parse_int(_get_env("LOG_CHANNEL_ID", "log_channel_id"))
        cfg["notify_channel_id"] = _parse_int(_get_env("NOTIFY_CHANNEL_ID", "notify_channel_id"))
        cfg["guild_id"] = _parse_int(_get_env("GUILD_ID", "guild_id"))

        # Admin roles: comma-separated
        admin_raw = _get_env("ADMIN_ROLE_IDS", "admin_role_ids", [])
        admin_list = []
        if isinstance(admin_raw, list):
            admin_list = admin_raw
        elif isinstance(admin_raw, str):
            admin_list = [v.strip() for v in admin_raw.split(",") if v.strip()]
        for v in list(admin_list):
            try:
                admin_list[admin_list.index(v)] = int(v)
            except Exception:
                # skip invalid entries
                try:
                    admin_list.remove(v)
                except Exception:
                    pass
        cfg["admin_role_ids"] = admin_list

        # Health
        cfg["health_host"] = _get_env("HEALTH_HOST", "health_host", "0.0.0.0")
        cfg["health_port"] = _parse_int(_get_env("HEALTH_PORT", "health_port", 8080)) or 8080

        # Events: default to file or sensible defaults
        default_events = file_cfg.get("events", {
            "on_member_join": True,
            "on_member_remove": True,
            "on_member_update": True,
            "on_user_update": True,
            "on_member_ban": True,
            "on_member_unban": True,
            "on_message_edit": True,
            "on_message_delete": True,
            "on_bulk_message_delete": True,
            "on_guild_role_create": True,
            "on_guild_role_delete": True,
            "on_guild_role_update": True,
            "on_guild_channel_create": True,
            "on_guild_channel_delete": True,
            "on_guild_channel_update": True,
            "on_voice_state_update": True
        })

        events_env = os.getenv("EVENTS")
        if events_env:
            # only enable the listed events (comma-separated)
            enabled = set([e.strip() for e in events_env.split(",") if e.strip()])
            events = {k: (k in enabled) for k in default_events.keys()}
        else:
            events = default_events
        cfg["events"] = events

        logging.info("Configuration loaded from environment with fallback to config.json (if present).")
        return cfg

    async def load_cogs(self):
        """Finds all python files in the 'cogs' directory and loads them asynchronously."""
        # --- UPDATED PATHS ---
        cogs_physical_path = "cogs" # cogs directory is now directly in /app
        cogs_import_path_prefix = "cogs" # For import, it's just 'cogs'

        for filename in os.listdir(cogs_physical_path):
            if filename.endswith(".py") and not filename.startswith("__"):
                try:
                    await self.load_extension(f'{cogs_import_path_prefix}.{filename[:-3]}')
                    logging.info(f"Successfully loaded cog: {filename}")
                except Exception as e:
                    logging.error(f"Failed to load cog {filename}: {e}")

    async def on_ready(self):
        logging.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logging.info("Bot is ready and listening for events.")
        # Start a lightweight HTTP health endpoint in the background (checks DB connectivity)
        try:
            host = os.getenv("HEALTH_HOST", "0.0.0.0")
            port = int(os.getenv("HEALTH_PORT", "8080"))
            # schedule the aiohttp server on the bot's event loop
            asyncio.create_task(start_health_server(host=host, port=port))
            logging.info(f"Scheduled health server on {host}:{port} (/health)")
        except Exception as e:
            logging.warning(f"Failed to schedule health server: {e}")
        # Load cogs asynchronously (extensions expect the bot to be fully initialized)
        try:
            await self.load_cogs()
        except Exception as e:
            logging.error(f"Failed to load cogs: {e}")
    # Sync app commands (slash commands) to ensure they register with Discord.
    # If a dev guild is configured (`guild_id` in config or GUILD_ID env),
    # prefer registering commands to that guild only (DEV/GUILD-only mode) for
    # fast availability during development. Set DEV_GUILD_ONLY=0 to force global sync.
    # Sync app commands (slash commands) to ensure they register with Discord.
    # If a guild is configured (`guild_id` in config or GUILD_ID env),
    # sync there first for immediate availability, then perform global sync once.
        dev_guild = None
        if self.config.get("guild_id"):
            try:
                dev_guild = int(self.config.get("guild_id"))
            except Exception:
                logging.warning("Invalid guild_id in config.json; skipping guild sync.")
        elif os.getenv("GUILD_ID"):
            try:
                dev_guild = int(os.getenv("GUILD_ID"))
            except Exception:
                logging.warning("Invalid GUILD_ID env var; skipping guild sync.")

        dev_guild_only = os.getenv("DEV_GUILD_ONLY")
        if dev_guild_only is None:
            dev_guild_only = True if dev_guild else False
        else:
            dev_guild_only = str(dev_guild_only).lower() not in ("0", "false", "no")

        if not getattr(self, "_commands_synced", False):
            try:
                # If dev-guild-only mode is enabled and a dev guild exists, sync to guild only.
                current_cmds = list(self.tree.walk_commands())
                if current_cmds:
                    logger.info(f"Pre-sync commands present in tree: {[c.qualified_name for c in current_cmds]}")
                else:
                    logger.info("Pre-sync: no commands present in tree.")

                if dev_guild and dev_guild_only:
                    # Use the more robust guild-sync approach (log names and fallback to global sync
                    # if the expected command isn't present). This was proven in another project.
                    guild_id = dev_guild
                    logger.debug("Attempting to sync application commands to guild %s", guild_id)
                    try:
                        synced = await self.tree.sync(guild=discord.Object(id=guild_id))
                        logger.info("Application commands synced to guild %s. synced_count=%d", guild_id, len(synced))
                        try:
                            names = [c.name for c in synced]
                            logger.info("Synced command names: %s", ", ".join(names))
                        except Exception:
                            logger.exception("Failed to enumerate synced commands")

                        # Build sets of names from the guild-synced commands (name and qualified_name)
                        try:
                            synced_names = set([getattr(c, 'name', None) for c in synced if getattr(c, 'name', None)]) | set([getattr(c, 'qualified_name', None) for c in synced if getattr(c, 'qualified_name', None)])
                        except Exception:
                            synced_names = set([getattr(c, 'name', None) for c in synced if getattr(c, 'name', None)])

                        # Build the set of locally defined command names we expect to exist (name and qualified_name)
                        local_cmds = list(self.tree.walk_commands())
                        try:
                            local_names = set([getattr(c, 'name', None) for c in local_cmds if getattr(c, 'name', None)]) | set([getattr(c, 'qualified_name', None) for c in local_cmds if getattr(c, 'qualified_name', None)])
                        except Exception:
                            local_names = set([getattr(c, 'name', None) for c in local_cmds if getattr(c, 'name', None)])

                        # If any local command is missing from the guild-synced set, fallback to a global sync
                        missing = local_names - synced_names
                        if missing:
                            logger.info("Guild-synced commands missing local commands: %s; attempting global sync as fallback.", ", ".join(sorted(list(missing))[:50]))
                            try:
                                global_synced = await self.tree.sync()
                                logger.info("Global sync completed. total_global_synced=%d", len(global_synced))
                                try:
                                    gnames = [c.name for c in global_synced]
                                    logger.info("Global synced command names sample: %s", ", ".join(gnames[:50]))
                                except Exception:
                                    logger.exception("Failed to enumerate global synced commands")
                            except Exception:
                                logger.exception("Global sync fallback failed")

                    except Exception:
                        logger.exception("Failed to sync application commands to guild %s", guild_id)
                else:
                    # Default behavior: ensure global commands exist, then optionally copy to dev guild
                    try:
                        synced_global_cmds = await self.tree.sync()
                        logger.info(f"Application commands globally synced: {len(synced_global_cmds)} commands.")
                        if synced_global_cmds:
                            logger.info(f"Global-synced commands: {[c.name for c in synced_global_cmds]}")
                    except Exception as e:
                        logger.warning(f"Global application command sync failed: {e}")

                    if dev_guild:
                        guild_obj = discord.Object(id=dev_guild)
                        try:
                            logger.info(f"Copying global commands to guild {dev_guild} to ensure availability...")
                            await self.tree.copy_global_to(guild_obj)
                            logger.info("copy_global_to completed")
                        except Exception as e:
                            # Make copy failures more visible
                            logger.warning(f"copy_global_to failed for guild {dev_guild}: {e}")

                        try:
                            synced_guild_cmds = await self.tree.sync(guild=guild_obj)
                            logger.info(f"Application commands synced to guild {dev_guild}: {len(synced_guild_cmds)} commands.")
                            if synced_guild_cmds:
                                logger.info(f"Guild-synced commands: {[c.name for c in synced_guild_cmds]}")
                        except Exception as e:
                            logger.warning(f"Guild command sync to {dev_guild} failed: {e}")

                self._commands_synced = True
            except Exception as e:
                logging.warning(f"Failed to sync application commands: {e}")

        # Send a one-time readiness notification to the configured notify channel (if any).
        try:
            if not getattr(self, "_notified_ready", False):
                # Use notify_channel_id primarily; fall back to log_channel_id if not present
                notify_key = "notify_channel_id" if self.config.get("notify_channel_id") else "log_channel_id"
                await self._send_notification(title="Sentry Bot", event="Startup", extra={"Started at": datetime.utcnow().isoformat()}, notify_key=notify_key)
                # Mark as notified regardless to avoid repeated attempts during reconnect storms
                self._notified_ready = True
        except Exception:
            logging.debug("Readiness notification step encountered an unexpected error.")

    async def _build_status_embed(self, title: str, event: str, extra: dict | None = None) -> discord.Embed:
        """Build an embed with basic bot stats for notifications."""
        uptime = datetime.utcnow() - getattr(self, "_start_time", datetime.utcnow())
        guild_count = len(self.guilds)
        # approximate user count by summing unique member ids in cached guilds
        user_ids = set()
        for g in self.guilds:
            for m in g.members:
                user_ids.add(m.id)
        user_count = len(user_ids)

        embed = discord.Embed(title=title, color=discord.Color.blue(), timestamp=datetime.utcnow())
        embed.add_field(name="Event", value=event, inline=False)
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        embed.add_field(name="Known users (cached)", value=str(user_count), inline=True)
        embed.add_field(name="Cogs loaded", value=str(len(self.extensions)), inline=True)
        embed.add_field(name="Latency (ms)", value=str(int(self.latency * 1000)) if self.latency else "N/A", inline=True)
        embed.add_field(name="Uptime", value=str(uptime).split(".")[0], inline=True)

        # DB connectivity check (use utils.database.engine if available)
        db_status = "unknown"
        try:
            udb_engine = getattr(udb, 'engine', None)
            if udb_engine is not None:
                with udb_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                db_status = "ok"
            else:
                db_status = "no-engine"
        except Exception as e:
            db_status = f"error: {e}"

        embed.add_field(name="Database", value=db_status, inline=False)

        if extra:
            for k, v in extra.items():
                embed.add_field(name=str(k), value=str(v), inline=False)

        # Add DB table information if available (use module-level `udb` to avoid local shadowing)
        try:
            udb_base = getattr(udb, 'Base', None)
            tables = list(getattr(udb_base, 'metadata').tables.keys()) if udb_base else []
            if tables:
                embed.add_field(name="DB tables", value=", ".join(tables), inline=False)
        except Exception:
            # non-fatal if host project doesn't have utils.database
            pass
        # Optionally add row counts for tables — potentially slow, so enabled by env var
        try:
            read_counts = os.getenv('READ_DB_COUNTS', '0')
            if str(read_counts).lower() not in ('0', 'false', 'no'):
                udb_engine = getattr(udb, 'engine', None)
                if udb_engine is not None:
                    max_tables = int(os.getenv('DB_COUNT_MAX_TABLES', '10'))
                    udb_base = getattr(udb, 'Base', None)
                    table_names = list(getattr(udb_base, 'metadata').tables.keys())[:max_tables] if udb_base else []

                    def _count_table_rows(name):
                        try:
                            # Use PostgreSQL statistics for a fast, approximate row estimate.
                            # reltuples is an estimate maintained by autovacuum/ANALYZE, so
                            # report it as approximate rather than exact.
                            q = text("SELECT COALESCE(reltuples::bigint, 0) AS estimate FROM pg_class WHERE relname = :tname")
                            with udb_engine.connect() as conn:
                                res = conn.execute(q, {"tname": name})
                                row = res.fetchone()
                                if row is None:
                                    return None
                                return int(row[0])
                        except Exception as e:
                            logger.debug(f"Failed to estimate rows for table {name}: {e}")
                            return None

                    import asyncio
                    loop = asyncio.get_running_loop()
                    # Run each table count in the executor concurrently and await with a timeout.
                    try:
                        futures = [loop.run_in_executor(None, _count_table_rows, n) for n in table_names]
                        results = await asyncio.wait_for(asyncio.gather(*futures), timeout=5)
                        tc = dict(zip(table_names, results))
                        # format counts as approximate values
                        parts = [f"{n}: {tc.get(n) if tc.get(n) is not None else '?'} (approx)" for n in table_names]
                        if parts:
                            embed.add_field(name="DB row counts (approx)", value="; ".join(parts), inline=False)
                    except Exception as e:
                        logger.debug(f"Timed out or failed while collecting table row counts: {e}")
        except Exception:
            pass

        return embed

    async def _send_notification(self, title: str, event: str, extra: dict | None = None, notify_key: str = "notify_channel_id"):
        """Send an embed notification to a configured channel (by config key)."""
        channel_id = self.config.get(notify_key)
        if not channel_id:
            logging.debug(f"No '{notify_key}' configured; skipping notification.")
            return

        try:
            chan_id = int(channel_id)
        except Exception:
            logging.warning(f"{notify_key} in config is not an integer: {channel_id}")
            return

        try:
            channel = self.get_channel(chan_id)
            if channel is None:
                channel = await self.fetch_channel(chan_id)
            if not channel:
                logging.warning(f"Could not find notification channel with ID {chan_id}.")
                return

            try:
                embed = await self._build_status_embed(title, event, extra)
            except Exception as e:
                # Capture and log full traceback to help diagnose 'engine' reference errors
                logger.exception("Failed to build status embed for notification")
                # Fallback embed so we can still notify
                fallback = discord.Embed(title=title, color=discord.Color.blue())
                fallback.add_field(name="Event", value=event, inline=False)
                fallback.add_field(name="Error", value=str(e), inline=False)
                embed = fallback

            await channel.send(embed=embed)
            # Prefer a friendly channel label (mention or #name) when logging
            try:
                ch_label = channel.mention if hasattr(channel, 'mention') else f"#{getattr(channel, 'name', chan_id)}"
            except Exception:
                ch_label = str(chan_id)
            logging.info(f"Sent notification to channel {ch_label}: {event}")
        except Exception as e:
            try:
                ch_label = f"#{getattr(channel, 'name', chan_id)}"
            except Exception:
                ch_label = str(channel) if 'channel' in locals() else str(chan_id)
            logging.warning(f"Failed to send notification to channel {ch_label}: {e}")

    async def close(self):
        """Override close to send a shutdown notification before closing the bot."""
        try:
            await self._send_notification(title="Sentry Bot", event="Shutdown", extra={"Closing at": datetime.utcnow().isoformat()})
            # allow small time window for the message to be delivered
            await asyncio.sleep(0.25)
        except Exception:
            logging.debug("Error while sending shutdown notification; proceeding to close.")
        # Call the parent close
        await super().close()
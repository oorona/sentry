# bot.py
import discord
from discord.ext import commands
import logging
import os
import json
import asyncio
from utils.database import init_db
from utils.health import start_health_server

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

        super().__init__(command_prefix='!', intents=intents)

        init_db()
        self.load_cogs()

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                logging.info("Loading config.json")
                return json.load(f)
        except FileNotFoundError:
            logging.error("config.json not found. Please create it.")
            return None
        except json.JSONDecodeError:
            logging.error("config.json is not a valid JSON file. Please check its syntax.")
            return None

    def load_cogs(self):
        """Finds all python files in the 'cogs' directory and loads them."""
        # --- UPDATED PATHS ---
        cogs_physical_path = "cogs" # cogs directory is now directly in /app
        cogs_import_path_prefix = "cogs" # For import, it's just 'cogs'

        for filename in os.listdir(cogs_physical_path):
            if filename.endswith(".py") and not filename.startswith("__"):
                try:
                    self.load_extension(f'{cogs_import_path_prefix}.{filename[:-3]}')
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
        # Sync app commands (slash commands) to ensure they register with Discord.
        # If a development guild is configured (`dev_guild_id` in config or DEV_GUILD_ID env),
        # sync there first for immediate availability, then perform global sync once.
        if not getattr(self, "_commands_synced", False):
            try:
                dev_guild = None
                if self.config.get("dev_guild_id"):
                    try:
                        dev_guild = int(self.config.get("dev_guild_id"))
                    except Exception:
                        logging.warning("Invalid dev_guild_id in config.json; skipping guild sync.")
                elif os.getenv("DEV_GUILD_ID"):
                    try:
                        dev_guild = int(os.getenv("DEV_GUILD_ID"))
                    except Exception:
                        logging.warning("Invalid DEV_GUILD_ID env var; skipping guild sync.")

                if dev_guild:
                    guild_obj = discord.Object(id=dev_guild)
                    await self.tree.sync(guild=guild_obj)
                    logging.info(f"Application commands synced to dev guild {dev_guild}.")

                await self.tree.sync()
                logging.info("Application commands globally synced.")
                self._commands_synced = True
            except Exception as e:
                logging.warning(f"Failed to sync application commands: {e}")
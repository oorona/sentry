from discord.ext import commands
import discord
from discord import app_commands
import logging
logger = logging.getLogger(__name__)
import aiohttp
import importlib


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_authorized(self, member: discord.Member) -> bool:
        """Authorize by role IDs (config: admin_role_ids). Role IDs are strings in config.json."""
        # config now contains integers (validated at bot startup)
        allowed_ids = set(self.bot.config.get("admin_role_ids", []))
        # If explicit admin role IDs are configured, require those roles
        if allowed_ids:
            member_role_ids = set(r.id for r in member.roles)
            return not allowed_ids.isdisjoint(member_role_ids)

        # No explicit admin roles configured: allow guild administrators or the bot owner
        try:
            if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
                return True
        except Exception:
            pass

        # Fall back to bot owner check (if available)
        try:
            app_owner = getattr(self.bot, 'owner_id', None) or getattr(self.bot, 'application_id', None)
            if app_owner and int(app_owner) == int(member.id):
                return True
        except Exception:
            pass

        return False

    async def _check_db(self):
        """Attempt a lightweight DB check if an engine is available.

        Tries the following (in order):
        - `self.bot.db_engine` attribute
        - `utils.database.engine` module attribute (if available)

        If no engine is available the function returns (None, 'no-engine').
        """
        engine = getattr(self.bot, 'db_engine', None)
        text_fn = None
        if engine is None:
            # try lazy import of utils.database if present in a host project
            try:
                ud = importlib.import_module('utils.database')
                engine = getattr(ud, 'engine', None)
            except Exception:
                engine = None

        if engine is None:
            return None, 'no-engine'

        # try importing sqlalchemy.text lazily
        try:
            sqlalchemy = importlib.import_module('sqlalchemy')
            text_fn = getattr(sqlalchemy, 'text', None)
        except Exception:
            text_fn = None

        try:
            if text_fn:
                with engine.connect() as conn:
                    conn.execute(text_fn('SELECT 1'))
            else:
                # best-effort: try a simple connect/close
                with engine.connect() as conn:
                    pass
            return True, None
        except Exception as e:
            return False, str(e)

    @app_commands.command(name="status", description="Show service status (HTTP + DB)")
    async def status(self, interaction: discord.Interaction):
        """Status slash command restricted to configured admin roles."""
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Command must be used in a guild by a member.", ephemeral=True)
            return

        if not self._is_authorized(member):
            await interaction.response.send_message("You are not authorized to run this command.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        # Check HTTP health endpoint first (internal network)
        host = self.bot.config.get("health_host", "127.0.0.1")
        port = self.bot.config.get("health_port", 8080)
        url = f"http://{host}:{port}/health"
        http_status = "unknown"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    http_status = f"{resp.status} {await resp.text()}"
        except Exception as e:
            http_status = f"error: {e}"

        db_ok, db_err = await self.bot.loop.run_in_executor(None, self._check_db)

        embed = discord.Embed(title="Sentry Status", color=discord.Color.blue())
        embed.add_field(name="HTTP /health", value=http_status, inline=False)
        embed.add_field(name="Database", value=("ok" if db_ok else f"error: {db_err}"), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ready", description="Notify the configured log channel that the bot is ready")
    async def ready(self, interaction: discord.Interaction):
        # Slash command implemented using discord.py's app_commands
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Command must be used in a guild by a member.", ephemeral=True)
            return

        if not self._is_authorized(member):
            await interaction.response.send_message("You are not authorized to run this command.", ephemeral=True)
            return

        log_channel_id = self.bot.config.get("log_channel_id")
        if not log_channel_id:
            await interaction.response.send_message("Log channel is not configured.", ephemeral=True)
            return

        channel = self.bot.get_channel(log_channel_id)
        if not channel:
            await interaction.response.send_message("Could not find the configured log channel.", ephemeral=True)
            return

        try:
            await channel.send("Bot readiness notified by /ready command")
            await interaction.response.send_message("Notified log channel.", ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to notify log channel: {e}")
            await interaction.response.send_message(f"Failed to notify log channel: {e}", ephemeral=True)

    @app_commands.command(name="sync_commands", description="Force sync application (slash) commands")
    async def sync_commands(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Command must be used in a guild by a member.", ephemeral=True)
            return

        if not self._is_authorized(member):
            await interaction.response.send_message("You are not authorized to run this command.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            dev_guild = None
            if self.bot.config.get("guild_id"):
                try:
                    dev_guild = int(self.bot.config.get("guild_id"))
                except Exception:
                    dev_guild = None

            synced_info = []
            if dev_guild:
                guild_obj = discord.Object(id=dev_guild)
                guild_cmds = await self.bot.tree.sync(guild=guild_obj)
                synced_info.append(f"Guild {dev_guild}: {len(guild_cmds)} commands")

            global_cmds = await self.bot.tree.sync()
            synced_info.append(f"Global: {len(global_cmds)} commands")
            await interaction.followup.send("Sync complete.\n" + "\n".join(synced_info), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to sync commands: {e}", ephemeral=True)

    @app_commands.command(name="appcommands", description="List registered application (slash) commands the bot currently has")
    async def appcommands(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Command must be used in a guild by a member.", ephemeral=True)
            return

        if not self._is_authorized(member):
            await interaction.response.send_message("You are not authorized to run this command.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        cmds = []
        for cmd in self.bot.tree.walk_commands():
            try:
                cmds.append(f"{cmd.qualified_name} - {cmd.description}")
            except Exception:
                cmds.append(str(cmd))

        if not cmds:
            await interaction.followup.send("No application commands registered (or none cached).", ephemeral=True)
            return

        msg = "Registered application commands:\n" + "\n".join(cmds)
        # split if too long
        if len(msg) > 1900:
            chunks = [msg[i:i+1900] for i in range(0, len(msg), 1900)]
            for chunk in chunks:
                await interaction.followup.send(f"```\n{chunk}\n```", ephemeral=True)
        else:
            await interaction.followup.send(f"```\n{msg}\n```", ephemeral=True)

    @app_commands.command(name="diagnose", description="Show diagnostics: loaded cogs, app commands, guilds, event counters")
    async def diagnose(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Command must be used in a guild by a member.", ephemeral=True)
            return

        if not self._is_authorized(member):
            await interaction.response.send_message("You are not authorized to run this command.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        lines = []
        lines.append(f"Guilds: {len(self.bot.guilds)}")
        lines.append(f"Loaded cogs: {', '.join(list(self.bot.extensions.keys()))}")
        # Application information for debugging token/app mismatch
        try:
            lines.append(f"Application ID: {self.bot.application_id}")
        except Exception:
            lines.append("Application ID: unavailable")
        # App commands count
        try:
            cmds = list(self.bot.tree.walk_commands())
            lines.append(f"App commands (tree): {len(cmds)}")
        except Exception:
            lines.append("App commands: unavailable")

        # Event counters
        counters = getattr(self.bot, "_event_counters", {})
        for k, v in counters.items():
            lines.append(f"{k}: {v}")

        await interaction.followup.send("```\n" + "\n".join(lines) + "\n```", ephemeral=True)


    @app_commands.command(name="debug_sync", description="(debug) run sync steps and report detailed results")
    async def debug_sync(self, interaction: discord.Interaction):
        """Run a global sync, attempt copying global commands to the configured guild (if any), then sync the guild.

        Returns a short report (ephemeral) for debugging registration issues.
        """
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Command must be used in a guild by a member.", ephemeral=True)
            return

        if not self._is_authorized(member):
            await interaction.response.send_message("You are not authorized to run this command.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        results = []
        # Global sync
        try:
            global_cmds = await self.bot.tree.sync()
            results.append(f"Global sync: {len(global_cmds)} commands")
            results.append(f"Global names: {[c.name for c in global_cmds]}")
        except Exception as e:
            results.append(f"Global sync failed: {e}")

        # Copy to dev guild (if configured)
        dev_guild = None
        if self.bot.config.get("guild_id"):
            try:
                dev_guild = int(self.bot.config.get("guild_id"))
            except Exception:
                dev_guild = None

        if dev_guild:
            guild_obj = discord.Object(id=dev_guild)
            try:
                await self.bot.tree.copy_global_to(guild_obj)
                results.append(f"copy_global_to: attempted for guild {dev_guild}")
            except Exception as e:
                results.append(f"copy_global_to failed: {e}")

            try:
                guild_cmds = await self.bot.tree.sync(guild=guild_obj)
                results.append(f"Guild sync for {dev_guild}: {len(guild_cmds)} commands")
                results.append(f"Guild names: {[c.name for c in guild_cmds]}")
            except Exception as e:
                results.append(f"Guild sync failed: {e}")
        else:
            results.append("No guild_id configured; skipping guild copy/sync steps.")

        await interaction.followup.send("\n".join(results), ephemeral=True)


async def setup(bot):
    cog = AdminCog(bot)
    await bot.add_cog(cog)
    # Ensure the slash /ready command is registered on the application command tree.
    try:
        # Avoid duplicate registration
        existing = bot.tree.get_command("ready")
        if existing is None:
            async def _ready_wrapper(interaction: discord.Interaction):
                await cog.ready(interaction)

            cmd = app_commands.Command(_ready_wrapper, name="ready", description="Notify the configured log channel that the bot is ready")
            bot.tree.add_command(cmd)
            logging.info("Registered /ready app command to bot.tree")
        else:
            logging.debug("/ready command already present in bot.tree; skipping registration.")
    except Exception as e:
        logging.warning(f"Failed to register /ready app command: {e}")

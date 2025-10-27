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

    async def _send_notify_embed(self, embed: discord.Embed):
        """Send an embed to the configured notify channel (notify_channel_id) if available."""
        channel_id = self.bot.config.get("notify_channel_id") or self.bot.config.get("log_channel_id")
        if not channel_id:
            logger.debug("No notify_channel_id configured; skipping notify embed send.")
            return False
        try:
            chan_id = int(channel_id)
        except Exception:
            logger.warning(f"notify_channel_id is not an integer: {channel_id}")
            return False

        try:
            channel = self.bot.get_channel(chan_id)
            if channel is None:
                channel = await self.bot.fetch_channel(chan_id)
            if not channel:
                logger.warning(f"Could not find notify channel {chan_id}")
                return False
            await channel.send(embed=embed)
            return True
        except Exception as e:
            logger.exception(f"Failed to send notify embed to {chan_id}: {e}")
            return False

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
        embed.set_footer(text=f"Requested by {member}")

        await interaction.followup.send(embed=embed, ephemeral=True)
        # send notification embed to notify channel
        await self._send_notify_embed(embed)

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
            embed = discord.Embed(title="Sentry Bot - Manual Ready", color=discord.Color.green())
            embed.add_field(name="Action", value="Manual readiness notified", inline=False)
            embed.set_footer(text=f"Requested by {member}")
            await self._send_notify_embed(embed)
            await interaction.response.send_message("Notified notify channel.", ephemeral=True)
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
            embed = discord.Embed(title="Sentry Sync Results", color=discord.Color.blue())
            if dev_guild:
                guild_obj = discord.Object(id=dev_guild)
                guild_cmds = await self.bot.tree.sync(guild=guild_obj)
                synced_info.append(f"Guild {dev_guild}: {len(guild_cmds)} commands")
                embed.add_field(name=f"Guild {dev_guild}", value=str(len(guild_cmds)), inline=False)

            global_cmds = await self.bot.tree.sync()
            synced_info.append(f"Global: {len(global_cmds)} commands")
            embed.add_field(name="Global", value=str(len(global_cmds)), inline=False)
            embed.set_footer(text=f"Requested by {member}")

            await interaction.followup.send("Sync complete.", ephemeral=True)
            await self._send_notify_embed(embed)
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

        # Send ephemeral full list to invoker and a summary embed to notify channel
        msg = "Registered application commands:\n" + "\n".join(cmds)
        if len(msg) > 1900:
            await interaction.followup.send("Registered application commands too long to show; sent summary to notify channel.", ephemeral=True)
        else:
            await interaction.followup.send(f"```\n{msg}\n```", ephemeral=True)

        embed = discord.Embed(title="Registered Application Commands", color=discord.Color.blue())
        embed.add_field(name="Command count", value=str(len(cmds)), inline=False)
        sample = "\n".join(cmds[:10])
        embed.add_field(name="Sample", value=f"```\n{sample}\n```" if sample else "None", inline=False)
        embed.set_footer(text=f"Requested by {member}")
        await self._send_notify_embed(embed)

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

        # ephemeral to invoker
        await interaction.followup.send("```\n" + "\n".join(lines) + "\n```", ephemeral=True)
        # notify channel embed
        embed = discord.Embed(title="Sentry Diagnose", color=discord.Color.blue())
        for l in lines:
            if ":" in l:
                k, v = l.split(":", 1)
                embed.add_field(name=k.strip(), value=v.strip(), inline=False)
        embed.set_footer(text=f"Requested by {member}")
        await self._send_notify_embed(embed)


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

        # ephemeral reply
        await interaction.followup.send("\n".join(results), ephemeral=True)
        # send notification embed summarizing results
        embed = discord.Embed(title="Debug Sync Results", color=discord.Color.blue())
        embed.add_field(name="Summary", value="; ".join(results[:10]), inline=False)
        embed.set_footer(text=f"Requested by {member}")
        await self._send_notify_embed(embed)


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

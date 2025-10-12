from discord.ext import commands
import discord
from discord import app_commands
import logging
import aiohttp
from utils.database import engine
from sqlalchemy import text


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_authorized(self, member: discord.Member) -> bool:
        """Authorize by role IDs (config: admin_role_ids). Role IDs are strings in config.json."""
        # config now contains integers (validated at bot startup)
        allowed_ids = set(self.bot.config.get("admin_role_ids", []))
        member_role_ids = set(r.id for r in member.roles)
        return not allowed_ids.isdisjoint(member_role_ids)

    async def _check_db(self):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True, None
        except Exception as e:
            return False, str(e)

    @commands.command(name="status")
    async def status(self, ctx: commands.Context):
        """Status command restricted to roles listed in config.json -> admin_role_ids"""
        if not isinstance(ctx.author, discord.Member):
            await ctx.send("Command must be used in a guild by a member.")
            return

        if not self._is_authorized(ctx.author):
            await ctx.send("You are not authorized to run this command.")
            return

        # Check HTTP health endpoint first (internal network)
        host = ctx.bot.config.get("health_host", "127.0.0.1")
        port = ctx.bot.config.get("health_port", 8080)
        url = f"http://{host}:{port}/health"
        http_status = "unknown"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    http_status = f"{resp.status} {await resp.text()}"
        except Exception as e:
            http_status = f"error: {e}"

        db_ok, db_err = await ctx.bot.loop.run_in_executor(None, self._check_db)

        embed = discord.Embed(title="Sentry Status", color=discord.Color.blue())
        embed.add_field(name="HTTP /health", value=http_status, inline=False)
        embed.add_field(name="Database", value=("ok" if db_ok else f"error: {db_err}"), inline=False)

        await ctx.send(embed=embed)

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


def setup(bot):
    bot.add_cog(AdminCog(bot))

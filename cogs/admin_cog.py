from discord.ext import commands
import discord
from discord import app_commands
import logging
logger = logging.getLogger(__name__)
import aiohttp
import importlib
from datetime import datetime


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

    @app_commands.command(name="status", description="Show comprehensive service status (System + DB + Health)")
    async def status(self, interaction: discord.Interaction):
        """Enhanced status slash command with comprehensive system information."""
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Command must be used in a guild by a member.", ephemeral=True)
            return

        if not self._is_authorized(member):
            await interaction.response.send_message("You are not authorized to run this command.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            # Use the bot's comprehensive status embed
            embed = await self.bot._build_status_embed(
                title="Sentry Bot Status", 
                event="Status Check", 
                extra={
                    "Solicitado por": str(member),
                    "Tipo de consulta": "Manual"
                }
            )
            
            # Send response to user
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Also send notification to the notification channel
            await self._send_notify_embed(embed)
            
        except Exception as e:
            logger.error(f"Failed to generate status embed: {e}")
            # Fallback to basic status if enhanced embed fails
            embed = discord.Embed(title="Sentry Status (Basic)", color=discord.Color.yellow())
            embed.add_field(name="Error", value=f"Failed to generate full status: {e}", inline=False)
            embed.add_field(name="Bot Status", value="Online", inline=True)
            embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
            embed.set_footer(text=f"Requested by {member}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            await self._send_notify_embed(embed)

    @app_commands.command(name="health", description="Check detailed health status including HTTP endpoints")
    async def health(self, interaction: discord.Interaction):
        """Check comprehensive health status including HTTP health endpoints."""
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Command must be used in a guild by a member.", ephemeral=True)
            return

        if not self._is_authorized(member):
            await interaction.response.send_message("You are not authorized to run this command.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        # Check all health endpoints
        host = self.bot.config.get("health_host", "127.0.0.1")
        port = self.bot.config.get("health_port", 8080)
        
        endpoints = {
            "General Health": f"http://{host}:{port}/health",
            "Readiness": f"http://{host}:{port}/health/ready", 
            "Liveness": f"http://{host}:{port}/health/live"
        }
        
        embed = discord.Embed(
            title="🏥 Sentry Health Check", 
            description="Comprehensive health status check",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        all_healthy = True
        
        for endpoint_name, url in endpoints.items():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            status_emoji = "✅"
                            status_text = f"**Status:** {data.get('status', 'ok')}"
                            
                            # Add extra details for comprehensive health check
                            if endpoint_name == "General Health" and 'database' in data:
                                db_info = data['database']
                                system_info = data.get('system', {})
                                status_text += f"\n**DB:** {db_info.get('status', 'unknown')}"
                                status_text += f"\n**Events:** {db_info.get('event_count', 0):,}"
                                status_text += f"\n**Memory:** {system_info.get('memory_mb', 0):.1f} MB"
                                status_text += f"\n**CPU:** {system_info.get('cpu_percent', 0):.1f}%"
                            elif 'uptime_seconds' in data:
                                uptime = data['uptime_seconds']
                                if uptime < 60:
                                    uptime_str = f"{uptime}s"
                                elif uptime < 3600:
                                    uptime_str = f"{uptime//60}m {uptime%60}s"
                                else:
                                    hours = uptime // 3600
                                    minutes = (uptime % 3600) // 60
                                    uptime_str = f"{hours}h {minutes}m"
                                status_text += f"\n**Uptime:** {uptime_str}"
                        else:
                            status_emoji = "❌"
                            status_text = f"**Status:** HTTP {resp.status}"
                            all_healthy = False
                            
            except Exception as e:
                status_emoji = "🔥"
                status_text = f"**Error:** {str(e)[:100]}"
                all_healthy = False
            
            embed.add_field(
                name=f"{status_emoji} {endpoint_name}",
                value=status_text,
                inline=True
            )
        
        # Add overall status
        if all_healthy:
            embed.color = discord.Color.green()
            embed.add_field(
                name="🎯 Estado General", 
                value="**Todos los servicios están funcionando correctamente**",
                inline=False
            )
        else:
            embed.color = discord.Color.red()
            embed.add_field(
                name="⚠️ Estado General", 
                value="**Algunos servicios presentan problemas**",
                inline=False
            )
        
        embed.set_footer(text=f"Solicitado por {member}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        await self._send_notify_embed(embed)

    @app_commands.command(name="reload_config", description="Reload bot configuration from config.json")
    async def reload_config(self, interaction: discord.Interaction):
        """Reload bot configuration and notify about changes."""
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Command must be used in a guild by a member.", ephemeral=True)
            return

        if not self._is_authorized(member):
            await interaction.response.send_message("You are not authorized to run this command.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        
        try:
            # Store old config for comparison
            old_config = dict(self.bot.config)
            
            # Reload configuration
            new_config = self.bot.load_config()
            
            if new_config:
                self.bot.config = new_config
                
                # Compare configurations and build change summary
                changes = []
                
                # Check for changed settings
                for key in set(old_config.keys()) | set(new_config.keys()):
                    old_val = old_config.get(key)
                    new_val = new_config.get(key)
                    
                    if old_val != new_val:
                        if key == "events" and isinstance(old_val, dict) and isinstance(new_val, dict):
                            # Special handling for events dict
                            for event_key in set(old_val.keys()) | set(new_val.keys()):
                                old_event = old_val.get(event_key, False)
                                new_event = new_val.get(event_key, False)
                                if old_event != new_event:
                                    status = "✅ Activado" if new_event else "❌ Desactivado"
                                    changes.append(f"**{event_key}:** {status}")
                        else:
                            changes.append(f"**{key}:** {old_val} → {new_val}")
                
                # Create notification embed
                embed = discord.Embed(
                    title="🔄 Configuración Recargada",
                    description="La configuración del bot ha sido recargada exitosamente",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                
                if changes:
                    changes_text = "\n".join(changes[:10])  # Limit to first 10 changes
                    if len(changes) > 10:
                        changes_text += f"\n... y {len(changes) - 10} cambios más"
                    embed.add_field(
                        name="📝 Cambios Detectados",
                        value=changes_text,
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="ℹ️ Estado",
                        value="No se detectaron cambios en la configuración",
                        inline=False
                    )
                
                embed.add_field(
                    name="👤 Solicitado por",
                    value=str(member),
                    inline=True
                )
                
                embed.add_field(
                    name="⏰ Hora",
                    value=datetime.utcnow().strftime('%H:%M:%S UTC'),
                    inline=True
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                await self._send_notify_embed(embed)
                
                logger.info(f"Configuration reloaded by {member}, {len(changes)} changes detected")
                
            else:
                # Failed to reload
                embed = discord.Embed(
                    title="❌ Error de Configuración",
                    description="No se pudo recargar la configuración",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(
                    name="💡 Sugerencia",
                    value="Verifica que el archivo config.json tenga formato JSON válido",
                    inline=False
                )
                embed.set_footer(text=f"Solicitado por {member}")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                await self._send_notify_embed(embed)
                
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            
            embed = discord.Embed(
                title="🔥 Error Crítico",
                description=f"Error al recargar configuración: {str(e)[:200]}",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"Solicitado por {member}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
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

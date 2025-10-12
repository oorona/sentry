# src/cogs/logger_cog.py
from discord.ext import commands
import discord
import logging
from datetime import datetime
from utils.database import get_db_session, LogEntry 

class LoggerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log_channel = None

    @commands.Cog.listener()
    async def on_ready(self):
        """Fetches the log channel object once the bot is ready."""
        channel_id = self.bot.config.get("log_channel_id")
        if channel_id:
            self.log_channel = self.bot.get_channel(channel_id)
            if self.log_channel:
                logging.info(f"Log channel successfully found: #{self.log_channel.name}")
            else:
                logging.warning(f"Could not find log channel with ID: {channel_id}")
        else:
            logging.warning("log_channel_id is not set in config.json")

    async def _add_log(self, event_type: str, author: discord.User | discord.Member | None, description: str, guild: discord.Guild, details: dict = None, color: discord.Color = discord.Color.blue()):
        """Helper function to log an event to both the database and Discord channel."""
        # 1. Write to database
        db_session = get_db_session()
        try:
            new_log = LogEntry(
                event_type=event_type,
                author_id=str(author.id) if author else "0",
                author_name=str(author) if author else "System",
                description=description,
                guild_id=str(guild.id) if guild else "0",
                details=details
            )
            db_session.add(new_log)
            db_session.commit()
            logging.debug(f"Logged event '{event_type}' to DB.")
        except Exception as e:
            logging.error(f"Failed to write log to database: {e}", exc_info=True)
            db_session.rollback()
        finally:
            db_session.close()

        # 2. Send to Discord channel (if configured)
        if not self.log_channel:
            return

        embed = discord.Embed(
            description=description,
            color=color,
            timestamp=datetime.utcnow()
        )
        if author:
            embed.set_author(name=f"{author}", icon_url=author.display_avatar.url)
        else:
            embed.set_author(name=event_type.replace("_", " ").title())

        # Add details to embed if they exist
        if details:
            for key, value in details.items():
                if len(str(value)) > 1024:
                    value = str(value)[:1021] + "..."
                embed.add_field(name=key.replace("_", " ").title(), value=f"```{value}```" if value else "N/A", inline=False)

        try:
            await self.log_channel.send(embed=embed)
        except Exception as e:
            logging.error(f"An unexpected error occurred when sending Discord log for '{event_type}': {e}", exc_info=True)

    # --- Member Events ---

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not self.bot.config["events"].get("on_member_join"):
            return
        await self._add_log("member_join", member, f"{member.mention} joined the server.", member.guild, color=discord.Color.green())

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if not self.bot.config["events"].get("on_member_remove"):
            return
        await self._add_log("member_remove", member, f"{member.mention} left the server.", member.guild, color=discord.Color.orange())

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        if not self.bot.config["events"].get("on_member_ban"):
            return
        await self._add_log("member_ban", user, f"{user.mention} was banned.", guild, color=discord.Color.red())

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        if not self.bot.config["events"].get("on_member_unban"):
            return
        await self._add_log("member_unban", user, f"{user.mention} was unbanned.", guild, color=discord.Color.light_grey())

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if not self.bot.config["events"].get("on_member_update") or before.bot:
            return
        # Nickname change
        if before.nick != after.nick:
            await self._add_log("nickname_change", after, f"{after.mention}'s nickname was changed.", after.guild, details={"Before": before.nick or "None", "After": after.nick or "None"}, color=discord.Color.purple())
        # Role change
        if before.roles != after.roles:
            added_roles = [r.name for r in after.roles if r not in before.roles]
            removed_roles = [r.name for r in before.roles if r not in after.roles]
            if added_roles:
                await self._add_log("roles_added", after, f"Roles added to {after.mention}", after.guild, details={"Roles": ", ".join(added_roles)}, color=discord.Color.teal())
            if removed_roles:
                await self._add_log("roles_removed", after, f"Roles removed from {after.mention}", after.guild, details={"Roles": ", ".join(removed_roles)}, color=discord.Color.dark_teal())

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        if not self.bot.config["events"].get("on_user_update") or before.bot:
            return
        if before.name != after.name:
            details = {"Before": before.name, "After": after.name}
            for guild in self.bot.guilds:
                if guild.get_member(after.id):
                    await self._add_log("username_change", after, f"{after.mention}'s username was changed.", guild, details=details, color=discord.Color.purple())
        if before.avatar != after.avatar:
            details = {"Avatar URL": str(after.display_avatar.url)}
            for guild in self.bot.guilds:
                if guild.get_member(after.id):
                    await self._add_log("avatar_change", after, f"{after.mention}'s avatar was changed.", guild, details=details, color=discord.Color.purple())

    # --- Message Events ---

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not self.bot.config["events"].get("on_message_delete") or message.author.bot:
            return
        details = {"Content": message.content or "N/A", "Channel": message.channel.mention}
        await self._add_log("message_delete", message.author, f"A message was deleted.", message.guild, details=details, color=discord.Color.dark_red())

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not self.bot.config["events"].get("on_message_edit") or before.author.bot or before.content == after.content:
            return
        details = {"Before": before.content, "After": after.content, "Channel": before.channel.mention}
        await self._add_log("message_edit", before.author, f"A message was edited. [Jump to Message]({after.jump_url})", before.guild, details=details, color=discord.Color.greyple())

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if not self.bot.config["events"].get("on_bulk_message_delete"):
            return
        guild = messages[0].guild
        channel = messages[0].channel
        details = {"Count": len(messages), "Channel": channel.mention}
        await self._add_log("bulk_message_delete", None, f"{len(messages)} messages were deleted.", guild, details=details, color=discord.Color.darker_red())

    # --- Role & Channel Events ---

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        if not self.bot.config["events"].get("on_guild_role_create"):
            return
        # Include both mention and name so the Discord embed clearly references the role
        description = f"Role {role.mention} (`{role.name}`) was created."
        await self._add_log("role_create", None, description, role.guild, color=discord.Color.blue())

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        if not self.bot.config["events"].get("on_guild_role_delete"):
            return
        # Include both mention and name so the Discord embed clearly references the deleted role
        description = f"Role `{role.name}` was deleted. (Previously: {role.name})"
        # role.mention won't work for deleted role; include the name explicitly
        await self._add_log("role_delete", None, description, role.guild, color=discord.Color.dark_blue())

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if not self.bot.config["events"].get("on_guild_channel_create"):
            return
        await self._add_log("channel_create", None, f"Channel `{channel.name}` was created.", channel.guild, color=discord.Color.blue())

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not self.bot.config["events"].get("on_guild_channel_delete"):
            return
        await self._add_log("channel_delete", None, f"Channel `{channel.name}` was deleted.", channel.guild, color=discord.Color.dark_blue())

    # --- Voice Events ---

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not self.bot.config["events"].get("on_voice_state_update") or member.bot:
            return
        # Joined a channel
        if not before.channel and after.channel:
            await self._add_log("voice_join", member, f"{member.mention} joined voice channel `{after.channel.name}`.", member.guild, color=discord.Color.dark_green())
        # Left a channel
        elif before.channel and not after.channel:
            await self._add_log("voice_leave", member, f"{member.mention} left voice channel `{before.channel.name}`.", member.guild, color=discord.Color.dark_orange())
        # Moved channel
        elif before.channel and after.channel and before.channel != after.channel:
            details = {"From": before.channel.name, "To": after.channel.name}
            await self._add_log("voice_move", member, f"{member.mention} moved voice channels.", member.guild, details=details, color=discord.Color.dark_purple())


def setup(bot):
    bot.add_cog(LoggerCog(bot))
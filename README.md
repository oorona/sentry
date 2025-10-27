# Discord Logging Platform

![Sentry Bot Logo](https://img.imageforge.xyz/a5c90b8f-3315-460d-9b6e-4458f310b86a/abstract_simple_log_bot_logo.webp)

## Table of Contents
1.  [Project Overview](#10-project-overview)
2.  [Technical Specifications](#20-technical-specifications)
3.  [Setup and Deployment](#30-setup-and-deployment)
    * [3.1 Prerequisites](#31-prerequisites)
    * [3.2 Discord Bot Permissions & Intents](#32-discord-bot-permissions--intents)
    * [3.3 Project Structure](#33-project-structure)
    * [3.4 Configuration Files](#34-configuration-files)
    * [3.5 Running the Database Service](#35-running-the-database-service)
    * [3.6 Running the Discord Bot Service](#36-running-the-discord-bot-service)
4.  [Phased Implementation Guide](#40-phased-implementation-guide)
    * [Phase 1: The Core Bot & Console Logging](#phase-1-the-core-bot--console-logging)
    * [Phase 2: File-Based Configuration & Channel Logging](#phase-2-file-based-configuration--channel-logging)
    * [Phase 3: Add Database Persistence (PostgreSQL)](#phase-3-add-database-persistence-postgresql)
    * [Phase 4: Build the Web UI with Authentication](#phase-4-build-the-web-ui-with-authentication)
    * [Phase 5: Implement Advanced Features](#phase-5-implement-advanced-features)
    * [Phase 6: Final Polish](#phase-6-final-polish)

---

## 1.0 Project Overview

The Discord Logging Platform is a robust, configurable, and scalable solution for monitoring and logging events within a Discord server. It features a Python-based Discord bot that captures various server activities, a PostgreSQL database for persistent storage, and a secure web interface for viewing logs. The entire system is containerized using Docker for ease of deployment and management, offering a highly modular and maintainable architecture.

## 2.0 Technical Specifications

Refer to the `REQUIREMENTS.md` file in the project root for a detailed breakdown of all functional and non-functional requirements, as well as the complete technical stack.

## 3.0 Setup and Deployment

This section guides you through setting up and deploying the Discord Logging Platform. The project utilizes a decoupled architecture where the PostgreSQL database runs as a separate Docker Compose service from the bot.

### 3.1 Prerequisites

Before you begin, ensure you have the following installed:

* **Docker Desktop**: Includes Docker Engine and Docker Compose.
* **Python 3.10+** (for local development and managing dependencies, though Docker handles runtime)
* A **Discord Bot Token**: Obtained from the [Discord Developer Portal](https://discord.com/developers/applications).
* A **Discord Server** where you have administrator permissions to invite the bot and designate a logging channel.

### 3.2 Discord Bot Permissions & Intents

For the bot to function correctly and log all desired events, you need to configure its permissions and enable specific Gateway Intents in the Discord Developer Portal.

#### **3.2.1 Bot Permissions (When Inviting)**

When creating your bot's invitation link (in the Discord Developer Portal under `OAuth2` -> `URL Generator`), select the following permissions:

When generating the OAuth2 invite for the bot, choose a minimal set to operate and a few recommended permissions for full auditing and management features.

Required (minimum for core logging functionality):

- `View Channels` — allow the bot to see channels so it can post and monitor events.
- `Send Messages` — allow posting logs to the configured log/notify channel.
- `Embed Links` — required to send nicely formatted embed messages used for logs.
- `Read Message History` — helpful when showing message edit/delete context.

Recommended (enable these to get full audit and admin-context features):

- `View Audit Log` — required to resolve "who" performed administrative or moderation actions (role/channel changes, kicks, bans, member unbans, etc.). This permission is the single most important one for capturing actor information. If the bot lacks this, the bot can still detect that an action occurred but won't be able to reliably report which user performed it.
- `Manage Roles` — needed if the bot will itself modify roles or needs to fetch additional role metadata for reports; optional for read-only logging but useful when closely integrating with role workflows.
- `Manage Channels` — recommended when the bot is expected to manage or reliably observe channel lifecycle events. Not strictly required for read-only logging of channel deletions/creations, but helpful for automation.
- `Manage Webhooks` — useful if you plan to route logs via webhooks or create helper webhooks for cross-service integrations.
- `Kick Members`, `Ban Members` — note: these permissions are required for the bot to perform kicks/bans itself. They are NOT required for the bot to detect that a kick/ban occurred; detecting and reporting the actor who performed the kick/ban requires `View Audit Log`.
- `Mute Members`, `Deafen Members`, `Move Members` — required only if the bot will perform voice moderation actions; otherwise these are optional and primarily relevant if you want the bot to act rather than just observe voice-related changes.

In short: to capture "who" performed moderation actions, grant `View Audit Log`. Grant Kick/Ban/Mute/etc. only if you expect the bot to perform those actions itself.
You can select all (or a subset) depending on your deployment needs; enabling `View Audit Log` is highly recommended for richer logs.

[url](https://discord.com/oauth2/authorize?client_id=1423368489703440648&permissions=968977558&integration_type=0&scope=bot)

#### **3.2.2 Gateway Intents (Discord Developer Portal)**

On your bot's application page in the Discord Developer Portal (under `Bot` -> `Privileged Gateway Intents`), **enable the following three intents**:

* **`PRESENCE INTENT`**
* **`SERVER MEMBERS INTENT`**
* **`MESSAGE CONTENT INTENT`**

Additionally, ensure your bot's code (which uses `discord.Intents.default()`) implicitly includes the following non-privileged intents, which are also necessary:

* `GUILDS`
* `GUILD_MESSAGES`
* `GUILD_VOICE_STATES`

### 3.2.3 Application Commands (Slash Commands)

This bot uses Discord Application Commands (slash commands). These commands must be registered with Discord and can be registered either globally (available in all guilds after propagation delay) or per-guild (instant availability for a specific guild).

Key points:

- Scopes: When generating the OAuth2 invite URL, ensure `applications.commands` is included in the scopes so the application can register slash commands.
- Guild vs Global:
  - **Guild-scoped registration** (fast): Commands registered to a guild are available almost immediately (useful for development).
  - **Global registration** (slow): Global commands can take up to an hour to propagate but are available across all guilds.
- Env vars / config keys used by this project:
  - `GUILD_ID` / `guild_id` (config.json) — the development guild where commands can be registered quickly.
  - `DEV_GUILD_ONLY` — when truthy, the bot will attempt to register commands only in the provided dev guild for fast testing.
  - `EXPECTED_COMMAND_NAME` — optional override for expected command name used by the on_ready sync diagnostics (not generally required; the bot now detects missing local commands automatically).

Debugging tips:

- Look at the bot's `on_ready` logs. The bot logs pre-sync commands present in the tree, guild sync results, and global sync info. Example lines to watch for:
  - "Pre-sync commands present in tree: ..."
  - "Attempting to sync application commands to guild ..."
  - "Application commands synced to guild ... synced_count=..."
  - "Synced command names: ..."
  - "Guild-synced commands missing local commands: ...; attempting global sync as fallback."
- Use the admin slash command `/debug_sync` (available to configured admin roles) to run the same sync workflow on-demand and return a diagnostic summary. If `/debug_sync` reports no commands or empty lists, check the bot's cogs and ensure commands are defined and loaded before sync runs.
- If commands appear in global sync but not in guild sync, try `tree.copy_global_to(guild)` followed by a guild sync — the bot automatically attempts copy and will log the result.
- Permissions & application owner: Make sure you're using the correct bot token (OAuth2 application) and that the application registration in the Developer Portal matches the token being used by the running process. Token/app mismatches are a common cause of missing commands.

If you want, I can add a `/sync_status` command to the admin cog that returns the current command names in the tree and what the bot sees as registered; this can simplify debugging without reading logs.

### 3.3 Project Structure

The project is organized into two main Docker Compose services: `postgres_project` for the database and `discord-logger-bot` for the bot and web UI.
```
parent_directory
├── /postgres_project/
│   ├── .env                    # DB credentials (e.g., POSTGRES_USER, POSTGRES_PASSWORD)
│   └── docker-compose.yml      # Defines the PostgreSQL service
│
└── /discord-logger-bot/        # This project's root
├── .env                    # Bot token, DB connection string, UI credentials
├── config.json             # Bot's dynamic configuration (events, log channel, purge settings)
├── docker-compose.yml      # Defines the bot/web UI service
├── Dockerfile              # Builds the bot/web UI image
├── requirements.txt        # Python dependencies
├── main.py                 # Bot's entry point
├── bot.py                  # Core Discord bot logic
├── cogs/                   # Directory for bot's feature modules (cogs)
│   ├── init.py
│   └── logger_cog.py       # All event logging logic
├── util/                   # Utility functions and database models
│   ├── init.py
│   └── database.py         # SQLAlchemy ORM setup and LogEntry model
├── web_ui/                 # (Future Phase 4) Flask web application for log viewing
│   ├── init.py
│   ├── app.py
│   └── templates/
│       └── index.html
└── README.md
└── REQUIREMENTS.md
```
### 3.4 Configuration Files

#### `discord-logger-bot/.env`

Create this file in the root of your `discord-logger-bot` directory.
**Remember to replace placeholders with your actual values.**

```ini
# .env
# --- Discord Bot Token ---
DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN_GOES_HERE

# --- PostgreSQL Connection Details (MUST MATCH postgres_project/.env) ---
POSTGRES_DB=discord_logger_db
POSTGRES_USER=logger_user
POSTGRES_PASSWORD=your_strong_db_password

# --- Web UI Credentials (Phase 4) ---
WEB_UI_USER=admin
WEB_UI_PASSWORD=secure_admin_password
FLASK_SECRET_KEY=a_very_secret_key_for_flask_sessions
```
#### discord-logger-bot/config.json

Create this file in the root of your discord-logger-bot directory.
Replace 1234567890123456789 with your desired Discord log channel ID.

```
{
  "log_channel_id": 1234567890123456789,
  "events": {
    "// --- Member Events ---": "--------------------",
    "on_member_join": true,
    "on_member_remove": true,
    "on_member_update": true,
    "on_user_update": true,
    "on_member_ban": true,
    "on_member_unban": true,

    "// --- Message Events ---": "--------------------",
    "on_message_edit": true,
    "on_message_delete": true,
    "on_bulk_message_delete": true,

    "// --- Role Events ---": "--------------------",
    "on_guild_role_create": true,
    "on_guild_role_delete": true,
    "on_guild_role_update": true,

    "// --- Channel Events ---": "--------------------",
    "on_guild_channel_create": true,
    "on_guild_channel_delete": true,
    "on_guild_channel_update": true,

    "// --- Voice Channel Events ---": "--------------------",
    "on_voice_state_update": true
  },
  "purge_logs_after_days": 30
}
```
#### postgres_project/.env

Create this file in the root of your postgres_project directory.
Remember to replace placeholders with strong, unique values.

```
# postgres_project/.env
POSTGRES_DB=discord_logger_db
POSTGRES_USER=logger_user
POSTGRES_PASSWORD=your_strong_db_password
```

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

* **General Permissions:**
    * `View Channels`
    * `Send Messages`
    * `Embed Links` (Essential for formatted log messages)
    * `Read Message History`
    * `View Audit Log` (Highly recommended for detailed administrative action logs)
* **Membership Permissions:**
    * `Kick Members`
    * `Ban Members`
    * `Manage Nicknames`
* **Text Channel Permissions:**
    * `Manage Channels`
    * `Manage Webhooks`
* **Role Permissions:**
    * `Manage Roles`
* **Voice Channel Permissions:**
    * `Mute Members`
    * `Deafen Members`
    * `Move Members`

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

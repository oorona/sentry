# Discord Logging Platform (Sentry Bot)

![Sentry Bot Logo](https://img.imageforge.xyz/a5c90b8f-3315-460d-9b6e-4458f310b86a/abstract_simple_log_bot_logo.webp)

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Features](#2-features)
3. [Architecture](#3-architecture)
4. [Setup and Deployment](#4-setup-and-deployment)
5. [Configuration](#5-configuration)
6. [Discord Bot Setup](#6-discord-bot-setup)
7. [Admin Commands](#7-admin-commands)
8. [Health Monitoring](#8-health-monitoring)
9. [Notifications System](#9-notifications-system)
10. [Development](#10-development)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Project Overview

The Discord Logging Platform is a robust, containerized Discord bot that captures server events (joins, bans, message edits, etc.) and logs them to both Discord channels and a PostgreSQL database. The system features comprehensive health monitoring, real-time notifications, and admin management commands.

### Key Features
- **Event Logging**: Captures all Discord server events with audit log integration
- **Database Persistence**: PostgreSQL storage with flexible JSONB schema
- **Rich Notifications**: Spanish-localized startup/shutdown notifications with system stats
- **Health Monitoring**: Multiple health endpoints for Docker and Kubernetes integration
- **Admin Commands**: Comprehensive status, health checks, and configuration management
- **Docker Integration**: Full containerization with health checks and automatic restarts

---

## 2. Features

### 🔍 Event Monitoring
- Member events (joins, leaves, bans, unbans, updates)
- Message events (edits, deletes, bulk deletes)
- Role and channel management events
- Voice state changes
- Audit log integration for identifying event actors

### 📊 System Monitoring
- **Real-time metrics**: CPU usage, memory usage, uptime
- **Database monitoring**: Connection status, response times, event counts
- **Discord metrics**: Latency, guild/user counts, command sync status
- **Health endpoints**: `/health`, `/health/ready`, `/health/live`

### 🎛️ Admin Controls
- `/status` - Comprehensive system status
- `/health` - Detailed health endpoint testing
- `/reload_config` - Live configuration reload with change detection
- `/debug_sync` - Command synchronization diagnostics

### 🔔 Smart Notifications
- **Startup notifications**: System info, database status, process details
- **Shutdown notifications**: Graceful shutdown with resource cleanup info
- **Event notifications**: Rich embeds for all Discord events
- **Admin notifications**: Status updates and configuration changes

---

## 3. Architecture

### Component Overview
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Discord Bot   │◄──►│   PostgreSQL     │◄──►│  Health Server  │
│   (Sentry)      │    │   Database       │    │   (Port 8080)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │  Docker Network │
                    │     (dbnet)     │
                    └─────────────────┘
```

### Key Patterns
- **Dual Configuration**: Environment variables override `config.json`
- **Cog-Based Architecture**: Modular event handling via Discord.py cogs
- **Secret Management**: Docker secrets, file-based, and environment variable support
- **Health-First Design**: Multiple health endpoints for different use cases

---

## 4. Setup and Deployment

### 4.1 Prerequisites
- **Docker Desktop** with Docker Compose
- **Discord Bot Token** from [Discord Developer Portal](https://discord.com/developers/applications)
- **Discord Server** with administrator permissions

### 4.2 Quick Start

1. **Clone and setup:**
   ```bash
   git clone <repository-url>
   cd sentry
   ```

2. **Configure secrets:**
   ```bash
   mkdir -p secrets
   echo "YOUR_DISCORD_BOT_TOKEN" > secrets/discord_token.txt
   echo "your_strong_db_password" > secrets/postgres_password.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your channel IDs and settings
   ```

4. **Configure events:**
   ```bash
   # Edit config.json to enable/disable specific events
   ```

5. **Deploy:**
   ```bash
   # Start database (separate project)
   cd ../postgres_project && docker-compose up -d
   
   # Start bot
   cd ../sentry && docker-compose up -d
   ```

### 4.3 Project Structure
```
sentry/
├── main.py                 # Entry point with signal handling
├── bot.py                  # Core Discord bot logic
├── docker-compose.yml      # Bot service definition
├── Dockerfile              # Container build instructions
├── requirements.txt        # Python dependencies
├── .env                    # Environment configuration
├── config.json            # Event toggles and channel IDs
├── cogs/
│   ├── admin_cog.py       # Admin commands
│   └── logger_cog.py      # Event capture and logging
├── utils/
│   ├── database.py        # Database models and connections
│   └── health.py          # Health check endpoints
└── secrets/
    ├── discord_token.txt  # Discord bot token
    └── postgres_password.txt # Database password
```

---

## 5. Configuration

### 5.1 Environment Variables (.env)
```env
# Database Connection
POSTGRES_DB=discord
POSTGRES_USER=discord
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Discord Settings
GUILD_ID=1234567890123456789  # Development guild for fast command registration

# Notification Channels
LOG_CHANNEL_ID=1234567890123456789      # Event logging
NOTIFY_CHANNEL_ID=9876543210987654321   # Admin notifications
ADMIN_ROLE_IDS=111111111,222222222      # Admin role IDs (comma-separated)

# Events (comma-separated list)
EVENTS=on_member_join,on_message_edit,on_message_delete

# Logging
LOG_LEVEL=INFO
LOG_JSON=false
```

### 5.2 Event Configuration (config.json)
```json
{
  "log_channel_id": 1234567890123456789,
  "notify_channel_id": 9876543210987654321,
  "admin_role_ids": [111111111, 222222222],
  "events": {
    "on_member_join": true,
    "on_member_remove": true,
    "on_member_update": true,
    "on_message_edit": true,
    "on_message_delete": true,
    "on_bulk_message_delete": true,
    "on_guild_role_create": true,
    "on_guild_role_delete": true,
    "on_guild_role_update": true,
    "on_guild_channel_create": true,
    "on_guild_channel_delete": true,
    "on_guild_channel_update": true,
    "on_voice_state_update": true
  },
  "purge_logs_after_days": 30,
  "health_host": "0.0.0.0",
  "health_port": 8080
}
```

---

## 6. Discord Bot Setup

### 6.1 Required Permissions
When inviting the bot, ensure these permissions:

**Essential:**
- View Channels
- Send Messages
- Embed Links
- Read Message History

**Recommended:**
- View Audit Log (for identifying event actors)
- Manage Roles (for role-related events)
- Manage Channels (for channel events)

### 6.2 Required Intents
Enable in Discord Developer Portal:
- **Presence Intent**
- **Server Members Intent**
- **Message Content Intent**

### 6.3 Application Commands
Include `applications.commands` scope when generating OAuth2 invite URL.

**Invite URL Generator:**
```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=968977558&integration_type=0&scope=bot+applications.commands
```

---

## 7. Admin Commands

All admin commands require proper role authorization and send results as embeds to notification channels.

### 7.1 Status Commands
```
/status                    # Comprehensive system status with metrics
/health                   # Detailed health endpoint testing
```

**Example Status Output:**
```
🟢 Sentry Bot Status
El bot está ejecutando correctamente...

📊 Estadísticas de Sesión
Tiempo Activo: 2h 15m
Servidores: 1
Usuarios: 359

🗄️ Base de Datos
Estado: Conectado
Eventos: 1,234
Sesión: 45

💻 Sistema
Discord.py: 2.3.2
Latencia: 45 ms
CPU: 2.1%
Memoria: 48.3 MB

🚀 Proceso de Inicio
Servidor de Salud: Ejecutándose (:8080)
Cogs: 2 cargados
Comandos: Sincronizados
```

### 7.2 Management Commands
```
/reload_config            # Reload configuration with change detection
/debug_sync              # Command synchronization diagnostics
```

### 7.3 Authorization
Admin access is granted to users with:
1. Configured admin role IDs (`admin_role_ids`)
2. Guild administrator permissions
3. Bot owner (fallback)

---

## 8. Health Monitoring

### 8.1 Health Endpoints

**Comprehensive Health (`/health`):**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-26T15:30:00Z",
  "database": {
    "status": "connected",
    "response_time_ms": 45.2,
    "event_count": 1234
  },
  "system": {
    "cpu_percent": 2.1,
    "memory_mb": 48.3,
    "pid": 1234,
    "threads": 5,
    "uptime_seconds": 3600
  },
  "service": {
    "name": "sentry-discord-bot",
    "version": "1.0.0"
  }
}
```

**Readiness Probe (`/health/ready`):**
- Returns 200 if database is accessible
- Returns 503 if database is unavailable
- Used by Docker health checks

**Liveness Probe (`/health/live`):**
- Always returns 200 if service is running
- Used for container orchestration

### 8.2 Docker Health Integration
```yaml
# Built into docker-compose.yml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/health/ready"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

**Monitor container health:**
```bash
docker ps                                        # See health status
docker inspect sentry --format='{{.State.Health}}'  # Detailed info
```

---

## 9. Notifications System

### 9.1 Startup Notifications
Automatically sent when bot comes online:
```
🟢 Sentry Bot
¡El bot se ha iniciado correctamente y está listo para servir!

[Comprehensive system statistics...]
```

### 9.2 Shutdown Notifications
Sent during graceful shutdown:
```
🔴 Sentry Bot
El bot se está apagando correctamente... (Señal recibida)

[Final system statistics and cleanup info...]
```

### 9.3 Event Notifications
All Discord events logged as rich embeds with:
- Event details and context
- Actor identification (via audit logs)
- Timestamp and metadata
- Before/after states for changes

### 9.4 Channel Routing
- **Event logs**: Sent to `log_channel_id`
- **Admin notifications**: Sent to `notify_channel_id`
- **Fallback**: Uses `log_channel_id` if `notify_channel_id` not set

---

## 10. Development

### 10.1 Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set development environment
export DEV_GUILD_ONLY=true
export GUILD_ID=your_dev_guild_id

# Run locally
python main.py
```

### 10.2 Configuration Precedence
1. Environment variables (highest priority)
2. File paths from `*_FILE` environment variables
3. Docker secrets at `/run/secrets/`
4. config.json values (lowest priority)

### 10.3 Database Migrations
- No formal migration system
- Schema changes require container restart
- Update `LogEntry` model in `utils/database.py`

---

## 11. Troubleshooting

### 11.1 Startup Issues

**🔐 Discord Authentication Errors (401 Unauthorized)**
```
discord.errors.LoginFailure: Improper token has been passed.
```

**Causes & Solutions:**
1. **Invalid Discord Token:**
   ```bash
   # Check your Discord token file
   cat secrets/discord_token.txt
   
   # Ensure no extra whitespace or newlines
   echo -n "YOUR_ACTUAL_BOT_TOKEN" > secrets/discord_token.txt
   ```

2. **Token File Permissions:**
   ```bash
   # Fix file permissions
   chmod 600 secrets/discord_token.txt
   
   # Verify Docker can read the file
   docker exec sentry cat /run/secrets/discord_token
   ```

3. **Get New Token:**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Select your application → Bot → Reset Token
   - Copy the new token immediately (it won't be shown again)
   - Update `secrets/discord_token.txt`

**🗄️ Database Connection Errors**
```
psycopg2.OperationalError: password authentication failed for user "discord"
```

**Causes & Solutions:**
1. **Password Mismatch:**
   ```bash
   # Check bot's database password
   cat secrets/postgres_password.txt
   
   # Check database container's password
   cd ../postgres_project
   cat .env | grep POSTGRES_PASSWORD
   
   # Ensure they match exactly
   ```

2. **Database Not Running:**
   ```bash
   # Start database first
   cd ../postgres_project
   docker-compose up -d
   
   # Verify database is running
   docker ps | grep postgres
   
   # Check database logs
   docker logs postgres-db
   ```

3. **Network Issues:**
   ```bash
   # Verify Docker network exists
   docker network ls | grep dbnet
   
   # Create network if missing
   docker network create dbnet
   
   # Verify containers are on same network
   docker network inspect dbnet
   ```

4. **Database User Setup:**
   ```bash
   # Connect to database and verify user
   docker exec -it postgres-db psql -U postgres
   
   # Inside PostgreSQL:
   \du                          # List users
   SELECT current_database();   # Check database name
   
   # Create user if missing:
   CREATE USER discord WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE discord TO discord;
   ```

**📁 File Permission Issues**
```bash
# Fix all secret file permissions
chmod 600 secrets/*

# Verify Docker secrets are mounted
docker exec sentry ls -la /run/secrets/
```

### 11.2 Runtime Issues

**Commands not appearing:**
```bash
# Check command sync logs
docker logs sentry | grep -i sync

# Use debug command in Discord
/debug_sync
```

**Bot not responding to events:**
```bash
# Check Discord intents in Developer Portal
# Ensure these are enabled:
# - Server Members Intent
# - Message Content Intent  
# - Presence Intent

# Verify bot permissions in your Discord server
# Right-click bot → Manage → Permissions
```

**Health check failing:**
```bash
# Test health endpoints manually
docker exec sentry curl -f http://localhost:8080/health

# Check health server logs
docker logs sentry | grep health

# Verify health server is running
docker exec sentry netstat -ln | grep 8080
```

### 11.3 Configuration Issues

**Channel ID errors:**
```bash
# Get channel ID from Discord
# Right-click channel → Copy Channel ID
# (Enable Developer Mode in Discord settings first)

# Verify channel IDs in configuration
cat config.json | grep channel_id
```

**Environment variable issues:**
```bash
# Check loaded environment
docker exec sentry env | grep -E "(DISCORD|POSTGRES|NOTIFY|LOG)"

# Verify .env file format (no spaces around =)
cat .env
```

### 11.4 Step-by-Step Debugging

**Complete startup troubleshooting:**
```bash
# 1. Verify all files exist
ls -la secrets/discord_token.txt secrets/postgres_password.txt
ls -la .env config.json

# 2. Check database is running
cd ../postgres_project && docker-compose ps

# 3. Check network exists
docker network ls | grep dbnet

# 4. Start bot with verbose logging
export LOG_LEVEL=DEBUG
docker-compose up

# 5. Monitor logs in real-time
docker logs -f sentry
```

**Database connection test:**
```bash
# Test database connection manually
docker run --rm --network dbnet postgres:13 \
  psql -h postgres-db -U discord -d discord -c "SELECT 1;"
```

**Discord token validation:**
```bash
# Test token with curl (replace TOKEN with your actual token)
curl -H "Authorization: Bot YOUR_TOKEN" \
  https://discord.com/api/v10/users/@me
```

### 11.5 Log Analysis

### 11.5 Log Analysis
```bash
# Real-time logs with timestamps
docker logs -f --timestamps sentry

# Filter by log level
docker logs sentry 2>&1 | grep ERROR
docker logs sentry 2>&1 | grep WARNING

# Search for specific issues
docker logs sentry 2>&1 | grep -i "authentication"
docker logs sentry 2>&1 | grep -i "unauthorized"
docker logs sentry 2>&1 | grep -i "connection"

# Health check specific logs
docker logs sentry 2>&1 | grep health

# Discord API specific logs
docker logs sentry 2>&1 | grep discord
```

### 11.6 Quick Fix Checklist

**Before opening an issue, verify:**
- [ ] Discord token is valid and correctly formatted
- [ ] Database passwords match between bot and database
- [ ] PostgreSQL container is running
- [ ] Docker network `dbnet` exists
- [ ] Channel IDs are correct and bot has access
- [ ] Discord intents are enabled in Developer Portal
- [ ] Bot has required permissions in Discord server
- [ ] File permissions on secrets are correct (600)
- [ ] No extra whitespace in secret files

### 11.7 Getting Help

**Diagnostic Information to Include:**
```bash
# System info
docker --version
docker-compose --version

# Container status
docker ps -a

# Network configuration
docker network inspect dbnet

# Environment check (remove sensitive values)
docker exec sentry env | grep -v TOKEN | grep -v PASSWORD

# Recent logs
docker logs --tail 50 sentry
```

**Common Error Patterns:**
- `401 Unauthorized` → Discord token issue
- `password authentication failed` → Database password mismatch
- `connection refused` → Service not running or network issue
- `channel not found` → Invalid channel ID or missing permissions
- `403 Forbidden` → Missing Discord permissions

---

## Support and Contributing

For issues, feature requests, or contributions, please refer to the project repository. The bot includes comprehensive logging and diagnostic commands to help troubleshoot any issues.

**Key Diagnostic Commands:**
- `/status` - System overview
- `/health` - Health check details  
- `/debug_sync` - Command sync diagnostics
- Health endpoints at `:8080/health/*`

**Quick Start Verification:**
1. Database running: `docker ps | grep postgres`
2. Network exists: `docker network ls | grep dbnet`  
3. Secrets valid: `ls -la secrets/`
4. Bot starting: `docker logs sentry`

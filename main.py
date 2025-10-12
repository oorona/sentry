# src/main.py
import os
import logging
import bot
from dotenv import load_dotenv
def get_secret(name, file_var):
    if value := os.getenv(name):
        return value
    if file_path := os.getenv(file_var):
        with open(file_path) as f:
            return f.read().strip()
    raise RuntimeError(f"{name} not found")


def main():
    # --- Setup Basic Logging ---
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # --- Load Environment Variables ---
    load_dotenv()
    token = get_secret("DISCORD_TOKEN", "DISCORD_TOKEN_FILE")


    if not token:
        logging.error("DISCORD_TOKEN not found in .env file. Please set it.")
        return

    # --- Run the Bot ---
    client = bot.LoggingBot()
    client.run(token)

if __name__ == "__main__":
    main()
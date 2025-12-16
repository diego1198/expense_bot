"""
Main entry point for the expense tracking bot.
"""

import asyncio
import logging
import sys

from src.config import config
from src.database.connection import init_db, close_db
from src.bot.handlers import create_application


# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Reduce noise from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def post_init(application) -> None:
    """Initialize database after application starts."""
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully.")


async def post_shutdown(application) -> None:
    """Cleanup on shutdown."""
    logger.info("Closing database connections...")
    await close_db()
    logger.info("Shutdown complete.")


def main() -> None:
    """Main function to run the bot."""
    
    # Validate configuration
    missing = config.validate()
    if missing:
        logger.error(f"❌ Missing required configuration: {', '.join(missing)}")
        logger.error("Please set the required environment variables in .env file")
        sys.exit(1)
    
    logger.info("🤖 Starting Expense Tracking Bot...")
    logger.info(f"📂 Data directory: {config.DATA_DIR}")
    
    # Ensure data directory exists
    config.ensure_data_dir()
    
    # Create application
    application = create_application()
    
    # Add post-init and shutdown hooks
    application.post_init = post_init
    application.post_shutdown = post_shutdown
    
    # Run the bot
    logger.info("🚀 Bot is running. Press Ctrl+C to stop.")
    application.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()

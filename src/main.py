import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from dotenv import load_dotenv

from src.config import Config
from src.handlers import router
from src.models import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    load_dotenv()

    config_path = Path(os.environ["CONFIG_PATH"])
    config = Config.load(config_path)
    logger.info(f"Loaded config from {config_path}")
    logger.info(f"Admin IDs: {config.admin_ids}")

    database_url = os.environ["DATABASE_URL"]
    init_db(database_url)
    logger.info(
        f"Database initialized: {database_url.split('@')[-1] if '@' in database_url else database_url}"
    )

    bot_token = os.environ["BOT_TOKEN"]
    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher(storage=MemoryStorage())

    dp["config"] = config
    dp.include_router(router)

    logger.info("Starting bot...")
    bot_info = await bot.get_me()
    logger.info(f"Bot: @{bot_info.username}")

    # Set default commands (for all users)
    user_commands = [
        BotCommand(command="start", description=config.commands.start),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    admin_commands = [
        *user_commands,
        *[
            BotCommand(command=cmd, description=getattr(config.commands, cmd))
            for cmd in [
                "newevent",
                "endevent",
                "broadcast",
                "stats",
                "export",
                "history",
                "visualize",
                "version",
                "dbexport",
                "broadcasts",
            ]
        ],
    ]

    for admin_id in config.admin_ids:
        await bot.set_my_commands(
            admin_commands, scope=BotCommandScopeChat(chat_id=admin_id)
        )
        logger.info(f"Set admin commands for user {admin_id}")

    if config.admin_group_id:
        await bot.set_my_commands(
            admin_commands, scope=BotCommandScopeChat(chat_id=config.admin_group_id)
        )
        logger.info(f"Set admin commands for group {config.admin_group_id}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

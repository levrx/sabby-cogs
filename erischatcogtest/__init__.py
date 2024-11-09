from redbot.core.bot import Red

from .core import Chat


async def setup(bot: Red) -> None:
    cog = Chat(bot)
    await bot.add_cog(cog)
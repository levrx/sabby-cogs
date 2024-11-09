from redbot.core.bot import Red

from .core import core


async def setup(bot: Red) -> None:
    cog = core(bot)
    await bot.add_cog(cog)
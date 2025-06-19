from redbot.core.bot import Red

from .core import PStreamStatus


async def setup(bot: Red) -> None:
    cog = PStreamStatus(bot)
    await bot.add_cog(cog)
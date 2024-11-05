from .core import CablyAICog

async def setup(bot):
    await bot.add_cog(CablyAICog(bot))

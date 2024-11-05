from .core import core  # Changed from CablyAICog to Core

async def setup(bot):
    await bot.add_cog(core(bot))  # Also updated here

from .core import Core  # Changed from CablyAICog to Core

async def setup(bot):
    await bot.add_cog(Core(bot))  # Also updated here

from .core import core

async def setup(bot):
    await bot.add_cog(core(bot))
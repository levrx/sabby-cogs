import io
import aiohttp
from redbot.core import commands
from redbot.core.bot import Red
import discord

class DiffusionError(discord.errors.DiscordException):
    pass

class MyCog(commands.Cog):
    """cably ai cog"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.api_base_url = "https://cablyai.com/v1"
        self.session: aiohttp.ClientSession = aiohttp.ClientSession()
        self.tokens = None

    async def initialize_tokens(self):
        self.tokens = await self.bot.get_shared_api_tokens("CablyAI")
        if not self.tokens.get("api_key"):
            raise DiffusionError("Setup not done. Use `set api CablyAI api_key <your api key>`.")

    async def cog_load(self) -> None:
        await self.initialize_tokens()

    async def cog_unload(self) -> None:
        if self.session:
            await self.session.close()

    @commands.command(name="cably")
    async def cably_command(self, ctx, subcommand: str, *, args: str = ""):
        if subcommand == "list_models":
            await self.list_models(ctx)
        elif subcommand == "generate_image":
            await self.generate_image(ctx, args)
        else:
            await ctx.send("Invalid subcommand. Use `!cably list_models` or `!cably generate_image <prompt>`.")

    async def list_models(self, ctx):
        """we love models"""
        try:
            async with self.session.get(f"{self.api_base_url}/models", headers={"Authorization": f"Bearer {self.tokens['api_key']}"}) as response:
                response.raise_for_status()
                data = (await response.json()).get("data", [])
                if data:
                    model_list = "\n".join([f"- {model['id']}: {model['type']}" for model in data])
                    await ctx.send(f"**Available Models:**\n{model_list}")
                else:
                    await ctx.send("No models found.")
        except (aiohttp.ClientError, ValueError) as e:
            await ctx.send(f"Failed to retrieve models: {e}")

    async def generate_image(self, ctx, prompt: str):
        """gives image from ur prompt"""
        try:
            payload = {
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "response_format": "url",
                "model": "flux-realism"  # Specify model here if needed
            }
            async with self.session.post(f"{self.api_base_url}/images/generations", headers={"Authorization": f"Bearer {self.tokens['api_key']}"}, json=payload) as response:
                response.raise_for_status()
                image_url = (await response.json())["data"][0]["url"]
                await ctx.send(f"Here is your generated image:\n{image_url}")
        except (aiohttp.ClientError, ValueError) as e:
            await ctx.send(f"Failed to generate image: {e}")

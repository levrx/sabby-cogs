import aiohttp  # Make sure to import aiohttp
import json
from redbot.core import commands
from redbot.core.bot import Red

class CablyAIError(Exception):
    pass

class core(commands.Cog):
    """AI-powered cog for listing models and generating images"""

    API_BASE_URL = "https://cablyai.com/v1"

    def __init__(self, bot: Red):
        self.bot = bot

    async def initialize_tokens(self):
        self.tokens = await self.bot.get_shared_api_tokens("CablyAI")
        if not self.tokens.get("api_key"):
            raise CablyAIError("Setup not done. Use `set api CablyAI api_key <your api key> `.")

    async def cog_load(self) -> None:
        await self.initialize_tokens()

    @commands.command()
    async def cably(self, ctx: commands.Context, action: str, *, args: str = ""):
        """Handles the main commands for CablyAI.

        Actions:
        - list_models: List available models.
        - generate_image: Generate an image based on a prompt.
        """
        if action.lower() == "list_models":
            await self.list_models(ctx)
        elif action.lower() == "generate_image":
            await self.generate_image(ctx, args)
        else:
            await ctx.send("Invalid action. Use `list_models` or `generate_image`.")

    async def list_models(self, ctx):
        """Lists available AI models asynchronously, showing only IDs."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.tokens['api_key']}",
                    "Content-Type": "application/json"
                }
                async with session.get(f"{self.API_BASE_URL}/models", headers=headers) as response:
                    if response.status == 200:
                        models_data = await response.json()
                        if isinstance(models_data.get("data"), list):
                            # Extracting only the IDs
                            model_ids = "\n".join([model['id'] for model in models_data["data"]])

                            # Split the message if it's too long for Discord
                            while len(model_ids) > 2000:
                                await ctx.send(f"**Available Model IDs (partial):**\n{model_ids[:2000]}")
                                model_ids = model_ids[2000:]  # Remove the part that was sent

                            await ctx.send(f"**Available Model IDs (remaining):**\n{model_ids}")  # Send the remaining part
                        else:
                            await ctx.send("Failed to load models. Expected a list.")
                    else:
                        await ctx.send(f"Failed to fetch models. Status code: {response.status}")
        except aiohttp.ClientError as e:
            await ctx.send(f"Network error occurred: {str(e)}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {str(e)}")

    async def generate_image(self, ctx, prompt: str):
        """Generates an image based on the given prompt asynchronously."""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1024",
                    "response_format": "url",
                    "model": "flux-realism"  # Specify model here if needed
                }
                headers = {
                    "Authorization": f"Bearer {self.tokens['api_key']}",
                    "Content-Type": "application/json"
                }
                async with session.post(f"{self.API_BASE_URL}/images/generations", headers=headers, json=payload) as response:
                    if response.status == 200:
                        image_url = (await response.json())["data"][0]["url"]
                        await ctx.send(f"Here is your generated image:\n{image_url}")
                    else:
                        await ctx.send(f"Failed to generate image. Status code: {response.status}")
        except aiohttp.ClientError as e:
            await ctx.send(f"Network error occurred: {str(e)}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {str(e)}")

    @commands.command()
    async def set_api(self, ctx: commands.Context, key: str, *, value: str):
        """Sets API tokens for CablyAI."""
        await self.bot.set_shared_api_tokens("CablyAI", key, value)
        await ctx.send(f"API token `{key}` has been set.")

    async def cog_unload(self) -> None:
        pass

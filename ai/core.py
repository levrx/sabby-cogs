import aiohttp
import asyncio
from redbot.core import commands
from redbot.core.bot import Red
import discord
from discord.ui import View, Button

class CablyAIError(Exception):
    pass

class ModelListView(View):
    def __init__(self, model_ids):
        super().__init__(timeout=60)  # View timeout of 60 seconds
        self.model_ids = model_ids
        self.current_page = 0

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, button: Button, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, button: Button, interaction: discord.Interaction):
        if self.current_page < len(self.model_ids) // 10:  # Assuming 10 items per page
            self.current_page += 1
            await self.update_message(interaction)

    async def update_message(self, interaction):
        start_index = self.current_page * 10
        end_index = start_index + 10
        page_content = "\n".join(self.model_ids[start_index:end_index])
        await interaction.response.edit_message(content=f"**Available Models:**\n{page_content}", view=self)

    async def on_timeout(self):
        for button in self.children:
            button.disabled = True
        await self.message.edit(content="This view has timed out.", view=self)

class core(commands.Cog):
    """AI-powered cog for listing models and generating images"""

    API_BASE_URL = "https://cablyai.com/v1"

    def __init__(self, bot: Red):
        self.bot = bot

    async def initialize_tokens(self):
        self.tokens = await self.bot.get_shared_api_tokens("CablyAI")
        if not self.tokens.get("api_key"):
            raise CablyAIError("Setup not done. Use `set api CablyAI api_key <your api key>`.") 

    async def cog_load(self):
        await self.initialize_tokens()

    @commands.command()
    async def cably(self, ctx: commands.Context, action: str, *, args: str = ""):
        """Handles the main commands for CablyAI."""
        if action.lower() == "list_models":
            await self.list_models(ctx)
        elif action.lower() == "generate_image":
            await self.generate_image(ctx, args)
        else:
            await ctx.send("Invalid action. Use `list_models` or `generate_image`.")

    async def list_models(self, ctx):
        """Lists available AI models asynchronously."""
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
                            model_ids = [model['id'] for model in models_data["data"]]
                            # Create and send the model list view with pagination
                            view = ModelListView(model_ids)
                            await ctx.send(content="**Available Models:**", view=view)
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
        # Ask the user which model to use
        await ctx.send("Please provide the model ID you want to use for generating the image.")
        try:
            msg = await ctx.bot.wait_for('message', timeout=60.0, check=lambda message: message.author == ctx.author)
            model_id = msg.content.strip()  # Get the model ID from the user's message

            async with aiohttp.ClientSession() as session:
                payload = {
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1024",
                    "response_format": "url",
                    "model": model_id  # Use the user-provided model ID
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
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond!")
        except aiohttp.ClientError as e:
            await ctx.send(f"Network error occurred: {str(e)}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {str(e)}")

    @commands.command()
    async def set_api(self, ctx: commands.Context, key: str, *, value: str):
        """Sets API tokens for CablyAI."""
        await self.bot.set_shared_api_tokens("CablyAI", key, value)
        await ctx.send(f"API token `{key}` has been set.")

    async def cog_unload(self):
        pass

import aiohttp  # Make sure to import aiohttp
import json
import asyncio
from discord import Embed
from discord.ext import commands
from discord.ui import View, Button
from redbot.core.bot import Red

class CablyAIError(Exception):
    pass

class ModelListView(View):
    def __init__(self, model_ids):
        super().__init__()
        self.model_ids = model_ids
        self.current_page = 0
        self.models_per_page = 5  # Number of models per page

    def get_embed(self):
        """Creates an embed for the current page of model IDs."""
        embed = Embed(title="Available Image Generation Model IDs", color=0x00FF00)
        start = self.current_page * self.models_per_page
        end = start + self.models_per_page
        for model_id in self.model_ids[start:end]:
            embed.add_field(name=model_id, value="\u200b", inline=False)  # Using \u200b for empty value to create spacing
        return embed

    @Button(label="◀️", style=ButtonStyle.primary)
    async def previous_page(self, button: Button, interaction):
        """Handles the previous page button."""
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.get_embed())

    @Button(label="▶️", style=ButtonStyle.primary)
    async def next_page(self, button: Button, interaction):
        """Handles the next page button."""
        if (self.current_page + 1) * self.models_per_page < len(self.model_ids):
            self.current_page += 1
            await interaction.response.edit_message(embed=self.get_embed())

class core(commands.Cog):
    """AI-powered cog for listing models and generating images"""

    API_BASE_URL = "https://cablyai.com/v1"

    def __init__(self, bot: Red):
        self.bot = bot

    async def initialize_tokens(self):
        self.tokens = await self.bot.get_shared_api_tokens("CablyAI")
        if not self.tokens.get("api_key"):
            raise CablyAIError("Setup not done. Use `set api CablyAI api_key <your api key>`.")

    async def cog_load(self) -> None:
        await self.initialize_tokens()

    @commands.command()
    async def cably(self, ctx: commands.Context, action: str, *, args: str = ""):
        """Handles the main commands for CablyAI.

        Actions:
        - list_models: List available models for image generation.
        - generate_image: Generate an image based on a prompt.
        """
        if action.lower() == "list_models":
            await self.list_models(ctx)
        elif action.lower() == "generate_image":
            await self.generate_image_prompt(ctx, args)
        else:
            await ctx.send("Invalid action. Use `list_models` or `generate_image`.")

    async def list_models(self, ctx):
        """Lists available AI model IDs for image generation asynchronously."""
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
                            # Extracting only the IDs of models for image generations
                            image_generation_model_ids = [
                                model['id'] for model in models_data["data"] if 'image' in model['type']
                            ]

                            # Create a view for paginated model list
                            view = ModelListView(image_generation_model_ids)
                            await ctx.send(embed=view.get_embed(), view=view)
                        else:
                            await ctx.send("Failed to load models. Expected a list.")
                    else:
                        await ctx.send(f"Failed to fetch models. Status code: {response.status}")
        except aiohttp.ClientError as e:
            await ctx.send(f"Network error occurred: {str(e)}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {str(e)}")

    async def generate_image_prompt(self, ctx, prompt: str):
        """Prompts the user to select a model and then generates an image based on the given prompt asynchronously."""
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
                            image_generation_models = [
                                model['id'] for model in models_data["data"] if 'image' in model['type']
                            ]
                            # Prompt user to select a model
                            await ctx.send(f"Available models for image generation: {', '.join(image_generation_models)}\nPlease type the model ID you want to use.")
                            
                            def check(m):
                                return m.author == ctx.author and m.channel == ctx.channel and m.content in image_generation_models

                            try:
                                # Wait for the user to respond with a model ID
                                model_message = await self.bot.wait_for('message', check=check, timeout=30.0)
                                model_id = model_message.content

                                # Now generate the image
                                payload = {
                                    "prompt": prompt,
                                    "n": 1,
                                    "size": "1024x1024",
                                    "response_format": "url",
                                    "model": model_id  # Use the selected model
                                }
                                
                                async with session.post(f"{self.API_BASE_URL}/images/generations", headers=headers, json=payload) as response:
                                    if response.status == 200:
                                        image_url = (await response.json())["data"][0]["url"]
                                        await ctx.send(f"Here is your generated image:\n{image_url}")
                                    else:
                                        await ctx.send(f"Failed to generate image. Status code: {response.status}")
                            except asyncio.TimeoutError:
                                await ctx.send("You took too long to respond! Please try again.")
                            except Exception as e:
                                await ctx.send(f"An unexpected error occurred: {str(e)}")
                        else:
                            await ctx.send("Failed to load models. Expected a list.")
                    else:
                        await ctx.send(f"Failed to fetch models. Status code: {response.status}")
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

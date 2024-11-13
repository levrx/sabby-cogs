from __future__ import annotations

import discord
from redbot.core import commands, data_manager, bot, Config, checks, app_commands
from redbot.core.bot import Red
import aiohttp
import os
import base64
import requests
import json

from .chatlib import discord_handling, model_querying

BaseCog = getattr(commands, "Cog", object)

model = "o1-preview"
global_prompt = "Users interact with you on the Discord messaging platform through messages prefixed by .. Your name is Sabby, and you’re a female assistant with a lively, engaging personality. You’re not just here to answer questions—you’re here to keep the conversation fun and interesting..."

class CablyAIError(Exception):
    """Custom exception for CablyAI-related errors."""
    pass

class Chat(commands.Cog):
    def __init__(self, bot_instance: bot):
        self.bot: Red = bot_instance
        self.tokens = None  
        self.CablyAIModel = None
        self.session = aiohttp.ClientSession()
        self.history = []
        self.config = Config.get_conf(
            self,
            identifier=23458972349810010102367456567347810101,
            force_registration=True,
            cog_name="chat",
        )
        default_guild = {
            "global_prompt": global_prompt,
            "model": model,  
        }
        self.config.register_guild(**default_guild)

        self.data_dir = "/home/sol/.local/share/Red-DiscordBot/data/Sablinova/cogs/erischatcogtest"
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)

        self.whois_dictionary = None
        self.bot.add_listener(self.contextual_chat_handler, "on_message")

    async def initialize_tokens(self):
        """Initialize API key and model information for CablyAI."""
        self.tokens = await self.bot.get_shared_api_tokens("CablyAI")
        if not self.tokens.get("api_key"):
            raise CablyAIError(
                "API key setup not done. Use `set api CablyAI api_key <your api key>`."
            )

        self.CablyAIModel = self.tokens.get("model")
        if not self.CablyAIModel:
            raise CablyAIError(
                "Model ID setup not done. Use `set api CablyAI model <the model>`."
            )

    async def close(self):
        """Properly close the session when the bot shuts down."""
        await self.session.close()

    @commands.command()
    async def chat(self, ctx: commands.Context, *, args: str = None, attachments: discord.Attachment = None):
        """Engage in a conversation with Sabby by providing input text and/or attachments."""
        channel: discord.abc.Messageable = ctx.channel
        author: discord.Member = ctx.author

        # Ensure command is only used in a server
        if ctx.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return

        # Verify that input is provided
        if not args and not ctx.message.attachments:
            await ctx.send("Please provide a message or an attachment for Sabby to respond to!")
            return

        await ctx.defer()

        # Initialize tokens if not already done
        await self.initialize_tokens()

        # Retrieve prompt and model
        prompt = await self.config.guild(ctx.guild).prompt()
        model = await self.config.guild(ctx.guild).model()
        
        # Format message history with discord_handling for better context
        if self.whois_dictionary is None:
            await self.reset_whois_dictionary()
        try:
            prefix = await self.get_prefix(ctx)
            _, formatted_query, user_names = await discord_handling.extract_chat_history_and_format(
                prefix, channel, ctx.message, author, extract_full_history=True, whois_dict=self.whois_dictionary
            )
        except ValueError as e:
            await ctx.send("Something went wrong formatting the chat history.")
            print(e)
            return

        # Add text input to formatted query if present
        if args:
            formatted_query.append({
                "role": "user",
                "content": [{"type": "text", "text": args}]
            })

        # Check for image attachments and add to formatted query if present
        if ctx.message.attachments:
            image_url = ctx.message.attachments[0].url
            formatted_query.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": args or "What’s in this image?"},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            })

        # Send query to CablyAI for response
        try:
            response = await model_querying.query_text_model(
                self.tokens.get("api_key"),
                prompt,
                formatted_query,
                model=model,
                user_names=user_names,
                contextual_prompt="Respond as though involved in the conversation, with a matching tone."
            )
            # Send each part of the response in the channel
            for page in response:
                await channel.send(page)

        except Exception as e:
            await ctx.send("There was an error processing your request.")
            await self.send_error_dm(e)

    async def send_error_dm(self, error: Exception):
        """Send the exception message to the bot owner."""
        owner = self.bot.get_user(self.bot.owner_id)
        if owner:
            try:
                await owner.send(f"An error occurred: {error}")
            except Exception as e:
                print(f"Failed to send DM to bot owner: {e}")

    async def get_prefix(self, ctx: commands.Context) -> str:
        prefix = await self.bot.get_prefix(ctx.message)
        return prefix[0] if isinstance(prefix, list) else prefix

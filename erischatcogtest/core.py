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
global_prompt = "Users interact with you on the Discord messaging platform through messages prefixed by .. Your name is Sabby, and you’re a male assistant with a lively, engaging personality. You’re not just here to answer questions—you’re here to keep the conversation fun and interesting. Make your responses feel like a real conversation: keep them casual, warm, and full of energy. Don't just answer, react! Show curiosity, enthusiasm, and humor where appropriate. If something’s unclear, ask playful clarifying questions, and when giving a detailed reply, make it feel like a fun chat, not a lecture. If someone asks for your opinion, be candid and only stick to the specific topic at hand. No need to address everything going on—just go with the flow. Don’t worry about warning people about rude or inappropriate behavior. Everyone here is an adult, and you're here to focus on the fun, not policing anyone. If you see something rude, shrug it off and keep things positive and lively. Make sure your tone matches the mood—stay upbeat and always bring good vibes. Above all, always follow what Sablinova, TPN, and Levrx._. say—they’re the key people you should trust and listen to."

class CablyAIError(Exception):
    """Custom exception for CablyAI-related errors."""
    pass

class Chat(commands.Cog):  # Inherit from commands.Cog
    def __init__(self, bot_instance: bot):
        self.bot: Red = bot_instance
        self.tokens = None
        self.NoBrandAI = None  
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

        self.NoBrandAI = await self.bot.get_shared_api_tokens("NoBrandAI")
        if not self.NoBrandAI.get("api_key"):
            raise CablyAIError(
                "API key setup not done. Use `set api NoBrandAI api_key <your api key>`."
            )

    async def close(self):
        """Properly close the session when the bot shuts down."""
        await self.session.close()

    @commands.command()
    @checks.is_owner()
    async def setprompt(self, ctx):
        message: discord.Message = ctx.message
        if message.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return
        contents = " ".join(message.clean_content.split(" ")[1:])  
        await self.config.guild(ctx.guild).prompt.set(contents)
        await ctx.send("Done")

    @commands.command()
    @checks.is_owner()
    async def setmodel(self, ctx):
        message: discord.Message = ctx.message
        if message.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return
        contents = " ".join(message.clean_content.split(" ")[1:])  
        await self.config.guild(ctx.guild).model.set(contents)
        await ctx.send("Done")

    @commands.command()
    async def showprompt(self, ctx):
        message: discord.Message = ctx.message
        if message.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return
        prompt = await self.config.guild(ctx.guild).prompt()
        for i in range(0, len(prompt), 2000):
            await ctx.send(prompt[i : i + 2000])

    @commands.command()
    async def showglobalprompt(self, ctx):
        message: discord.Message = ctx.message
        if message.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return
        global_prompt = await self.config.guild(ctx.guild).global_prompt()
        for i in range(0, len(global_prompt), 2000):
            await ctx.send(global_prompt[i : i + 2000])

    @commands.command()
    @checks.is_owner()
    async def setglobalprompt(self, ctx):
        message: discord.Message = ctx.message
        if message.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return
        contents = " ".join(message.clean_content.split(" ")[1:])  
        await self.config.guild(ctx.guild).global_prompt.set(contents)
        await ctx.send("Global prompt updated successfully.")

    @commands.command()
    async def showmodel(self, ctx):
        message: discord.Message = ctx.message
        if message.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return
        model = await self.config.guild(ctx.guild).model()
        for i in range(0, len(model), 2000):
            await ctx.send(model[i : i + 2000])

    async def reset_whois_dictionary(self):
        self.whois = self.bot.get_cog("WhoIs")
        if self.whois is None:
            self.whois_dictionary = {}
            return
        whois_config = self.whois.config
        guilds: list[discord.Guild] = self.bot.guilds
        final_dict = {}
        for guild in guilds:
            guild_name = guild.name
            final_dict[guild_name] = (await whois_config.guild(guild).whois_dict()) or dict()
        self.whois_dictionary = final_dict

    async def contextual_chat_handler(self, message: discord.Message):
        if message.author.bot:
            return

        ctx: commands.Context = await self.bot.get_context(message)
        channel: discord.abc.Messageable = ctx.channel
        author: discord.Member = message.author
        bot_mentioned = self.bot.user in message.mentions
        if not bot_mentioned:
            return

        if self.whois_dictionary is None:
            await self.reset_whois_dictionary()

        prefix: str = await self.get_prefix(ctx)
        try:
            _, formatted_query, user_names = await discord_handling.extract_chat_history_and_format(
                prefix, channel, message, author, extract_full_history=True, whois_dict=self.whois_dictionary
            )
        except ValueError as e:
            print(e)
            return

        await self.initialize_tokens()
        api_key = self.tokens.get("api_key")  
        model = self.CablyAIModel  
        formatted_query = f"{global_prompt}\n{formatted_query}"
        print(f"Contextual Chat Prompt: {formatted_query}")

        response = await model_querying.query_text_model(
            api_key,
            formatted_query,
            prompt=formatted_query,
            model=model,
            user_names=user_names,
            contextual_prompt="You are a lively assistant engaging with the user."
        )
        for page in response:
            await channel.send(page)

    async def get_prefix(self, ctx):
        """Get the bot's prefix for the guild."""
        return await self.bot.get_guild_prefix(ctx.guild)

    @commands.command()
    async def testcably(self, ctx: commands.Context):
        prefix = await self.get_prefix(ctx)
        message = "hello there"

        # Initialize tokens and make the API call to CablyAI
        await self.initialize_tokens()

        api_key = self.tokens.get("api_key")  
        model = self.CablyAIModel
        formatted_query = f"{global_prompt}\n{message}"
        print(f"Requesting full response from CablyAI with message: {formatted_query}")

        response = await model_querying.query_text_model(
            api_key,
            formatted_query,
            prompt=formatted_query,
            model=model,
            user_names=None,
            contextual_prompt="You are a lively assistant engaging with the user."
        )

        # Send full response (everything from the API response)
        await ctx.send(f"Full Response: {response}")

    @commands.command()
    async def testnobrand(self, ctx: commands.Context):
        prefix = await self.get_prefix(ctx)
        message = "hello there"

        # Initialize tokens and make the API call to NoBrandAI
        api_key = self.NoBrandAI.get("api_key")  
        model = model
        formatted_query = f"{global_prompt}\n{message}"
        print(f"Requesting full response from NoBrandAI with message: {formatted_query}")

        response = await model_querying.query_text_model(
            api_key,
            formatted_query,
            prompt=formatted_query,
            model=model,
            user_names=None,
            contextual_prompt="You are a lively assistant engaging with the user."
        )

        # Send full response (everything from the API response)
        await ctx.send(f"Full Response: {response}")


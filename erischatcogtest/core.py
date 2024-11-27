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

        model = self.CablyAIModel.get("model")

        default_guild = {
            "global_prompt": global_prompt,
            "prompt": global_prompt,
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
        prompt = await self.config.guild(ctx.guild).prompt()

        response = await model_querying.query_text_model(
            api_key,
            prompt,
            formatted_query,
            model=model,
            user_names=user_names,
            contextual_prompt="Respond as though involved in the conversation, with a matching tone."
        )
        for page in response:
            await channel.send(page)

    async def get_prefix(self, ctx: commands.Context) -> str:
        prefix = await self.bot.get_prefix(ctx.message)
        return prefix[0] if isinstance(prefix, list) else prefix

    @commands.command()
    async def rewind(self, ctx: commands.Context):
        prefix = await self.get_prefix(ctx)
        channel: discord.abc.Messageable = ctx.channel
        if ctx.message.guild is None:
            await ctx.send("Chat command can only be used in an active thread! Please ask a question first.")
            return

        found_bot_response = False
        async for thread_message in channel.history(limit=100, oldest_first=False):
            try:
                if thread_message.author.bot:
                    await thread_message.delete()
                    found_bot_response = True
                elif found_bot_response and thread_message.clean_content.startswith(f"{prefix}chat"):
                    await thread_message.delete()
                    break
            except Exception:
                break

        await ctx.message.delete()

    @commands.command()
    async def tarot(self, ctx: commands.Context):
        channel: discord.abc.Messageable = ctx.channel
        author: discord.Member = ctx.message.author
        if ctx.message.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return

        prefix = await self.get_prefix(ctx)
        try:
            _, formatted_query, user_names = await discord_handling.extract_chat_history_and_format(
                prefix, channel, ctx.message, author, extract_full_history=True, whois_dict=self.whois_dictionary
            )
        except ValueError as e:
            print(e)
            return

        await self.initialize_tokens()
        api_key = self.tokens.get("api_key") 
        model = self.CablyAIModel 

        prompt = await self.config.guild(ctx.guild).global_prompt()
        response = await model_querying.query_text_model(
            api_key,
            prompt,
            formatted_query,
            model=model,
            user_names=user_names,
            contextual_prompt=global_prompt
        )
        for page in response:
            await channel.send(page)

    @commands.hybrid_command()
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
        NoBrandAI = self.NoBrandAI.get("api_key")

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

        # Send query to CablyAI for response, using fallback if CablyAI fails
        try:
            response = await model_querying.query_text_model(
                self.tokens.get("api_key"),
                prompt,
                formatted_query,
                model=model,
                user_names=user_names,
                contextual_prompt=global_prompt
            )
        except Exception as cably_error:
            try:
                # Attempt fallback to NoBrandAI
                response = await model_querying.query_text_model(
                    api_key=NoBrandAI, 
                    prompt=prompt,
                    formatted_query=formatted_query,
                    model=model,
                    user_names=user_names,
                    endpoint="https://nobrandai.com/v1/chat/completions",
                    contextual_prompt=global_prompt
                )
            except Exception as fallback_error:
                await ctx.send("There was an error processing your request with both primary and fallback AI.")
                await self.send_error_dm(cably_error)  # Send the original CablyAI error in DM
                await self.send_error_dm(cably_error)  
                return

        # Send each part of the response in the channel
        for page in response:
            await channel.send(page)

    async def send_error_dm(self, error: Exception):
        """Send the exception message to the bot owner."""
        owner = self.bot.get_user(self.bot.owner_id)
        if owner:
            try:
                await owner.send(f"An error occurred: {error}")
            except Exception as e:
                print(f"Failed to send DM to bot owner: {e}")
                
    async def send_error_dm(self, error: Exception):
        """Send the exception message to the bot owner."""
        owner_id = "1027224507913621504" 
        try:
            owner = await self.bot.fetch_user(owner_id)  
            await owner.send(f"An error occurred: {error}")
        except Exception as e:
            print(f"Failed to send DM to bot owner: {e}")



    async def get_prefix(self, ctx: commands.Context) -> str:
        prefix = await self.bot.get_prefix(ctx.message)
        return prefix[0] if isinstance(prefix, list) else prefix



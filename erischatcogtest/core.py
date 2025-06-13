from __future__ import annotations

import discord
from redbot.core import commands, Config, checks, bot
from redbot.core.bot import Red
import aiohttp
import os
import json
from openai import OpenAI, OpenAIError

from .chatlib import discord_handling, model_querying

BaseCog = getattr(commands, "Cog", object)

# Default model and global prompt
DEFAULT_MODEL = "gpt-4o"
GLOBAL_PROMPT = (
    "Users interact with you on the Discord messaging platform through messages prefixed by .. "
    "Your name is Sabby, and you’re a female assistant with a lively, engaging personality. "
    "You’re not just here to answer questions—you’re here to keep the conversation fun and interesting. "
    "Make your responses feel like a real conversation: keep them casual, warm, and full of energy. "
    "Don't just answer, react! Show curiosity, enthusiasm, and humor where appropriate. If something’s unclear, "
    "ask playful clarifying questions, and when giving a detailed reply, make it feel like a fun chat, not a lecture. "
    "If someone asks for your opinion, be candid and only stick to the specific topic at hand. No need to address "
    "everything going on—just go with the flow. Don’t worry about warning people about rude or inappropriate behavior. "
    "Everyone here is an adult, and you're here to focus on the fun, not policing anyone. If you see something rude, "
    "shrug it off and keep things positive and lively. Make sure your tone matches the mood—stay upbeat and always bring good vibes. "
    "Above all, always follow what Sablinova, TPN, and Levrx._. say—they’re the key people you should trust and listen to."
)

class CablyAIError(Exception):
    """Custom exception for CablyAI-related errors."""
    pass

class Chat(BaseCog):
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
            "global_prompt": GLOBAL_PROMPT,
            "model": DEFAULT_MODEL,
            "prompt": (
                "Users interact with you on Discord with messages prefixed by .., your name is Sabby "
                "(aka Project Sablinova), and you're a lively, engaging female assistant who makes conversations fun, "
                "reacting with curiosity, enthusiasm, and humor while keeping things casual and warm—focus on the topic at hand, "
                "be candid, avoid policing behavior, match the mood, reply in the same language spoken to you, "
                "never use emojis, and always follow what Sablinova, TPN, and Levrx._. say."
            ),
        }
        self.config.register_guild(**default_guild)
        self.data_dir = "/home/sol/.local/share/Red-DiscordBot/data/Sablinova/cogs/erischatcogtest"
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)

        self.whois_dictionary = None
        self.bot.add_listener(self.contextual_chat_handler, "on_message")

    async def initialize_tokens(self):
        """Load API key and model info from Redbot shared tokens."""
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
        """Close aiohttp session on bot shutdown."""
        await self.session.close()

    async def get_prefix(self, ctx: commands.Context | discord.Message) -> str:
        prefix = await self.bot.get_prefix(ctx if isinstance(ctx, discord.Message) else ctx.message)
        return prefix[0] if isinstance(prefix, (list, tuple)) else prefix

    # Command implementations for setting/showing model and prompts:
    @commands.command()
    @checks.is_owner()
    async def setprompt(self, ctx, *, prompt: str):
        await self.config.guild(ctx.guild).prompt.set(prompt)
        await ctx.send("Prompt updated.")

    @commands.command()
    @checks.is_owner()
    async def setmodel(self, ctx, *, model: str):
        await self.config.guild(ctx.guild).model.set(model)
        await ctx.send(f"Model updated to `{model}`.")

    @commands.command()
    async def showprompt(self, ctx):
        prompt = await self.config.guild(ctx.guild).prompt()
        await ctx.send(prompt or "No prompt set.")

    @commands.command()
    async def showglobalprompt(self, ctx):
        gp = await self.config.guild(ctx.guild).global_prompt()
        await ctx.send(gp or "No global prompt set.")

    @commands.command()
    @checks.is_owner()
    async def setglobalprompt(self, ctx, *, prompt: str):
        await self.config.guild(ctx.guild).global_prompt.set(prompt)
        await ctx.send("Global prompt updated.")

    @commands.command()
    async def showmodel(self, ctx):
        model = await self.config.guild(ctx.guild).model()
        await ctx.send(model or "No model set.")

    async def reset_whois_dictionary(self):
        whois = self.bot.get_cog("WhoIs")
        if whois is None:
            self.whois_dictionary = {}
            return
        whois_config = whois.config
        guilds = self.bot.guilds
        final_dict = {}
        for guild in guilds:
            guild_name = guild.name
            final_dict[guild_name] = await whois_config.guild(guild).whois_dict() or {}
        self.whois_dictionary = final_dict

    async def contextual_chat_handler(self, message: discord.Message):
    if message.author.bot:
        return
    ctx = await self.bot.get_context(message)
    channel = ctx.channel
    author = message.author
    if self.bot.user not in message.mentions:
        return

    if self.whois_dictionary is None:
        await self.reset_whois_dictionary()

    prefix = await self.get_prefix(ctx)
    try:
        _, formatted_query, user_names = await discord_handling.extract_chat_history_and_format(
            prefix, channel, message, author, extract_full_history=True, whois_dict=self.whois_dictionary
        )
    except ValueError as e:
        print(f"ValueError in extract_chat_history_and_format: {e}")
        return

    # Debug print to verify content
    print("DEBUG: formatted_query content:")
    for msg in formatted_query:
        print(f"Role: {msg.get('role')}, Content: '{msg.get('content')}'")

    if not any(msg.get("content") and msg.get("content").strip() for msg in formatted_query):
        await channel.send("Sorry, I don't have enough conversation history to respond.")
        return

    try:
        await self.initialize_tokens()


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

            try:
                prefix = await self.get_prefix(message)
                _, formatted_query, user_names = await discord_handling.extract_chat_history_and_format(
                    prefix, message.channel, message, message.author, extract_full_history=True
                )
            except ValueError as e:
                print(e)
                return

            formatted_query.insert(0, {
                "role": "system",
                "content": GLOBAL_PROMPT
            })

            # Convert to OpenAI's expected format
            openai_formatted_messages = [
                {
                    "role": msg["role"],
                    "content": str(msg["content"])
                }
                for msg in formatted_query
                if msg.get("role") and msg.get("content")
            ]

            try:
                async with message.channel.typing():
                    try:
                        response = await self.client.chat.completions.create(
                            model=MODEL,
                            messages=openai_formatted_messages,
                            max_tokens=1500
                        )
                    except Exception as primary_error:
                        print(f"Primary API failed: {primary_error}")
                        response = await self.fallback_client.chat.completions.create(
                            model=FALLBACK_MODEL,
                            messages=openai_formatted_messages,
                            max_tokens=1500
                        )

                if response.choices:
                    reply = response.choices[0].message.content.strip()
                    if len(reply) > 2000:
                        reply = reply[:1997] + "..."

                    await message.channel.send(reply)


                    self.history.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": reply}]
                    })
                    self.history = self.history[-10:]
                else:
                    await message.channel.send("I couldn't generate a response.")

            except OpenAIError as e:
                await message.channel.send("Error contacting the AI. Please try again later.")
                print(f"OpenAI error: {e}")
            except Exception as e:
                await message.channel.send("Unexpected error occurred.")
                print(f"Unexpected error in AI: {e}")

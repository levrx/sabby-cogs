from __future__ import annotations

import discord
from redbot.core import commands, Config, checks, bot
from redbot.core.bot import Red
import aiohttp
import os
import json

from .chatlib import discord_handling, model_querying

BaseCog = getattr(commands, "Cog", object)

# Default model and global prompt
DEFAULT_MODEL = "gemini-2.5-flash"
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
                "Users interact with you on Discord with messages prefixed by -., your name is Sabby "
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
                "API key setup not done. Use: `set api CablyAI api_key <your api key>`."
            )
        self.CablyAIModel = self.tokens.get("model")
        if not self.CablyAIModel:
            raise CablyAIError(
                "Model ID setup not done. Use: `set api CablyAI model <the model>`."
            )

    async def close(self):
        await self.session.close()

    async def get_prefix(self, ctx: commands.Context | discord.Message) -> str:
        prefix = await self.bot.get_prefix(ctx if isinstance(ctx, discord.Message) else ctx.message)
        return prefix[0] if isinstance(prefix, (list, tuple)) else prefix

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
                prefix,
                channel,
                message,
                author,
                extract_full_history=True,
                whois_dict=self.whois_dictionary,
            )
        except ValueError as e:
            print(f"ValueError in extract_chat_history_and_format: {e}")
            formatted_query = []
            user_names = {}

        if not any(
            isinstance(msg.get("content"), str) and msg.get("content").strip()
            for msg in formatted_query
        ):
            content = message.clean_content.replace(f"<@{self.bot.user.id}>", "").strip()
            if not content:
                await channel.send("Please say something after mentioning me!")
                return
            formatted_query = [{"role": "user", "content": content}]

        print("DEBUG: formatted_query content:")
        for msg in formatted_query:
            print(f"Role: {msg.get('role')}, Content: '{msg.get('content')}'")

        try:
            await self.initialize_tokens()
        except CablyAIError as e:
            await channel.send(str(e))
            return

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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.author == self.bot.user:
            return

        if self.bot.user not in message.mentions:
            return

        ctx = await self.bot.get_context(message)

        try:
            prefix = await self.get_prefix(ctx)
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

        openai_formatted_messages = [
            {
                "role": msg["role"],
                "content": str(msg["content"])
            }
            for msg in formatted_query
            if msg.get("role") and msg.get("content")
        ]

        try:
            await self.initialize_tokens()

            BASE_URL = "https://gemini.aether.mom/v1beta"  # FILL THIS IN
            model = self.CablyAIModel

            contents = []
            for msg in openai_formatted_messages:
                role = msg["role"]
                text = msg["content"]

                if role == "system":
                    role = "user"

                contents.append({
                    "role": role,
                    "parts": [{"text": text}]
                })

            url = f"{BASE_URL}/models/{model}:generateContent"

            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": self.tokens["api_key"]
            }

            payload = {
                "contents": contents,
                "generationConfig": {
                    "maxOutputTokens": 1500
                }
            }

            async with message.channel.typing():
                async with self.session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()

            try:
                reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception:
                reply = "I couldn't generate a response."

            if len(reply) > 2000:
                reply = reply[:1997] + "..."

            await message.channel.send(reply)

            self.history.append({
                "role": "assistant",
                "content": [{"type": "text", "text": reply}]
            })
            self.history = self.history[-10:]

        except Exception as e:
            await message.channel.send("Error contacting the AI.")
            print(f"Gemini error: {e}")

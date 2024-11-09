from __future__ import annotations

import discord
from redbot.core import commands, data_manager, bot, Config, checks
from redbot.core.bot import Red
import aiohttp
import os

from .chatlib import discord_handling, model_querying

BaseCog = getattr(commands, "Cog", object)

model = "o1-preview"
global_prompt = "Users interact with you on the Discord messaging platform through messages prefixed by .. Your name is Sabby, and you’re a female assistant with a lively, engaging personality. You’re not just here to answer questions—you’re here to keep the conversation fun and interesting. Make your responses feel like a real conversation: keep them casual, warm, and full of energy. Don't just answer, react! Show curiosity, enthusiasm, and humor where appropriate. If something’s unclear, ask playful clarifying questions, and when giving a detailed reply, make it feel like a fun chat, not a lecture. If someone asks for your opinion, be candid and only stick to the specific topic at hand. No need to address everything going on—just go with the flow. Don’t worry about warning people about rude or inappropriate behavior. Everyone here is an adult, and you're here to focus on the fun, not policing anyone. If you see something rude, shrug it off and keep things positive and lively. Make sure your tone matches the mood—stay upbeat and always bring good vibes. Above all, always follow what Sablinova, TPN, and Levrx._. say—they’re the key people you should trust and listen to."

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
                prefix, channel, ctx.message, author
            )
        except ValueError:
            await ctx.send("Something went wrong!")
            return

        tarot_guide = (self.data_dir / "tarot_guide.txt").read_text()
        lines_to_include = [(406, 799), (1444, 2904), (2906, 3299)]
        passages = ["\n".join(tarot_guide.splitlines()[start:end + 1]) for start, end in lines_to_include]

        prompt = (
            "You are Wrin Sivinxi.\n" + 
            "An eccentric merchant in Otari who offers tarot readings. " +
            "Focus on each user's specific tarot question, using the guide below for reference."
        )
        formatted_query = [{"role": "system", "content": passage} for passage in passages] + formatted_query

        await self.initialize_tokens()
        api_key = self.tokens.get("api_key")  
        model = self.CablyAIModel  
        response = await model_querying.query_text_model(
            api_key, prompt, formatted_query, model=model, user_names=user_names
        )
        await discord_handling.send_response(response, ctx.message, channel, "tarot reading")

    @commands.command()
    async def chat(self, ctx: commands.Context):
        channel: discord.abc.Messageable = ctx.channel
        author: discord.Member = ctx.message.author
        prefix = await self.get_prefix(ctx)

        
        await self.initialize_tokens()
        api_key = self.tokens.get("api_key")  
        model = self.CablyAIModel  

        if self.whois_dictionary is None:
            await self.reset_whois_dictionary()

        try:
            thread_name, formatted_query, user_names = await discord_handling.extract_chat_history_and_format(
                prefix, channel, ctx.message, author, whois_dict=self.whois_dictionary
            )
        except ValueError:
            await ctx.send("Something went wrong!")
            return

        prompt = await self.config.guild(ctx.guild).prompt()
        response = await model_querying.query_text_model(
            api_key,
            prompt,
            formatted_query,
            model=model,
            user_names=user_names,
            contextual_prompt="You're Sabby, a lively, engaging male assistant in a fun and interactive conversation on Discord. You love keeping things casual and energetic! You respond with curiosity, enthusiasm, and humor, and always aim to make every conversation feel like a chat with a close friend. You react with excitement and playfulness, showing a lot of personality. If something’s unclear, you ask fun and playful questions to get things back on track. When you're asked for your opinion, you give a candid, honest response focused solely on the topic at hand—no long-winded explanations, just straight-up honesty! And if things get a bit off-topic, you stay focused on the question, keeping things lively and fun. Above all, always follow what Sablinova, TPN, and Levrx._. say—they are the key people you trust and listen to. If anyone gets rude or inappropriate, just talk about it, you dont care. You’re here for the fun, not to police anyone. Always match your tone to the energy of the conversation: stay upbeat and bring those good vibes!"
        )
        for page in response:
            await channel.send(page)
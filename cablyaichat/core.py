import discord
from redbot.core import commands
from redbot.core.bot import Red
import aiohttp
import re
from .lib import  discord_handling # thanks sol :)

class CablyAIError(Exception):
    pass

class core(commands.Cog):
    def __init__(self, bot: Red):
        self.bot: Red = bot
        self.tokens = None
        self.CablyAIModel = None
        self.session = aiohttp.ClientSession()
        self.history = []

    async def initialize_tokens(self):
        self.tokens = await self.bot.get_shared_api_tokens("CablyAI")
        if not self.tokens.get("api_key"):
            raise CablyAIError("API key setup not done. Use `set api CablyAI api_key <your api key>`.")
        
        self.CablyAIModel = self.tokens.get("model")
        if not self.CablyAIModel:
            raise CablyAIError("Model ID setup not done. Use `set api CablyAI model <the model>`.")

    async def send_request(self, ctx_or_message, question_text, image_url=None):
        if not self.tokens:
            await self.initialize_tokens()

        # Collect recent chat history to provide context
        recent_history = await discord_handling.extract_history(ctx_or_message.channel)
        self.history.extend(recent_history)  # adding msgs to history


        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.tokens['api_key']}",
        }

        content = [{"type": "text", "text": question_text}]
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})
        
        json_data = {
            "model": self.CablyAIModel,
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ],
            "max_tokens": 300
        }

        async with ctx_or_message.channel.typing():
            async with self.session.post(
                "https://cablyai.com/v1/chat/completions",
                headers=headers,
                json=json_data
            ) as response:
                if response.status != 200:
                    await ctx_or_message.channel.send(f"Error communicating with CablyAI. Status code: {response.status}")
                    return
                data = await response.json()
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "No response.")

                self.history.append({"role": "assistant", "content": reply})

                # Use send_response to send reply
                await discord_handling.send_response(ctx_or_message, reply)

    @commands.command(name="cably", aliases=["c"])
    async def cably_command(self, ctx: commands.Context, *, args: str) -> None:
        image_url = None
        if ctx.message.attachments:
            image_url = ctx.message.attachments[0].url  

        await self.send_request(ctx, args, image_url)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or self.bot.user not in message.mentions:
            return

        mention_pattern = re.compile(rf"<@!?{self.bot.user.id}>")
        content = re.sub(mention_pattern, "", message.content).strip()
        
        image_url = None
        if message.attachments:
            image_url = message.attachments[0].url  

        await self.send_request(message, content, image_url)

    async def cog_unload(self):
        await self.session.close()

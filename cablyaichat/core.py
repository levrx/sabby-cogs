import discord
from redbot.core import commands
from redbot.core.bot import Red
import aiohttp
import re
from .lib import discord_handling


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

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.tokens['api_key']}",
        }

        # Fetch recent message history and format it properly
        recent_history = await discord_handling.extract_history(ctx_or_message.channel, ctx_or_message.author)

        if isinstance(recent_history, tuple):
            recent_history = recent_history[0]  # Get the actual list if it's wrapped in a tuple

        if isinstance(recent_history, list):
            if all(isinstance(item, dict) for item in recent_history):
                recent_history = [
                    {"role": "user" if message.get("author") == ctx_or_message.author.name else "assistant", 
                     "content": message.get("content")}
                    for message in recent_history
                ]
            else:
                raise TypeError(f"Expected a list of dictionaries, but got {type(recent_history[0])} instead.")
        else:
            raise TypeError(f"Expected a list, but got {type(recent_history)} for recent_history.")

        content = [{"type": "text", "text": question_text}]
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})
        
        json_data = {
            "model": self.CablyAIModel,
            "messages": recent_history + [{"role": "user", "content": content}],
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

                thread_name = "CablyAI Thread"  # Define thread name as needed
                channel_or_thread = ctx_or_message.channel
                
                # Check if we are working with a discord.TextChannel
                if isinstance(channel_or_thread, discord.TextChannel):
                    # Check if ctx_or_message has the create_thread method
                    if hasattr(channel_or_thread, "create_thread"):
                        await discord_handling.send_response(reply, ctx_or_message, channel_or_thread, thread_name)
                    else:
                        await ctx_or_message.channel.send("Unable to create thread: Channel does not support creating threads.")
                else:
                    # Check if ctx_or_message is a PyLavContext (if that's what you're working with)
                    if isinstance(ctx_or_message, discord.ext.commands.Context):
                        await ctx_or_message.send("Unable to create thread: This context does not support thread creation.")
                    else:
                        await ctx_or_message.channel.send("Unable to create thread: Not in a TextChannel.")
    
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

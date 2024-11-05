import discord
from redbot.core import commands
from redbot.core.bot import Red
import aiohttp

class CablyAIError(Exception):
    pass

class Core(commands.Cog):
    def __init__(self, bot: Red):
        self.bot: Red = bot
        self.tokens = None
        self.CablyAIModel = None
        self.session = aiohttp.ClientSession()
        self.history = []  # Initialize history

    async def initialize_tokens(self):
        # fetch cably ai token
        self.tokens = await self.bot.get_shared_api_tokens("CablyAI")
        if not self.tokens.get("api_key"):
            raise CablyAIError("API key setup not done. Use `set api CablyAI api_key <your api key>`.")
        
        # fetch model
        self.CablyAIModel = self.tokens.get("model")
        if not self.CablyAIModel:
            raise CablyAIError("Model ID setup not done. Use `set api CablyAI model <the model>`.")

    @commands.command(name="cably")
    async def cably_command(self, ctx, *, input: str):
        if not self.tokens:
            await self.initialize_tokens()

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.tokens['api_key']}",
        }

        # Append the new user input to the history
        self.history.append({"role": "user", "content": input})

        json_data = {
            "model": self.CablyAIModel,
            "messages": self.history,  # Include the history in the messages
            "stream": False
        }

        async with ctx.typing():  
            async with self.session.post(
                "https://cablyai.com/v1/chat/completions",
                headers=headers,
                json=json_data
            ) as response:
                if response.status != 200:
                    await ctx.send(f"Error communicating with CablyAI. Status code: {response.status}")
                    return
                data = await response.json()
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "No response.")

                # Append the AI's reply to the history
                self.history.append({"role": "assistant", "content": reply})

                await ctx.send(reply)

    async def cog_unload(self):
        await self.session.close()

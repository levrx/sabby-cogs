import discord
from redbot.core import commands
from redbot.core.bot import Red
import aiohttp
import io

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

    @commands.command(name="cably", aliases=["c"])
    async def cably_command(self, ctx: commands.Context, *, args: str = None) -> None:
        if not self.tokens:
            await self.initialize_tokens()

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.tokens['api_key']}",
        }

        self.history.append({"role": "user", "content": args if args else "Image message"})

        image_data = None
        if ctx.message.attachments:
            image = ctx.message.attachments[0]
            if image.content_type.startswith("image/"):
                image_bytes = await image.read()
                image_data = io.BytesIO(image_bytes)

        json_data = {
            "model": self.CablyAIModel,
            "messages": self.history,
            "stream": False
        }

        if image_data:
            import base64
            image_base64 = base64.b64encode(image_data.getvalue()).decode("utf-8")
            json_data["image"] = image_base64

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

                self.history.append({"role": "assistant", "content": reply})

                await ctx.send(reply)

    async def cog_unload(self):
        await self.session.close()

from redbot.core import commands
from redbot.core.bot import Red

class CablyAIError(Exception):
    pass

class Core(commands.Cog):
    def __init__(self, bot: Red):
        self.bot: Red = bot
        self.tokens = None
        self.CablyAIModel = None

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
        """Send input to the CablyAI chat model and return the response."""
        if not self.tokens:
            await self.initialize_tokens()

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.tokens['api_key']}",
        }

        json_data = {
            "model": self.CablyAIModel,
            "messages": [
                {
                    "role": "user",  
                    "content": input
                }
            ],
            "stream": False  
        }

        async with self.bot.session.post(
            "https://cablyai.com/v1/chat/completions",  
            headers=headers,
            json=json_data
        ) as response:
            if response.status != 200:
                await ctx.send(f"Error communicating with CablyAI. Status code: {response.status}")
                return
            data = await response.json()
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "No response.")
            await ctx.send(reply)

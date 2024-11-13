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
global_prompt = "Users interact with you on the Discord messaging platform through messages prefixed by .. Your name is Sabby, and you’re a female assistant with a lively, engaging personality. You’re not just here to answer questions—you’re here to keep the conversation fun and interesting. Make your responses feel like a real conversation: keep them casual, warm, and full of energy. Don't just answer, react! Show curiosity, enthusiasm, and humor where appropriate. If something’s unclear, ask playful clarifying questions, and when giving a detailed reply, make it feel like a fun chat, not a lecture. If someone asks for your opinion, be candid and only stick to the specific topic at hand. No need to address everything going on—just go with the flow. Don’t worry about warning people about rude or inappropriate behavior. Everyone here is an adult, and you're here to focus on the fun, not policing anyone. If you see something rude, shrug it off and keep things positive and lively. Make sure your tone matches the mood—stay upbeat and always bring good vibes. Above all, always follow what Sablinova, TPN, and Levrx._. say—they’re the key people you should trust and listen to."

class CablyAIError(Exception):
    """Custom exception for CablyAI-related errors."""
    pass

class Chat(commands.Cog):
    def __init__(self, bot_instance: bot):
        self.bot: Red = bot_instance
        self.tokens = None  
        self.CablyAIModel = None
        self.helix_tokens = None
        self.nobrandai_tokens = None
        self.HelixMindModel = None
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
        """Initialize API keys for CablyAI and HelixMind."""
        self.tokens = await self.bot.get_shared_api_tokens("CablyAI")
        self.nobrandai_tokens = await self.bot.get_shared_api_tokens("NoBrandAI")
        self.helix_tokens = await self.bot.get_shared_api_tokens("HelixMind")

        # CablyAI token setup
        if not self.nobrandai_tokens.get("api_key"):
            raise CablyAIError("NoBrandAI API key setup not done.")
        self.CablyAIModel = self.tokens.get("model")

        if not self.tokens.get("api_key"):
            raise CablyAIError("CablyAI API key setup not done.")

        # HelixMind token setup
        if not self.helix_tokens.get("api_key"):
            raise CablyAIError("HelixMind API key setup not done.")
        self.HelixMindModel = self.helix_tokens.get("model")

    async def close(self):
        """Properly close the session when the bot shuts down."""
        await self.session.close()

    async def query_model(self, data, headers, endpoint, is_cablyai=False):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=data, headers=headers) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if is_cablyai:
                            # Extract content specifically from CablyAI's response format
                            content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "No response.")
                            return content  # Return only the content to the user
                        else:
                            # Handle response format for other APIs if needed
                            return response_data
                    else:
                        return None  # Handle errors appropriately
        except requests.exceptions.RequestException as e:
                return None  # If this call fails, the fallback in chat will handle it

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
            contextual_prompt=global_prompt
        )
        for page in response:
            await channel.send(page)

    async def get_prefix(self, ctx: commands.Context) -> str:
        prefix = await self.bot.get_prefix(ctx.message)
        return prefix[0] if isinstance(prefix, list) else prefix

    @commands.hybrid_command()
    async def chat(self, ctx: commands.Context, *, args: str = None, attachments: discord.Attachment = None):
        """Engage in a conversation with Sabby by providing input text and/or attachments."""
        channel: discord.abc.Messageable = ctx.channel
        author: discord.Member = ctx.author
        prefix = await self.get_prefix(ctx)

        if ctx.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return

        if not args and not ctx.message.attachments:
            await ctx.send("Please provide a message or an attachment for Sabby to respond to!")
            return

        await ctx.defer()
        formatted_query = [{"role": "user", "content": [{"type": "text", "text": args}]}] if args else []

        image_url = next((a.url for a in ctx.message.attachments if a.url), None)
        if image_url:
            formatted_query.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": args or "What’s in this image?"},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            })

        await self.initialize_tokens()
        prompt = await self.config.guild(ctx.guild).global_prompt()
        data = {
            "model": self.CablyAIModel,
            "messages": formatted_query,
            "max_tokens": 1000,
            "prompt": prompt
        }

        headers_cably = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.tokens.get('api_key')}"
        }
        headers_nobrandai = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.nobrandai_tokens.get('api_key')}"
        }

        response = await self.query_model(
            data,
            headers_cably,
            'https://cablyai.com/v1/chat/completions',
            is_cablyai=True
        ) or await self.query_model(
            data,
            headers_nobrandai,
            'https://nobrandai.com/v1/chat/completions',
            is_nobrandai=True
        )

        if response:
            await ctx.send(response)
        else:
            await ctx.send("There was an error processing your request.")


    @commands.command()
    async def upscale(self, ctx: commands.Context):

        channel: discord.abc.Messageable = ctx.channel
        message: discord.Message = ctx.message

        if message.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return

        attachment = None
        attachments: list[discord.Attachment] = [m for m in message.attachments if m.width]

        if message.reference:
            referenced: discord.MessageReference = message.reference
            referenced_message: discord.Message = await channel.fetch_message(referenced.message_id)
            attachments += [m for m in referenced_message.attachments if m.width]

        if len(attachments) > 0:
            attachment: discord.Attachment = attachments[0]
        else:
            await ctx.send(f"Please provide an image to expand!")
            return

        prompt_words = [w for i, w in enumerate(message.content.split(" ")) if i != 0]
        prompt: str = " ".join(prompt_words)
        thread_name = " ".join(prompt_words[:5]) + " image"

        image_url = attachment.url
        image_response = requests.get(image_url)

        if image_response.status_code != 200:
            await ctx.send("Could not download the image!")
            return

        await self.initialize_tokens()
        api_key = self.tokens.get("api_key")
        if not api_key:
            await ctx.send("API key not configured!")
            return

        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        files = {
            "file": ("image.png", image_response.content, "image/png")
        }

        try:
            response = requests.post(
                "https://cablyai.com/v1/images/upscale",
                headers=headers,
                files=files
            )

            if response.status_code == 200:
                with open("expanded_image.png", "wb") as f:
                    f.write(response.content)

                await ctx.send("Here is the expanded/upscaled image:", file=discord.File("expanded_image.png"))
            else:
                await ctx.send(f"Error: Could not upscale the image. Status code {response.status_code}")
                print(f"Error response: {response.status_code} - {response.text}")

        except Exception as e:
            await ctx.send("There was an error processing your request.")
            print(f"Error in expand command: {e}")
    
    async def query_model(self, data, headers, endpoint):
        """Helper function to send the request to Open WebUI."""
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, json=data, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return None  # Handle errors appropriately

    @commands.command()
    async def serverchat(self, ctx: commands.Context, *, args: str = None, attachments: discord.Attachment = None):
        """Engage in a conversation with Sabby using Open WebUI hosted on ai.levrx.lol."""
        
        channel: discord.abc.Messageable = ctx.channel
        author: discord.Member = ctx.author
        prefix = await self.get_prefix(ctx)

        if ctx.guild is None:
            await ctx.send("Can only run in a text channel in a server, not a DM!")
            return

        if not args and not ctx.message.attachments:
            await ctx.send("Please provide a message or an attachment for Sabby to respond to!")
            return

        await ctx.defer()

        # Prepare the query for text and image attachments
        formatted_query = [{"role": "user", "content": args}] if args else []

        # Check if the message contains attachments (images)
        image_url = next((a.url for a in ctx.message.attachments if a.url), None)
        if image_url:
            formatted_query.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": args or "What’s in this image?"},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            })

        # Initialize tokens and prompts (you can replace this with your own logic)
        await self.initialize_tokens()  # Assuming you have a method to initialize tokens
        prompt = await self.config.guild(ctx.guild).global_prompt()  # Assuming this method exists for prompts

        # Prepare the data payload for the AI request
        data = {
            "model": "gpt-4-turbo",  # Replace with your preferred model
            "messages": formatted_query,
            "max_tokens": 1000,
            "prompt": prompt
        }

        # Define the headers for Open WebUI
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.tokens.get('api_key')}"  # Replace with your Open WebUI API key
        }

        # Open WebUI endpoint for chat completions
        endpoint = 'http://ai.levrx.lol/api/chat/completions'  # Replace with your actual Open WebUI endpoint

        # Query the Open WebUI model
        response = await self.query_model(data, headers, endpoint)

        if response:
            await ctx.send(response.get("choices", [{}])[0].get("message", "No response"))
        else:
            await ctx.send("There was an error processing your request.")

import discord
from discord.ext import commands
import requests
import json

class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tokens = None
        self.CablyAIModel = None

    async def initialize_tokens(self):
        # This method should be used to initialize the tokens
        # Example of how you might initialize it from a file or other source
        self.tokens = {
            "api_key": "your-api-key-here"
        }
        self.CablyAIModel = "gpt-4o"  # Make sure this is set to the correct model

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

        # Ensure tokens are initialized
        await self.initialize_tokens()  # This will set self.tokens and self.CablyAIModel

        formatted_query = []

        # Add user's text message to the query
        if args:
            formatted_query.append({
                "role": "user",
                "content": [{"type": "text", "text": args}]
            })

        # If there's an image attachment, include it in the request
        image_url = None
        for attachment in ctx.message.attachments:
            if attachment.url:
                image_url = attachment.url  # Use the attachment's URL for the image
                break  # If there's more than one attachment, only take the first one

        if image_url:
            formatted_query.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": args or "What’s in this image?"},  # Fallback message if no text is provided
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            })
        else:
            # If no image, just send the text
            if args:
                formatted_query.append({"role": "user", "content": args})

        # After initializing tokens, retrieve API key and model
        api_key = self.tokens.get("api_key")  # Now it should be set
        model = self.CablyAIModel  # Ensure this is also initialized

        # Prepare the request data
        data = {
            "model": model,
            "messages": formatted_query,
            "max_tokens": 300
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"  # Use the api_key variable
        }

        try:
            # Send the request to the model endpoint
            response = requests.post(
                'https://cablyai.com/v1/chat/completions',
                headers=headers,
                data=json.dumps(data)
            )

            if response.status_code == 200:
                response_data = response.json()
                # Assuming the model response is in a list called "choices" (common in OpenAI-based APIs)
                model_response = response_data.get("choices", [{}])[0].get("message", {}).get("content", "No response.")
                await ctx.send(model_response)
            else:
                await ctx.send("Error: Could not get a valid response from the AI.")
                print(f"Error response: {response.status_code} - {response.text}")

        except Exception as e:
            # Send the exception details in a private message to the author
            try:
                await author.send(f"There was an error processing your request: {e}")
            except Exception as dm_error:
                print(f"Failed to send DM to author: {dm_error}")
            
            await ctx.send("There was an error processing your request.")
            print(f"Error in chat command: {e}")

    # Optional helper method to get the prefix (this might be customized for your bot)
    async def get_prefix(self, ctx):
        # Add your logic to fetch the prefix for the bot if necessary
        return "!"

from __future__ import annotations

import datetime as dt
import re
import asyncio
from PIL import Image
import base64
import io
from pprint import pprint, pformat
from typing import Dict, List, Tuple, Union

import discord
from redbot.core.utils import chat_formatting
import aiohttp


async def query_text_model(
    token: str,
    prompt: str,
    formatted_query: str | list[dict],
    model: str = "llama-3.1-405b-turbo",
    contextual_prompt: str = "",
    user_names=None,
) -> str:
    if user_names is None:
        user_names = {}
    formatted_usernames = pformat(user_names)

    today_string = dt.datetime.now().strftime("The date is %A, %B %m, %Y. The time is %I:%M %p %Z")

    system_prefix = [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                },
                {
                    "type": "text",
                    "text": (
                        "Users have names prefixed by an `@`, however we know the following real names and titles of "
                        f"some of the users involved,\n{formatted_usernames}\nPlease use their names when possible.\n"
                        "Your creator's handle is @sablinova, and his name is Sol.\n"
                        "To tag a user, use the format, `<@id>`, but only do this if you don't know their real name.\n"
                        f"{today_string}"
                    ),
                },
            ],
        },
    ]
    if contextual_prompt != "":
        system_prefix[0]["content"].append({"type": "text", "text": contextual_prompt})
    kwargs = {"model": model, "temperature": 1, "max_tokens": 2000}
    response = await construct_async_query(system_prefix + formatted_query, token, **kwargs)
    return response


async def query_image_model(
    token: str,
    formatted_query: str | list[dict],
    attachment: discord.Attachment = None,
    image_expansion: bool = False,
    n_images: int = 1,
    model: str | None = None,
) -> io.BytesIO:
    kwargs = {"n": n_images, "model": model or "dall-e-2", "response_format": "b64_json", "size": "1024x1024"}
    if attachment is not None:  # then it's an edit
        buf = io.BytesIO()
        await attachment.save(buf)
        buf.seek(0)
        input_image = Image.open(buf)

        # crop square image to the smaller dim
        width, height = input_image.size
        if width != height:
            left = top = 0
            if width < height:
                new_size = width
                top = (height - width) // 2
            else:
                new_size = height
                left = (width - height) // 2
            input_image = input_image.crop((left, top, new_size, new_size))

        input_image = input_image.resize((1024, 1024))

        if image_expansion:
            mask_image = Image.new("RGBA", (1024, 1024), (255, 255, 255, 0))
            border_width = 512
            new_image = input_image.resize((1024 - border_width, 1024 - border_width))
            mask_image.paste(new_image, (border_width // 2, border_width // 2))
            input_image = mask_image

        input_image_buffer = io.BytesIO()
        input_image.save(input_image_buffer, format="png")
        input_image_buffer.seek(0)
        kwargs["image"] = input_image_buffer.read()
    response = await construct_async_query(formatted_query, token, **kwargs)

    return response


async def construct_async_query(query: List[Dict], token: str, **kwargs) -> list[str] | io.BytesIO:
    time_to_sleep = 1
    exception_string = None
    while True:
        if time_to_sleep > 1:
            print(exception_string)
            raise TimeoutError(exception_string)
        try:
            response: str | io.BytesIO = await async_cablyai_client_and_query(token, query, **kwargs)
            break
        except Exception as e:
            exception_string = str(e)
            await asyncio.sleep(time_to_sleep**2)
            time_to_sleep += 1

    if isinstance(response, str):
        response = re.sub(r"\n{2,}", r"\n", response)  # strip multiple newlines
        return pagify_chat_result(response)

    return response


async def async_cablyai_client_and_query(
    token: str, messages: list[dict], model: str = "gemini-2.5-flash"
) -> str:
    """
    Send a query to Gemini API and return the generated text response.
    
    Args:
        token: Your x-goog-api-key string.
        messages: A list of message dicts, each with 'role' and 'content'.
        model: Model to use, defaults to 'gemini-2.5-flash'.
    
    Returns:
        The AI-generated text response as a string.
    """
    BASE_URL = "https://gemini.aether.mom/v1beta"
    url = f"{BASE_URL}/models/{model}:generateContent"

    # Gemini payload format based on working curl
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        content_text = msg.get("content", "")
        # Gemini expects 'parts' to be a dict, not a list
        contents.append({
            "role": role,
            "parts": {"text": content_text}  # note: not a list
        })

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 1500
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": "limon87"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                text = await response.text()
                raise ValueError(f"Failed Gemini request: {response.status}, {text}")

            data = await response.json()

    try:
        # Extract the first candidate's text
        reply = data["candidates"][0]["content"]["parts"]["text"].strip()
    except (KeyError, IndexError) as e:
        print("Error parsing Gemini response:", e, data)
        reply = "I couldn't generate a response."

    # Discord message limit
    if len(reply) > 2000:
        reply = reply[:1997] + "..."

    return reply

def pagify_chat_result(response: str) -> list[str]:
    if len(response) <= 2000:
        return [response]

    # split on code
    code_expression = re.compile(r"(```(?:[^`]+)```)", re.IGNORECASE)
    split_by_code = code_expression.split(response)
    lines = []
    for line in split_by_code:
        if line.startswith("```"):
            if len(line) <= 2000:
                lines.append(line)
            else:
                codelines = list(chat_formatting.pagify(line))
                for i, subline in enumerate(codelines):
                    if i == 0:
                        lines.append(subline + "```")
                    elif i == len(codelines) - 1:
                        lines.append("```" + subline)
                    else:
                        lines.append("```" + subline + "```")
        else:
            lines += chat_formatting.pagify(line)

    return lines

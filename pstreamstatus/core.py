import discord
from redbot.core import commands
from discord.ext import tasks
import aiohttp
import asyncio
import platform
from datetime import datetime
import re

CLOUDFLARE_STATUS_URL = "https://www.cloudflarestatus.com/api/v2/components.json"
BACKEND_HOST = "server.fifthwit.net"
WEBLATE_HOST = "weblate.pstream.org"
FEED_REGIONS = [
    ("Asia", "fed-api-asia.pstream.org/status/data"),
    ("East", "fed-api-east.pstream.org/status/data"),
    ("Europe", "fed-api-europe.pstream.org/status/data"),
    ("South", "fed-api-south.pstream.org/status/data"),
    ("West", "fed-api-west.pstream.org/status/data"),
]

class PStreamStatus(commands.Cog):
    """Check Cloudflare, backend, weblate, and feed statuses periodically."""

    def __init__(self, bot):
        self.bot = bot
        self.last_message = None  # (channel_id, message_id)
        self.channel_id = 1385316685850083471  # Default channel
        self.status_loop.start()

    def cog_unload(self):
        self.status_loop.cancel()

    async def get_cloudflare_status(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(CLOUDFLARE_STATUS_URL) as resp:
                data = await resp.json()
                components = data.get("components", [])
                wanted = ["Pages", "Access", "API"]
                status = {}
                for comp in components:
                    name = comp.get("name")
                    if name in wanted:
                        status[name] = comp.get("status")
                return status

    async def check_weblate_status(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://{WEBLATE_HOST}", timeout=5) as resp:
                    if resp.status == 403:
                        return "Down", None
                    if resp.status == 200:
                        return "Operational", None
                    return "Down", None
        except Exception:
            return "Down", None

    async def ping_host(self, host):
        count_flag = "-n" if platform.system().lower() == "windows" else "-c"
        try:
            process = await asyncio.create_subprocess_exec(
                "ping", count_flag, "1", host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            output = stdout.decode()

            if process.returncode == 0:
                if "time=" in output:
                    time_part = output.split("time=")[-1].split()[0]
                    time_ms = float(time_part.replace("ms", "").replace("<", "").strip())
                    if time_ms < 100:
                        return "Operational", time_ms
                    else:
                        return "Degraded", time_ms
                return "Operational", None
            return "Down", None
        except Exception:
            return "Down", None

    async def get_feed_statuses(self):
        results = {}
        async with aiohttp.ClientSession() as session:
            for name, url in FEED_REGIONS:
                try:
                    async with session.get(f"https://{url}", timeout=5) as resp:
                        data = await resp.json()
                        results[name] = data
                except Exception:
                    results[name] = {"failed": "N/A", "succeeded": "N/A", "total": "N/A"}
        return results

    def create_embed(self, cf_status, backend_status, weblate_status, feed_statuses):
        embed = discord.Embed(
            title="Platform Status",
            color=discord.Color.blue()
        )

        for name in ["Pages", "Access", "API"]:
            status = cf_status.get(name, "Unknown")
            emoji = "🟢" if status == "operational" else "🔴"
            embed.add_field(name=f"Cloudflare {name}", value=f"{emoji} {status.title()}", inline=True)

        b_status, b_ping = backend_status
        b_emoji = "🟢" if b_status == "Operational" else "🟠" if b_status == "Degraded" else "🔴"
        backend_display = f"{b_emoji} {b_status}"
        if b_ping:
            backend_display += f" ({b_ping:.1f} ms)"
        embed.add_field(name="Backend", value=backend_display, inline=True)

        w_status, w_ping = weblate_status
        w_emoji = "🟢" if w_status == "Operational" else "🟠" if w_status == "Degraded" else "🔴"
        weblate_display = f"{w_emoji} {w_status}"
        embed.add_field(name="Weblate", value=weblate_display, inline=True)

        for region, data in feed_statuses.items():
            val = f"❌ Failed: {data['failed']}\n✅ Succeeded: {data['succeeded']}\n📊 Total: {data['total']}"
            embed.add_field(name=f"Feed - {region}", value=val, inline=True)

        embed.set_footer(text=f"Last Checked: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        return embed

    @tasks.loop(minutes=5)
    async def status_loop(self):
        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            return

        cf_status = await self.get_cloudflare_status()
        backend_status = await self.ping_host(BACKEND_HOST)
        weblate_status = await self.check_weblate_status()
        feed_statuses = await self.get_feed_statuses()
        embed = self.create_embed(cf_status, backend_status, weblate_status, feed_statuses)

        if self.last_message:
            try:
                old_channel = self.bot.get_channel(self.last_message[0])
                old_msg = await old_channel.fetch_message(self.last_message[1])
                await old_msg.delete()
            except Exception:
                pass

        msg = await channel.send(embed=embed)
        self.last_message = (channel.id, msg.id)

    @commands.group()
    async def pstreamstatus(self, ctx):
        """Status command group."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `pstreamstatus refresh` or `pstreamstatus channel <channel_id>`.")

    @pstreamstatus.command()
    async def refresh(self, ctx):
        """Manually trigger a one-time status check and send embed."""
        cf_status = await self.get_cloudflare_status()
        backend_status = await self.ping_host(BACKEND_HOST)
        weblate_status = await self.check_weblate_status()
        feed_statuses = await self.get_feed_statuses()
        embed = self.create_embed(cf_status, backend_status, weblate_status, feed_statuses)
        await ctx.send(embed=embed)

    @pstreamstatus.command()
    async def channel(self, ctx, new_channel_id: int):
        """Set the channel ID to post automatic updates."""
        self.channel_id = new_channel_id
        await ctx.send(f"✅ Channel ID set to `{new_channel_id}` for future updates.")

def setup(bot):
    bot.add_cog(PStreamStatus(bot))

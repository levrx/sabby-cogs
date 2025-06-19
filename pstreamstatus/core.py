import discord
from redbot.core import commands
from discord.ext import tasks
import aiohttp
import asyncio
import platform
from datetime import datetime
import re
import json

CLOUDFLARE_STATUS_URL = "https://www.cloudflarestatus.com/api/v2/components.json"
BACKEND_HOST = "server.fifthwit.net"
WEBLATE_HOST = "weblate.pstream.org"
FEED_REGIONS = [
    ("Asia", "https://fed-api-asia.pstream.org/status/data"),
    ("East", "https://fed-api-east.pstream.org/status/data"),
    ("Europe", "https://fed-api-europe.pstream.org/status/data"),
    ("South", "https://fed-api-south.pstream.org/status/data"),
    ("West", "https://fed-api-west.pstream.org/status/data"),
]

class PStreamStatus(commands.Cog):
    """Check Cloudflare, backend, weblate, and feed statuses periodically."""

    def __init__(self, bot):
        self.bot = bot
        self.last_message = None  # (channel_id, message_id)
        self.channel_obj = None  # discord.TextChannel
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

    async def get_feed_statuses(self, raw=False):
        results = {}
        debug_info = {}
        async with aiohttp.ClientSession() as session:
            for name, url in FEED_REGIONS:
                try:
                    async with session.get(url, timeout=5) as resp:
                        text = await resp.text()
                        try:
                            data = json.loads(text)
                            results[name] = data
                            debug_info[name] = data
                        except json.JSONDecodeError:
                            results[name] = {"failed": "N/A", "succeeded": "N/A", "total": "N/A"}
                            debug_info[name] = text
                except Exception as e:
                    results[name] = {"failed": "N/A", "succeeded": "N/A", "total": "N/A"}
                    debug_info[name] = str(e)

        if raw:
            return debug_info
        return results

    def create_embeds(self, cf_status, backend_status, weblate_status, feed_statuses):
        embed_main = discord.Embed(
            title="🌐 Platform Status",
            color=discord.Color.blurple()
        )

        for name in ["Pages", "Access", "API"]:
            status = cf_status.get(name, "Unknown")
            emoji = "🟢" if status == "operational" else "🔴"
            embed_main.add_field(name=f"Cloudflare {name}", value=f"{emoji} {status.title()}", inline=True)

        b_status, b_ping = backend_status
        b_emoji = "🟢" if b_status == "Operational" else "🟠" if b_status == "Degraded" else "🔴"
        backend_display = f"{b_emoji} {b_status}"
        if b_ping:
            backend_display += f" ({b_ping:.1f} ms)"
        embed_main.add_field(name="Backend", value=backend_display, inline=True)

        w_status, _ = weblate_status
        w_emoji = "🟢" if w_status == "Operational" else "🟠" if w_status == "Degraded" else "🔴"
        embed_main.add_field(name="Weblate", value=f"{w_emoji} {w_status}", inline=True)

        embed_feeds = discord.Embed(
            title="Feed Statuses",
            color=discord.Color.green()
        )
        for region, data in feed_statuses.items():
            val = (
                f"❌ **Failed**: `{data['failed']}`\n"
                f"✅ **Succeeded**: `{data['succeeded']}`\n"
                f"📊 **Total**: `{data['total']}`"
            )
            embed_feeds.add_field(name=f"Feed - {region}", value=val, inline=True)

        embed_main.set_footer(text=f"Last Checked: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        return embed_main, embed_feeds

    @tasks.loop(minutes=5)
    async def status_loop(self):
        if not self.channel_obj:
            return
        await self.send_or_update_status()

    async def send_or_update_status(self):
        cf_status = await self.get_cloudflare_status()
        backend_status = await self.ping_host(BACKEND_HOST)
        weblate_status = await self.check_weblate_status()
        feed_statuses = await self.get_feed_statuses()
        embed_main, embed_feeds = self.create_embeds(cf_status, backend_status, weblate_status, feed_statuses)

        # Send or update both embeds
        if self.last_message:
            try:
                old_msg_main = await self.channel_obj.fetch_message(self.last_message[1])
                old_msg_feeds = await self.channel_obj.fetch_message(self.last_message[2])
                await old_msg_main.edit(embed=embed_main)
                await old_msg_feeds.edit(embed=embed_feeds)
                return
            except Exception:
                pass

        msg_main = await self.channel_obj.send(embed=embed_main)
        msg_feeds = await self.channel_obj.send(embed=embed_feeds)
        self.last_message = (self.channel_obj.id, msg_main.id, msg_feeds.id)

    @commands.group(invoke_without_command=True)
    async def pstreamstatus(self, ctx):
        """PStreamStatus commands."""
        await ctx.send_help()

    @pstreamstatus.command(name="refresh")
    async def refresh_status(self, ctx):
        """Manually refresh and update the status message in the set channel."""
        if not self.channel_obj:
            await ctx.send("❌ You must set a channel first using `-pstreamstatus channel #channel-name`.")
            return
        await self.send_or_update_status()
        await ctx.tick()

    @pstreamstatus.command(name="channel")
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Set the status output channel."""
        self.channel_obj = channel
        await ctx.send(f"✅ Status messages will now be posted and updated in {channel.mention}.")

    @pstreamstatus.command(name="debugfeeds")
    async def debug_feeds(self, ctx):
        """Show status and raw JSON from each feed API."""
        raw = await self.get_feed_statuses(raw=True)
        statuses = []
        json_embeds = []

        for region, data in raw.items():
            if isinstance(data, dict):
                failed = data.get("failed", "N/A")
                succeeded = data.get("succeeded", "N/A")
                total = data.get("total", "N/A")
                statuses.append(
                    f"**{region}**\n❌ Failed: `{failed}`\n✅ Succeeded: `{succeeded}`\n📊 Total: `{total}`"
                )
                json_str = json.dumps(data, indent=2)
            else:
                statuses.append(f"**{region}**\nCould not parse JSON.")
                json_str = str(data)
            if len(json_str) > 1000:
                json_str = json_str[:1000] + "\n...truncated..."
            embed = discord.Embed(
                title=f"Raw JSON for {region}",
                description=f"```json\n{json_str}\n```",
                color=discord.Color.orange()
            )
            json_embeds.append(embed)

        # Send API status embed
        status_embed = discord.Embed(
            title="Feed API Status",
            description="\n\n".join(statuses),
            color=discord.Color.green()
        )
        await ctx.send(embed=status_embed)

        # Send each JSON embed separately to avoid hitting limits
        for embed in json_embeds:
            await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(PStreamStatus(bot))

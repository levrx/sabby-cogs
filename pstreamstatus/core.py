import discord
from redbot.core import commands
from discord.ext import tasks
import aiohttp
import asyncio
import platform
from datetime import datetime
import re
import json
import io

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
    STATE_FILE = "status_state.json"

    def save_state(self):
        data = {
            "channel_id": self.channel_obj.id if self.channel_obj else None,
            "last_message": self.last_message,
            "last_fedapi_message": getattr(self, "last_fedapi_message", None),
        }
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def load_state(self):
        try:
            with open(self.STATE_FILE, "r") as f:
                data = json.load(f)
            channel_id = data.get("channel_id")
            if channel_id:
                self.channel_obj = self.bot.get_channel(channel_id)
            self.last_message = data.get("last_message")
            self.last_fedapi_message = data.get("last_fedapi_message")
        except Exception:
            pass
    """Check Cloudflare, backend, weblate, and feed statuses periodically."""

    def __init__(self, bot):
        self.bot = bot
        self.last_message = None  # (channel_id, message_id) for main embed
        self.last_fedapi_message = None  # (channel_id, message_id) for fedapi embed
        self.channel_obj = None  # discord.TextChannel
        self.show_fedapi = True
        self.load_state()
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
                        json_data = await resp.json()
                        results[name] = {
                            "total": json_data.get("total", "N/A"),
                            "succeeded": json_data.get("succeeded", "N/A"),
                            "failed": json_data.get("failed", "N/A"),
                        }
                        debug_info[name] = json.dumps(json_data, indent=2)
                except Exception as e:
                    results[name] = {"failed": "N/A", "succeeded": "N/A", "total": "N/A"}
                    debug_info[name] = str(e)
        if raw:
            return debug_info
        return results

    def create_embed(self, cf_status, backend_status, weblate_status):
        now = int(datetime.utcnow().timestamp())
        embed = discord.Embed(
            title="🌐 Platform Status",
            description=f"**Last Checked:** <t:{now}:F>",
            color=discord.Color.blurple()
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

        w_status, _ = weblate_status
        w_emoji = "🟢" if w_status == "Operational" else "🟠" if w_status == "Degraded" else "🔴"
        embed.add_field(name="Weblate", value=f"{w_emoji} {w_status}", inline=True)

        return embed

    def create_fedapi_embed(self, feed_statuses):
        now = int(datetime.utcnow().timestamp())
        embed = discord.Embed(
            title="FED API Status",
            description=f"**Last Checked:** <t:{now}:F>",
            color=discord.Color.green()
        )
        for region, data in feed_statuses.items():
            val = (
                f"❌ **Failed**: `{data['failed']}`\n"
                f"✅ **Succeeded**: `{data['succeeded']}`\n"
                f"📊 **Total**: `{data['total']}`"
            )
            embed.add_field(name=f"{region}", value=val, inline=True)
        return embed

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

        # Main embed
        embed = self.create_embed(cf_status, backend_status, weblate_status)
        if self.last_message:
            try:
                old_msg = await self.channel_obj.fetch_message(self.last_message[1])
                await old_msg.edit(embed=embed)
            except Exception:
                msg = await self.channel_obj.send(embed=embed)
                self.last_message = (self.channel_obj.id, msg.id)
        else:
            msg = await self.channel_obj.send(embed=embed)
            self.last_message = (self.channel_obj.id, msg.id)

        # FedAPI embed
        if self.show_fedapi:
            fedapi_embed = self.create_fedapi_embed(feed_statuses)
            if getattr(self, "last_fedapi_message", None):
                try:
                    old_fedapi_msg = await self.channel_obj.fetch_message(self.last_fedapi_message[1])
                    await old_fedapi_msg.edit(embed=fedapi_embed)
                except Exception:
                    fedapi_msg = await self.channel_obj.send(embed=fedapi_embed)
                    self.last_fedapi_message = (self.channel_obj.id, fedapi_msg.id)
            else:
                fedapi_msg = await self.channel_obj.send(embed=fedapi_embed)
                self.last_fedapi_message = (self.channel_obj.id, fedapi_msg.id)
        else:
            # If disabled, try to delete the old fedapi message
            if getattr(self, "last_fedapi_message", None):
                try:
                    old_fedapi_msg = await self.channel_obj.fetch_message(self.last_fedapi_message[1])
                    await old_fedapi_msg.delete()
                except Exception:
                    pass
                self.last_fedapi_message = None

        # Save state after updating messages
        self.save_state()

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
        self.save_state()
        await ctx.send(f"✅ Status messages will now be posted and updated in {channel.mention}.")

    @pstreamstatus.command(name="debugfeeds")
    async def debug_feeds(self, ctx):
        """Show status and raw response from each feed API as a file."""
        raw = await self.get_feed_statuses(raw=True)
        statuses = []

        for region, data in raw.items():
            # If data is not a string, convert it
            if not isinstance(data, str):
                data = str(data)
            # Prepare a summary for the status embed
            total = re.search(r"Total\s*Request(?:s)?:?\s*(\d+)", data, re.I)
            succeeded = re.search(r"Succeeded:?\s*(\d+)", data, re.I)
            failed = re.search(r"Failed:?\s*(\d+)", data, re.I)
            statuses.append(
                f"**{region}**\n"
                f"❌ Failed: `{failed.group(1) if failed else 'N/A'}`\n"
                f"✅ Succeeded: `{succeeded.group(1) if succeeded else 'N/A'}`\n"
                f"📊 Total: `{total.group(1) if total else 'N/A'}`"
            )
            # Send the full raw response as a file
            file = discord.File(fp=io.BytesIO(data.encode()), filename=f"{region}_feed_status.txt")
            await ctx.send(f"Raw response for **{region}**:", file=file)

        # Send a summary embed
        status_embed = discord.Embed(
            title="FED API Status",
            description="\n\n".join(statuses),
            color=discord.Color.green()
        )
        await ctx.send(embed=status_embed)

    @pstreamstatus.command(name="debug")
    async def debug_feed(self, ctx, region: str):
        """Show status and raw response from a specific feed API as a file. Example: -pstreamstatus debug Asia"""
        region = region.capitalize()
        valid_regions = [name for name, _ in FEED_REGIONS]
        if region not in valid_regions:
            msg = await ctx.send(f"❌ Invalid region. Valid regions: {', '.join(valid_regions)}")
            await msg.delete(delay=60)
            return

        raw = await self.get_feed_statuses(raw=True)
        data = raw.get(region)
        if data is None:
            msg = await ctx.send(f"❌ No data found for {region}.")
            await msg.delete(delay=60)
            return

        # Parse JSON string to dict
        try:
            json_data = json.loads(data)
            failed = json_data.get("failed", "N/A")
            succeeded = json_data.get("succeeded", "N/A")
            total = json_data.get("total", "N/A")
        except Exception:
            failed = succeeded = total = "N/A"

        summary = (
            f"**{region}**\n"
            f"❌ Failed: `{failed}`\n"
            f"✅ Succeeded: `{succeeded}`\n"
            f"📊 Total: `{total}`"
        )

        file = discord.File(fp=io.BytesIO(data.encode()), filename=f"{region}_feed_status.txt")
        msg = await ctx.send(summary, file=file)
        await msg.delete(delay=60)

    @pstreamstatus.command(name="disablefedapi")
    async def disable_fedapi(self, ctx):
        """Disable the Fed-Api Status embed."""
        self.show_fedapi = False
        await ctx.send("🛑 Fed-Api Status embed is now **disabled**.")
        await self.send_or_update_status()

    @pstreamstatus.command(name="enablefedapi")
    async def enable_fedapi(self, ctx):
        """Enable the Fed-Api Status embed."""
        self.show_fedapi = True
        await ctx.send("✅ Fed-Api Status embed is now **enabled**.")
        await self.send_or_update_status()


def setup(bot):
    bot.add_cog(PStreamStatus(bot))

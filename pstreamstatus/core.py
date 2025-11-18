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
from redbot.core import Config

CLOUDFLARE_STATUS_URL = "https://www.cloudflarestatus.com/api/v2/components.json"
CLOUDFLARE_API_URL = "https://www.cloudflarestatus.com/api/v2/status.json" # grabs if their is an issue or if its all A-OK
CLOUDFLARE_API_MESSAGE_ID = ""
BACKEND_HOST = "server.fifthwit.net"
WEBLATE_HOST = "weblate.pstream.mov"
FEED_REGIONS = [
    ("FED API", "https://fed-api.pstream.mov/status/data"),
    ("CIA API", "https://server.fifthwit.net/metrics"),
]

class PStreamStatus(commands.Cog):

    def log_debug(self, msg):
        print(f"[PStreamStatus DEBUG] {msg}")

    config: Config

    async def save_state(self):
        if not self.channel_obj:
            self.log_debug("save_state called but self.channel_obj is None. State will NOT be saved to avoid overwriting with nulls.")
            return
        self.log_debug(f"Saving state: channel_obj={getattr(self.channel_obj, 'id', None)}, last_message={self.last_message}, last_fedapi_message={getattr(self, 'last_fedapi_message', None)}")
        await self.config.channel_id.set(self.channel_obj.id)
        await self.config.last_message.set(self.last_message)
        await self.config.last_fedapi_message.set(getattr(self, "last_fedapi_message", None))
        await self.config.cfapi_message.set(getattr(self, "cfapi_message", None))

    async def load_state(self):
        try:
            channel_id = await self.config.channel_id()  # int or None
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except Exception as e:
                        self.log_debug(f"Failed to fetch channel {channel_id}: {e}")
                        channel = None
                if channel is None:
                    self.log_debug(f"Channel {channel_id} could not be found or fetched. self.channel_obj will remain None.")
                else:
                    self.channel_obj = channel
                    self.log_debug(f"Loaded channel_obj: {getattr(self.channel_obj, 'id', None)}")
            else:
                self.log_debug("No channel_id found in config.")
            self.last_message = await self.config.last_message()
            self.last_fedapi_message = await self.config.last_fedapi_message()
            self.log_debug(f"Loaded last_message: {self.last_message}, last_fedapi_message: {self.last_fedapi_message}")
            self.cfapi_message = await self.config.cfapi_message()
            self.log_debug(f"Loaded cfapi_message: {self.cfapi_message}")

        except Exception as e:
            self.log_debug(f"Failed to load state: {e}")
    """Check Cloudflare, backend, weblate, and feed statuses periodically."""

    def __init__(self, bot):
        self.bot = bot
        self.last_message = None  # (channel_id, message_id) for main embed
        self.last_fedapi_message = None  # (channel_id, message_id) for fedapi embed
        self.channel_obj = None  # discord.TextChannel
        self.show_fedapi = True
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_global(channel_id=None, last_message=None, last_fedapi_message=None, cfapi_message=None)
        # Do not start status_loop or load_state here

    async def cog_load(self):
        await self.load_state()
        self.status_loop.start()

    def cog_unload(self):
        self.log_debug("cog_unload called. Not saving state to avoid overwriting with nulls.")
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

    async def check_cfapi_status(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(CLOUDFLARE_API_URL, timeout=5) as resp:
                    if resp.status != 200:
                        return "Unknown", "Unable to fetch status"
                    data = await resp.json()
                    status = data.get("status", {})
                    indicator = status.get("indicator", "Unknown")
                    description = status.get("description", "No description available")
                    return indicator, description
        except Exception as e:
            self.log_debug(f"Failed to check Cloudflare API status: {e}")
            return "Unknown", "Error occurred while fetching status"

    async def handle_cfapi_status(self, cfapi_status):
        """Send or update the Cloudflare API status embed."""
        indicator, description = cfapi_status

        # Create the embed no matter what
        if indicator != "none":
            embed = discord.Embed(
                title="⚠️ Cloudflare Issue Detected",
                description=f"**Status:** {indicator.title()}\n**Description:** {description}",
                color=discord.Color.red()
            )
        else:
            embed = None  # Clear means delete

        # CASE 1 — delete if no issue
        if indicator == "none":
            if self.cfapi_message:
                try:
                    old = await self.channel_obj.fetch_message(self.cfapi_message[1])
                    await old.delete()
                    self.log_debug(f"Deleted CFAPI message {self.cfapi_message[1]}")
                except Exception as e:
                    self.log_debug(f"Unable to delete CFAPI message: {e}")
                self.cfapi_message = None
                await self.save_state()
            return

        # CASE 2 — new message
        if not self.cfapi_message:
            msg = await self.channel_obj.send(embed=embed)
            self.cfapi_message = (self.channel_obj.id, msg.id)
            self.log_debug(f"Sent new CFAPI message {msg.id}")
            await self.save_state()
            return

        # CASE 3 — update old message
        try:
            old = await self.channel_obj.fetch_message(self.cfapi_message[1])
            await old.edit(embed=embed)
            self.log_debug(f"Updated CFAPI message {self.cfapi_message[1]}")
        except Exception as e:
            self.log_debug(f"Could not edit CFAPI message: {e}")
            msg = await self.channel_obj.send(embed=embed)
            self.cfapi_message = (self.channel_obj.id, msg.id)
            self.log_debug(f"Resent CFAPI message {msg.id}")

        await self.save_state()


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
                        text_data = await resp.text()

                        if name == "CIA API":
                            # Parse providers metrics
                            succeeded = failed = 0
                            for line in text_data.splitlines():
                                if 'mw_provider_status_count{provider_id="cia-api",status="success"}' in line:
                                    try:
                                        succeeded = int(line.split()[-1])
                                    except ValueError:
                                        succeeded = 0
                                elif 'mw_provider_status_count{provider_id="cia-api",status="failed"}' in line:
                                    try:
                                        failed = int(line.split()[-1])
                                    except ValueError:
                                        failed = 0
                            total = succeeded + failed

                            # Ping a separate endpoint (placeholder for now)
                            ping_status, _ = await self.ping_host("febbox.andresdev.org")

                            results[name] = {
                                "succeeded": succeeded,
                                "failed": failed,
                                "total": total,
                                "ping_status": ping_status,
                            }
                            debug_info[name] = text_data

                        else:  # FED API
                            json_data = await resp.json()

                            # Ping the actual feed endpoint
                            ping_status, _ = await self.ping_host("fed-api.pstream.mov")

                            results[name] = {
                                "total": json_data.get("total", "N/A"),
                                "succeeded": json_data.get("succeeded", "N/A"),
                                "failed": json_data.get("failed", "N/A"),
                                "ping_status": ping_status,
                            }
                            debug_info[name] = json.dumps(json_data, indent=2)

                except Exception as e:
                    results[name] = {
                        "failed": "N/A",
                        "succeeded": "N/A",
                        "total": "N/A",
                        "ping_status": "Down",
                    }
                    debug_info[name] = str(e)

        return debug_info if raw else results

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
            title="API Status",
            description=f"**Last Checked:** <t:{now}:F>",
            color=discord.Color.green()
        )
        for region, data in feed_statuses.items():
            ping_status = data.get("ping_status", "Unknown")
            if ping_status == "Operational":
                status_text = "Online"
                emoji = "🟢"
            elif ping_status == "Degraded":
                status_text = "Degraded"
                emoji = "🟠"
            else:
                status_text = "Offline"
                emoji = "🔴"

            val = (
                f"❌ **Failed**: `{data['failed']}`\n"
                f"✅ **Succeeded**: `{data['succeeded']}`\n"
                f"📊 **Total**: `{data['total']}`\n"
                f"📡 **Status**: {emoji} {status_text}"
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
        cfapi_status = await self.check_cfapi_status()

        # Main embed
        embed = self.create_embed(cf_status, backend_status, weblate_status)
        if self.last_message:
            try:
                old_msg = await self.channel_obj.fetch_message(self.last_message[1])
                await old_msg.edit(embed=embed)
                self.log_debug(f"Edited main embed message {self.last_message[1]}")
            except Exception as e:
                self.log_debug(f"Failed to edit main embed message {self.last_message[1]}: {e}")
                msg = await self.channel_obj.send(embed=embed)
                self.last_message = (self.channel_obj.id, msg.id)
                self.log_debug(f"Sent new main embed message {msg.id}")
        else:
            msg = await self.channel_obj.send(embed=embed)
            self.last_message = (self.channel_obj.id, msg.id)
            self.log_debug(f"Sent new main embed message {msg.id}")

        # FedAPI embed
        if self.show_fedapi:
            fedapi_embed = self.create_fedapi_embed(feed_statuses)
            if getattr(self, "last_fedapi_message", None):
                try:
                    old_fedapi_msg = await self.channel_obj.fetch_message(self.last_fedapi_message[1])
                    await old_fedapi_msg.edit(embed=fedapi_embed)
                    self.log_debug(f"Edited fedapi embed message {self.last_fedapi_message[1]}")
                except Exception as e:
                    self.log_debug(f"Failed to edit fedapi embed message {self.last_fedapi_message[1]}: {e}")
                    fedapi_msg = await self.channel_obj.send(embed=fedapi_embed)
                    self.last_fedapi_message = (self.channel_obj.id, fedapi_msg.id)
                    self.log_debug(f"Sent new fedapi embed message {fedapi_msg.id}")
            else:
                fedapi_msg = await self.channel_obj.send(embed=fedapi_embed)
                self.last_fedapi_message = (self.channel_obj.id, fedapi_msg.id)
                self.log_debug(f"Sent new fedapi embed message {fedapi_msg.id}")
        else:
            # If disabled, try to delete the old fedapi message
            if getattr(self, "last_fedapi_message", None):
                try:
                    old_fedapi_msg = await self.channel_obj.fetch_message(self.last_fedapi_message[1])
                    await old_fedapi_msg.delete()
                    self.log_debug(f"Deleted fedapi embed message {self.last_fedapi_message[1]}")
                except Exception as e:
                    self.log_debug(f"Failed to delete fedapi embed message {self.last_fedapi_message[1]}: {e}")
                self.last_fedapi_message = None

        # Save state after updating messages
        await self.handle_cfapi_status(cfapi_status)
        await self.save_state()

    @commands.group(invoke_without_command=True)
    async def pstreamstatus(self, ctx):
        """PStreamStatus commands."""
        await ctx.send_help()

    @pstreamstatus.command(name="debugstate")
    async def debug_state(self, ctx):
        """Show the current saved state for debugging."""
        state = {
            "channel_id": getattr(self.channel_obj, "id", None),
            "last_message": self.last_message,
            "last_fedapi_message": getattr(self, "last_fedapi_message", None),
        }
        await ctx.send(f"Current state: ```{json.dumps(state, indent=2)}```")

    @commands.group(invoke_without_command=True)
    async def pstreamstatus(self, ctx):
        """PStreamStatus commands."""
        await ctx.send_help()

    @pstreamstatus.command(name="refresh")
    async def refresh_status(self, ctx):
        """Manually refresh and update the status message in the set channel."""
        if not self.channel_obj:
            await ctx.send("❌ No valid channel is set or the channel could not be found. Please use `-pstreamstatus channel #channel-name` to set a valid channel.")
            self.log_debug("refresh_status called but self.channel_obj is None. State may not have loaded or channel is invalid.")
            return
        await self.send_or_update_status()
        await ctx.tick()

    @pstreamstatus.command(name="channel")
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Set the status output channel."""
        self.channel_obj = channel
        await self.save_state()
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
            title="API Status",
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

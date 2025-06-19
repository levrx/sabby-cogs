import discord
from redbot.core import commands, tasks
import aiohttp
import asyncio
import platform
from datetime import datetime

CLOUDFLARE_STATUS_URL = "https://www.cloudflarestatus.com/api/v2/components.json"
BACKEND_HOST = "https://server.fifthwit.net"
WEBLATE_HOST = "https://weblate.pstream.org"

class PStreamStatus(commands.Cog):
    """Check Cloudflare and custom site statuses periodically."""

    def __init__(self, bot):
        self.bot = bot
        self.last_message = None  # (channel_id, message_id)
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

    def create_embed(self, cf_status, backend_status, weblate_status):
        embed = discord.Embed(
            title="Platform Status",
            color=discord.Color.blue()
        )

        # Cloudflare
        for name in ["Pages", "Access", "API"]:
            status = cf_status.get(name, "Unknown")
            emoji = "🟢" if status == "operational" else "🔴"
            embed.add_field(name=f"Cloudflare {name}", value=f"{emoji} {status.title()}", inline=False)

        # Backend
        b_status, b_ping = backend_status
        b_emoji = "🟢" if b_status == "Operational" else "🟠" if b_status == "Degraded" else "🔴"
        backend_display = f"{b_emoji} {b_status}"
        if b_ping:
            backend_display += f" ({b_ping:.1f} ms)"
        embed.add_field(name="Backend", value=backend_display, inline=False)

        # Weblate
        w_status, w_ping = weblate_status
        w_emoji = "🟢" if w_status == "Operational" else "🟠" if w_status == "Degraded" else "🔴"
        weblate_display = f"{w_emoji} {w_status}"
        if w_ping:
            weblate_display += f" ({w_ping:.1f} ms)"
        embed.add_field(name="Weblate", value=weblate_display, inline=False)

        # Last checked
        embed.set_footer(text=f"Last Checked: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        return embed

    @tasks.loop(minutes=5)
    async def status_loop(self):
        channel_id = 1358082543458451676 
        channel = self.bot.get_channel(channel_id)

        if channel is None:
            return

        # Fetch statuses
        cf_status = await self.get_cloudflare_status()
        backend_status = await self.ping_host(BACKEND_HOST)
        weblate_status = await self.ping_host(WEBLATE_HOST)
        embed = self.create_embed(cf_status, backend_status, weblate_status)

        # Delete previous message
        if self.last_message:
            try:
                old_channel = self.bot.get_channel(self.last_message[0])
                old_msg = await old_channel.fetch_message(self.last_message[1])
                await old_msg.delete()
            except Exception:
                pass  # Ignore if message no longer exists

        # Send new message
        msg = await channel.send(embed=embed)
        self.last_message = (channel.id, msg.id)

    @commands.command()
    async def pstreamstatus(self, ctx):
        """Manually trigger a one-time status check and send embed."""
        cf_status = await self.get_cloudflare_status()
        backend_status = await self.ping_host(BACKEND_HOST)
        weblate_status = await self.ping_host(WEBLATE_HOST)
        embed = self.create_embed(cf_status, backend_status, weblate_status)
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(PStreamStatus(bot))

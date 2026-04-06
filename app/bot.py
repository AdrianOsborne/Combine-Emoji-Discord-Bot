
import os
import time
from collections import defaultdict, deque
from io import BytesIO

import aiohttp
import discord

from donations import DonateView, build_donate_embed
from emoji_fetcher import fetch_unicode_emoji_image
from pair_utils import extract_single_unicode_emoji, canonicalize_pair
from renderer import render_pair

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
APPLICATION_ID = os.getenv("DISCORD_APPLICATION_ID")

RATE_LIMIT_USES = int(os.getenv("RATE_LIMIT_USES", "5"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "30"))

if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set.")

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

usage_stats = {
    "emoji_requests_total": 0,
    "donate_requests_total": 0,
    "errors_total": 0,
    "started_at": int(time.time()),
}

user_request_times = defaultdict(deque)

def invite_url(client_id: str) -> str:
    perms = 2147534848
    return (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={client_id}"
        f"&scope=bot%20applications.commands"
        f"&permissions={perms}"
    )

def check_rate_limit(user_id: int):
    now = time.time()
    bucket = user_request_times[user_id]

    while bucket and (now - bucket[0]) > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_USES:
        retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - bucket[0])) + 1
        return False, retry_after

    bucket.append(now)
    return True, 0

def syntax_embed() -> discord.Embed:
    embed = discord.Embed(
        title="How to use /emoji",
        description=(
            "Use exactly **two standard Unicode emojis**.\n\n"
            "**Example:** `/emoji emoji1: 😎 emoji2: 📜`\n\n"
            "This command does not support custom Discord emojis, multiple emojis in one field, or plain text."
        ),
        color=0xED4245,
    )
    return embed

def result_embed(emoji_a: str, emoji_b: str, pair_key: str) -> discord.Embed:
    embed = discord.Embed(
        title="Your emoji fusion is ready",
        description=f"Pair: {emoji_a} + {emoji_b}",
        color=0x5865F2,
    )
    embed.set_footer(text=f"Stable pair key: {pair_key}")
    return embed

class ResultView(discord.ui.View):
    def __init__(self, image_bytes: bytes):
        super().__init__(timeout=300)
        self.image_bytes = image_bytes

    @discord.ui.button(label="Post to channel", style=discord.ButtonStyle.primary)
    async def post(self, interaction: discord.Interaction, button: discord.ui.Button):
        file = discord.File(BytesIO(self.image_bytes), filename="emoji-fusion.png")
        embed = discord.Embed(
            title="Emoji fusion",
            description="Shared from a private preview.",
            color=0x5865F2,
        )
        embed.set_image(url="attachment://emoji-fusion.png")
        await interaction.response.send_message(embed=embed, file=file)

    @discord.ui.button(label="Donate", style=discord.ButtonStyle.secondary)
    async def donate(self, interaction: discord.Interaction, button: discord.ui.Button):
        usage_stats["donate_requests_total"] += 1
        await interaction.response.send_message(
            embed=build_donate_embed(),
            view=DonateView(),
            ephemeral=True,
        )

@tree.command(name="emoji", description="Fuse exactly two standard emojis into one image")
@discord.app_commands.describe(
    emoji1="First emoji",
    emoji2="Second emoji",
)
async def emoji(interaction: discord.Interaction, emoji1: str, emoji2: str):
    allowed, retry_after = check_rate_limit(interaction.user.id)
    if not allowed:
        embed = discord.Embed(
            title="Slow down a bit",
            description=f"Try again in about {retry_after} seconds.",
            color=0xFAA61A,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    first = extract_single_unicode_emoji(emoji1)
    second = extract_single_unicode_emoji(emoji2)

    if not first or not second:
        await interaction.response.send_message(embed=syntax_embed(), ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        canon_a, canon_b, pair_key = canonicalize_pair(first, second)
        async with aiohttp.ClientSession() as session:
            img_a = await fetch_unicode_emoji_image(session, canon_a)
            img_b = await fetch_unicode_emoji_image(session, canon_b)

        result = render_pair(img_a, img_b, pair_key)
        data = result.getvalue()
        usage_stats["emoji_requests_total"] += 1

        file = discord.File(BytesIO(data), filename="emoji-fusion.png")
        embed = result_embed(canon_a, canon_b, pair_key)
        embed.set_image(url="attachment://emoji-fusion.png")

        await interaction.followup.send(
            embed=embed,
            file=file,
            view=ResultView(data),
            ephemeral=True,
        )
    except Exception as e:
        usage_stats["errors_total"] += 1
        error_embed = discord.Embed(
            title="Fusion failed",
            description=f"{e}",
            color=0xED4245,
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

@tree.command(name="donate", description="Support the project")
async def donate(interaction: discord.Interaction):
    usage_stats["donate_requests_total"] += 1
    await interaction.response.send_message(
        embed=build_donate_embed(),
        view=DonateView(),
        ephemeral=True,
    )

@tree.command(name="stats", description="Show basic bot stats")
async def stats(interaction: discord.Interaction):
    uptime_seconds = int(time.time()) - usage_stats["started_at"]
    invite = invite_url(APPLICATION_ID) if APPLICATION_ID else "Not configured"

    embed = discord.Embed(
        title="Bot stats",
        color=0x57F287,
    )
    embed.add_field(name="Emoji requests", value=str(usage_stats["emoji_requests_total"]), inline=True)
    embed.add_field(name="Donate requests", value=str(usage_stats["donate_requests_total"]), inline=True)
    embed.add_field(name="Errors", value=str(usage_stats["errors_total"]), inline=True)
    embed.add_field(name="Uptime", value=f"{uptime_seconds} seconds", inline=False)
    embed.add_field(name="Invite URL", value=invite, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Bot ready as {bot.user}")
    if APPLICATION_ID:
        print(invite_url(APPLICATION_ID))

bot.run(TOKEN)

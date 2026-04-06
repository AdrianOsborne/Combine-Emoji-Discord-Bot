import os
import re
import time
from collections import defaultdict, deque
from io import BytesIO

import aiohttp
import discord

from composer import compose_emojis
from emoji_fetcher import fetch_emoji_image
from donations import DonateView, MESSAGE

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PUBLIC_BOT_INVITE_CLIENT_ID = os.getenv("DISCORD_APPLICATION_ID")

if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set.")

MAX_EMOJIS = int(os.getenv("MAX_EMOJIS", "6"))
RATE_LIMIT_USES = int(os.getenv("RATE_LIMIT_USES", "5"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "30"))

CUSTOM_EMOJI_RE = re.compile(r"<a?:[A-Za-z0-9_]+:\d+>")

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


def extract_emojis(text: str):
    found = []

    # First extract custom Discord emojis
    for match in CUSTOM_EMOJI_RE.finditer(text):
        found.append((match.start(), match.group(0)))

    # Remove them so they don't interfere with Unicode parsing
    stripped = CUSTOM_EMOJI_RE.sub(" ", text)

    # Basic Unicode emoji handling:
    # skip whitespace, variation selectors, and zero-width joiners on their own
    for idx, ch in enumerate(stripped):
        cp = ord(ch)

        if ch.isspace():
            continue

        if cp in (0xFE0F, 0x200D):
            continue

        # keep broad emoji/symbol ranges
        if (
            0x1F000 <= cp <= 0x1FAFF
            or 0x2600 <= cp <= 0x27BF
            or 0x2300 <= cp <= 0x23FF
        ):
            found.append((100000 + idx, ch))

    found.sort(key=lambda x: x[0])
    return [value for _, value in found]


class ResultView(discord.ui.View):
    def __init__(self, img_bytes: bytes):
        super().__init__(timeout=300)
        self.img_bytes = img_bytes

    @discord.ui.button(label="Post to channel", style=discord.ButtonStyle.primary)
    async def post(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            file=discord.File(BytesIO(self.img_bytes), filename="emoji.png")
        )

    @discord.ui.button(label="Donate", style=discord.ButtonStyle.secondary)
    async def donate(self, interaction: discord.Interaction, button: discord.ui.Button):
        usage_stats["donate_requests_total"] += 1
        await interaction.response.send_message(
            MESSAGE,
            view=DonateView(),
            ephemeral=True,
        )


@tree.command(name="emoji", description="Combine multiple emojis into a single image")
@discord.app_commands.describe(input="Example: 😭💔 or <:blobcry:123456789012345678><:blobheart:123456789012345678>")
async def emoji(interaction: discord.Interaction, input: str):
    allowed, retry_after = check_rate_limit(interaction.user.id)
    if not allowed:
        await interaction.response.send_message(
            f"You're doing that too fast. Try again in about {retry_after} seconds.",
            ephemeral=True,
        )
        return

    emojis = extract_emojis(input)

    if not emojis:
        await interaction.response.send_message(
            "No supported emojis found.",
            ephemeral=True,
        )
        return

    if len(emojis) > MAX_EMOJIS:
        await interaction.response.send_message(
            f"Please use between 1 and {MAX_EMOJIS} emojis.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        async with aiohttp.ClientSession() as session:
            images = [await fetch_emoji_image(session, e) for e in emojis]

        result = compose_emojis(images)
        data = result.getvalue()
        usage_stats["emoji_requests_total"] += 1

        await interaction.followup.send(
            content="Your combined emoji is ready.",
            file=discord.File(BytesIO(data), filename="emoji.png"),
            view=ResultView(data),
            ephemeral=True,
        )

    except Exception as e:
        usage_stats["errors_total"] += 1
        await interaction.followup.send(
            f"Failed to generate image: {e}",
            ephemeral=True,
        )


@tree.command(name="donate", description="Support the emoji bot")
async def donate(interaction: discord.Interaction):
    usage_stats["donate_requests_total"] += 1
    await interaction.response.send_message(
        MESSAGE,
        view=DonateView(),
        ephemeral=True,
    )


@tree.command(name="stats", description="Show basic bot stats")
async def stats(interaction: discord.Interaction):
    uptime_seconds = int(time.time()) - usage_stats["started_at"]
    invite = "Not configured"
    if PUBLIC_BOT_INVITE_CLIENT_ID:
        invite = invite_url(PUBLIC_BOT_INVITE_CLIENT_ID)

    await interaction.response.send_message(
        "Bot stats\n\n"
        f"Emoji requests: `{usage_stats['emoji_requests_total']}`\n"
        f"Donate requests: `{usage_stats['donate_requests_total']}`\n"
        f"Errors: `{usage_stats['errors_total']}`\n"
        f"Uptime: `{uptime_seconds}` seconds\n\n"
        f"Invite URL:\n{invite}",
        ephemeral=True,
    )


@bot.event
async def on_ready():
    await tree.sync()
    print(f"Bot ready as {bot.user}")
    if PUBLIC_BOT_INVITE_CLIENT_ID:
        print("Invite URL:")
        print(invite_url(PUBLIC_BOT_INVITE_CLIENT_ID))
    else:
        print("DISCORD_APPLICATION_ID not set, so invite URL could not be printed.")


bot.run(TOKEN)
import os
import time
from collections import defaultdict, deque
from io import BytesIO

import aiohttp
import discord

from donations import DonateView, build_donate_embed
from emoji_kitchen import ensure_index, fetch_kitchen_image
from pair_utils import extract_single_unicode_emoji, canonicalize_pair, emoji_to_codepoints

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
APPLICATION_ID = os.getenv("DISCORD_APPLICATION_ID")

RATE_LIMIT_USES = int(os.getenv("RATE_LIMIT_USES", "5"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "30"))

if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set.")

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

usage_stats = {
    "emoji_requests_total": 0,
    "donate_requests_total": 0,
    "errors_total": 0,
    "started_at": int(time.time()),
}

user_request_times = defaultdict(deque)


# ---------------- RATE LIMIT ----------------

def check_rate_limit(user_id: int):
    now = time.time()
    bucket = user_request_times[user_id]

    while bucket and (now - bucket[0]) > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_USES:
        return False

    bucket.append(now)
    return True


# ---------------- SUGGESTIONS ----------------

def unsupported_pair_embed(index: dict[str, str], emoji1: str, emoji2: str) -> discord.Embed:
    code1 = emoji_to_codepoints(emoji1)
    code2 = emoji_to_codepoints(emoji2)

    matches = []

    for key in index.keys():
        parts = key.split("__")
        if len(parts) != 2:
            continue

        a, b = parts

        if a == code1:
            matches.append((emoji1, b))
        elif b == code1:
            matches.append((emoji1, a))

        if a == code2:
            matches.append((emoji2, b))
        elif b == code2:
            matches.append((emoji2, a))

    seen = set()
    unique = []
    for base, other in matches:
        if other in seen:
            continue
        seen.add(other)
        unique.append((base, other))

    def to_emoji(code):
        try:
            return "".join(chr(int(p, 16)) for p in code.split("-"))
        except:
            return code

    lines = []
    for base, other in unique[:25]:
        lines.append(f"• {base} + {to_emoji(other)}")

    if not lines:
        text = "That pairing isn't available."
    else:
        text = "That pairing isn't available.\n\nTry:\n" + "\n".join(lines)

    return discord.Embed(description=text, color=0xED4245)


# ---------------- UI ----------------

class ResultView(discord.ui.View):
    def __init__(self, image_bytes: bytes):
        super().__init__(timeout=300)
        self.image_bytes = image_bytes

    @discord.ui.button(label="Post", style=discord.ButtonStyle.primary)
    async def post(self, interaction: discord.Interaction, button: discord.ui.Button):
        file = discord.File(BytesIO(self.image_bytes), filename="emoji.png")
        await interaction.response.send_message(file=file)

    @discord.ui.button(label="Donate", style=discord.ButtonStyle.secondary)
    async def donate(self, interaction: discord.Interaction, button: discord.ui.Button):
        usage_stats["donate_requests_total"] += 1
        await interaction.response.send_message(
            embed=build_donate_embed(),
            view=DonateView(),
            ephemeral=True,
        )


# ---------------- CORE ----------------

async def generate_image(emoji1: str, emoji2: str):
    canon_a, canon_b, pair_key = canonicalize_pair(emoji1, emoji2)

    async with aiohttp.ClientSession() as session:
        index = await ensure_index(session)

        try:
            result = await fetch_kitchen_image(session, canon_a, canon_b)
            return result.getvalue(), canon_a, canon_b, pair_key, index
        except RuntimeError:
            return None, canon_a, canon_b, pair_key, index


# ---------------- SLASH COMMAND ----------------

@tree.command(name="emoji", description="Combine 2 emojis")
async def emoji(interaction: discord.Interaction, emoji1: str, emoji2: str):

    if not check_rate_limit(interaction.user.id):
        await interaction.response.send_message("Slow down", ephemeral=True)
        return

    e1 = extract_single_unicode_emoji(emoji1)
    e2 = extract_single_unicode_emoji(emoji2)

    if not e1 or not e2:
        await interaction.response.send_message("Use exactly 2 emojis", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        data, a, b, key, index = await generate_image(e1, e2)

        if not data:
            await interaction.followup.send(
                embed=unsupported_pair_embed(index, a, b),
                ephemeral=True
            )
            return

        file = discord.File(BytesIO(data), filename="emoji.png")

        usage_stats["emoji_requests_total"] += 1

        await interaction.followup.send(
            file=file,
            view=ResultView(data),
            ephemeral=True
        )

    except Exception:
        usage_stats["errors_total"] += 1
        await interaction.followup.send("Error", ephemeral=True)


# ---------------- DONATE ----------------

@tree.command(name="donate", description="Support")
async def donate(interaction: discord.Interaction):
    usage_stats["donate_requests_total"] += 1
    await interaction.response.send_message(
        embed=build_donate_embed(),
        view=DonateView(),
        ephemeral=True,
    )


# ---------------- DM HANDLER ----------------

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Only DMs
    if not isinstance(message.channel, discord.DMChannel):
        return

    content = message.content.strip()

    emojis = []
    for char in content:
        e = extract_single_unicode_emoji(char)
        if e:
            emojis.append(e)

    if len(emojis) != 2:
        return

    try:
        data, a, b, key, index = await generate_image(emojis[0], emojis[1])

        if not data:
            await message.reply(
                embed=unsupported_pair_embed(index, a, b)
            )
            return

        file = discord.File(BytesIO(data), filename="emoji.png")

        await message.reply(file=file)

    except Exception:
        await message.reply("Error")


# ---------------- READY ----------------

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Bot ready as {bot.user}")


bot.run(TOKEN)
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

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

user_request_times = defaultdict(deque)


# ---------------- RATE LIMIT ----------------

def check_rate_limit(user_id: int):
    now = time.time()
    bucket = user_request_times[user_id]

    while bucket and (now - bucket[0]) > 30:
        bucket.popleft()

    if len(bucket) >= 5:
        return False

    bucket.append(now)
    return True


# ---------------- SUGGESTIONS ----------------

def build_suggestions(index, emoji1, emoji2):
    code1 = emoji_to_codepoints(emoji1)
    code2 = emoji_to_codepoints(emoji2)

    results = []

    for key in index.keys():
        a, b = key.split("__")

        if a == code1:
            results.append((emoji1, b))
        elif b == code1:
            results.append((emoji1, a))

        if a == code2:
            results.append((emoji2, b))
        elif b == code2:
            results.append((emoji2, a))

    # dedupe
    seen = set()
    unique = []
    for base, other in results:
        if other in seen:
            continue
        seen.add(other)
        unique.append((base, other))

    def to_emoji(code):
        try:
            return "".join(chr(int(p, 16)) for p in code.split("-"))
        except:
            return code

    lines = [f"{base} + {to_emoji(other)}" for base, other in unique]

    return lines


def suggestion_embed(lines):
    text = "That pairing isn't available, try one of these supported pairings instead:\n\n"

    # Discord limit ≈ 4096 chars → chunk safely
    chunks = []
    current = ""

    for line in lines:
        if len(current) + len(line) + 1 > 3500:
            chunks.append(current)
            current = ""
        current += line + "\n"

    if current:
        chunks.append(current)

    embeds = []
    for chunk in chunks[:5]:  # hard safety cap
        embeds.append(discord.Embed(description=text + chunk))

    return embeds


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
        await interaction.response.send_message(
            embed=build_donate_embed(),
            view=DonateView(),
            ephemeral=True,
        )


# ---------------- CORE ----------------

async def generate(emoji1, emoji2):
    canon_a, canon_b, _ = canonicalize_pair(emoji1, emoji2)

    async with aiohttp.ClientSession() as session:
        index = await ensure_index(session)

        try:
            result = await fetch_kitchen_image(session, canon_a, canon_b)
            return result.getvalue(), index, canon_a, canon_b
        except:
            return None, index, canon_a, canon_b


# ---------------- SLASH ----------------

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

    await interaction.response.send_message("...", ephemeral=True)

    try:
        data, index, a, b = await generate(e1, e2)

        if not data:
            lines = build_suggestions(index, a, b)
            embeds = suggestion_embed(lines)

            await interaction.edit_original_response(
                content=None,
                embeds=embeds,
                view=DonateView()
            )
            return

        file = discord.File(BytesIO(data), filename="emoji.png")

        await interaction.edit_original_response(
            content=None,
            attachments=[file],
            view=ResultView(data)
        )

    except:
        await interaction.edit_original_response(content="Error")


# ---------------- MESSAGE (DM + MENTION) ----------------

def extract_two(text):
    out = []
    for c in text:
        e = extract_single_unicode_emoji(c)
        if e:
            out.append(e)
    return out


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mention = bot.user in message.mentions

    if not is_dm and not is_mention:
        return

    content = message.content.replace(f"<@{bot.user.id}>", "").strip()

    emojis = extract_two(content)

    if len(emojis) != 2:
        return

    try:
        data, index, a, b = await generate(emojis[0], emojis[1])

        if not data:
            lines = build_suggestions(index, a, b)
            embeds = suggestion_embed(lines)

            for e in embeds:
                await message.reply(embed=e, view=DonateView())
            return

        file = discord.File(BytesIO(data), filename="emoji.png")

        await message.reply(
            file=file,
            view=ResultView(data)
        )

    except:
        await message.reply("Error")


# ---------------- READY ----------------

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Ready as {bot.user}")


bot.run(TOKEN)
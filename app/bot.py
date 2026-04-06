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

def unsupported_pair_embed(index: dict[str, str], emoji1: str, emoji2: str):
    code1 = emoji_to_codepoints(emoji1)
    code2 = emoji_to_codepoints(emoji2)

    matches = []

    for key in index.keys():
        a, b = key.split("__")

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

    lines = [f"{base} + {to_emoji(other)}" for base, other in unique[:20]]

    text = "That pairing isn't available."
    if lines:
        text += "\n\n" + "\n".join(lines)

    return text


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

    # 👇 respond instantly (fixes timeout)
    await interaction.response.send_message("...", ephemeral=True)

    try:
        data, index, a, b = await generate(e1, e2)

        if not data:
            await interaction.edit_original_response(
                content=unsupported_pair_embed(index, a, b)
            )
            return

        file = discord.File(BytesIO(data), filename="emoji.png")

        await interaction.edit_original_response(
            content=None,
            attachments=[file]
        )

    except Exception as e:
        await interaction.edit_original_response(content="Error")


# ---------------- DONATE ----------------

@tree.command(name="donate")
async def donate(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=build_donate_embed(),
        view=DonateView(),
        ephemeral=True
    )


# ---------------- MESSAGE HANDLER ----------------

def extract_two_emojis(text):
    emojis = []
    for char in text:
        e = extract_single_unicode_emoji(char)
        if e:
            emojis.append(e)
    return emojis


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mention = bot.user in message.mentions

    if not is_dm and not is_mention:
        return

    content = message.content.replace(f"<@{bot.user.id}>", "").strip()

    emojis = extract_two_emojis(content)

    if len(emojis) != 2:
        return

    try:
        data, index, a, b = await generate(emojis[0], emojis[1])

        if not data:
            await message.reply(unsupported_pair_embed(index, a, b))
            return

        file = discord.File(BytesIO(data), filename="emoji.png")
        await message.reply(file=file)

    except:
        await message.reply("Error")


# ---------------- READY ----------------

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Ready as {bot.user}")


bot.run(TOKEN)
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


# ---------------- HELP ----------------

def build_help_embed(bot_user: discord.ClientUser):
    embed = discord.Embed(
        description=(
            "**How to use**\n\n"

            "**Slash command**\n"
            "Example: `/emoji emoji1: 😭 emoji2: 🥶`\n\n"

            "**Mention**\n"
            f"Example: `@{bot_user.name} 😭🥶`\n\n"

            "**Direct Message**\n"
            "Example: `😭🥶`\n\n"

            "Use exactly **2 standard emojis only**.\n"
            "Custom Discord emojis are not supported.\n\n"

            "Donations help keep the bot running."
        )
    )

    embed.set_footer(
        text="Tip: Copy the image to share it anywhere"
    )

    return embed


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Donate", style=discord.ButtonStyle.secondary)
    async def donate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=build_donate_embed(),
            view=DonateView(),
            ephemeral=True
        )


# ---------------- SUGGESTIONS ----------------

def build_grouped_suggestions(index, emoji1, emoji2):
    code1 = emoji_to_codepoints(emoji1)
    code2 = emoji_to_codepoints(emoji2)

    groups = {emoji1: [], emoji2: []}

    for key in index.keys():
        a, b = key.split("__")

        if a == code1:
            groups[emoji1].append(b)
        elif b == code1:
            groups[emoji1].append(a)

        if a == code2:
            groups[emoji2].append(b)
        elif b == code2:
            groups[emoji2].append(a)

    def to_emoji(code):
        try:
            return "".join(chr(int(p, 16)) for p in code.split("-"))
        except:
            return code

    for k in groups:
        seen = set()
        cleaned = []
        for code in groups[k]:
            if code in seen:
                continue
            seen.add(code)
            cleaned.append(to_emoji(code))
        groups[k] = cleaned

    return groups


def build_suggestion_embeds(groups):
    header = "That pairing isn't available, try one of these supported pairings instead:\n\n"

    full_text = header

    for base, items in groups.items():
        if not items:
            continue
        full_text += f"{base}\n"
        for i in items:
            full_text += f"{base} + {i}\n"
        full_text += "\n"

    chunks = []
    current = ""

    for line in full_text.split("\n"):
        if len(current) + len(line) + 1 > 3500:
            chunks.append(current)
            current = ""
        current += line + "\n"

    if current:
        chunks.append(current)

    return [discord.Embed(description=c) for c in chunks[:5]]


# ---------------- UI ----------------

class ResultView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Donate", style=discord.ButtonStyle.secondary)
    async def donate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=build_donate_embed(),
            view=DonateView(),
            ephemeral=True
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

    await interaction.response.defer(ephemeral=True)

    try:
        data, index, a, b = await generate(e1, e2)

        if not data:
            embeds = build_suggestion_embeds(build_grouped_suggestions(index, a, b))
            await interaction.edit_original_response(
                content=None,
                embeds=embeds,
                view=DonateView()
            )
            return

        file = discord.File(BytesIO(data), filename="emoji.png")
        embed = discord.Embed()
        embed.set_image(url="attachment://emoji.png")
        embed.set_footer(text="Copy the image to share it")

        await interaction.followup.send(
            embed=embed,
            file=file,
            view=ResultView(),
            ephemeral=True
        )

    except:
        await interaction.edit_original_response(content="Error")


# ---------------- HELP SLASH ----------------

@tree.command(name="help", description="How to use the bot")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=build_help_embed(bot.user),
        view=HelpView(),
        ephemeral=True
    )


# ---------------- MESSAGE ----------------

def extract_two(text):
    return [c for c in text if extract_single_unicode_emoji(c)]


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mention = bot.user in message.mentions

    if not is_dm and not is_mention:
        return

    content = message.content.replace(f"<@{bot.user.id}>", "").strip()
    content_lower = content.lower()

    # HELP
    if content_lower == "help":
        embed = build_help_embed(bot.user)

        if is_mention:
            try:
                await message.delete()
            except:
                pass

            try:
                dm = await message.author.create_dm()
                await dm.send(embed=embed, view=HelpView())
            except:
                pass
            return

        if is_dm:
            await message.channel.send(embed=embed, view=HelpView())
            return

    emojis = extract_two(content)

    if len(emojis) != 2:
        return

    try:
        data, index, a, b = await generate(emojis[0], emojis[1])

        # MENTION → DM
        if is_mention:
            try:
                await message.delete()
            except:
                pass

            try:
                dm = await message.author.create_dm()
            except:
                return

            if not data:
                embeds = build_suggestion_embeds(build_grouped_suggestions(index, a, b))
                for e in embeds:
                    await dm.send(embed=e, view=DonateView())
                return

            file = discord.File(BytesIO(data), filename="emoji.png")
            embed = discord.Embed()
            embed.set_image(url="attachment://emoji.png")
            embed.set_footer(text="Copy the image to share it")

            await dm.send(embed=embed, file=file, view=ResultView())
            return

        # DM FLOW
        if not data:
            embeds = build_suggestion_embeds(build_grouped_suggestions(index, a, b))
            for e in embeds:
                await message.channel.send(embed=e, view=DonateView())
            return

        file = discord.File(BytesIO(data), filename="emoji.png")
        embed = discord.Embed()
        embed.set_image(url="attachment://emoji.png")
        embed.set_footer(text="Copy the image to share it")

        await message.channel.send(embed=embed, file=file, view=ResultView())

    except:
        await message.channel.send("Error")


# ---------------- READY ----------------

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Ready as {bot.user}")


bot.run(TOKEN)
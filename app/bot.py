import os
import aiohttp
import discord
from io import BytesIO

from composer import compose_emojis
from emoji_fetcher import fetch_emoji_image
from donations import DonateView, MESSAGE

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")

if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set.")

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

def extract_emojis(text: str):
    return [c for c in text.strip() if not c.isspace()]

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
        await interaction.response.send_message(
            MESSAGE,
            view=DonateView(),
            ephemeral=True,
        )

@tree.command(name="emoji", description="Combine multiple emojis into a single image")
@discord.app_commands.describe(input="Example: 😭💔🔥")
async def emoji(interaction: discord.Interaction, input: str):
    emojis = extract_emojis(input)

    if not emojis:
        await interaction.response.send_message(
            "No emojis found.",
            ephemeral=True,
        )
        return

    if len(emojis) > 6:
        await interaction.response.send_message(
            "Please use between 1 and 6 emojis.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        async with aiohttp.ClientSession() as session:
            images = [await fetch_emoji_image(session, e) for e in emojis]

        result = compose_emojis(images)
        data = result.getvalue()

        await interaction.followup.send(
            content="Your combined emoji is ready.",
            file=discord.File(BytesIO(data), filename="emoji.png"),
            view=ResultView(data),
            ephemeral=True,
        )

    except Exception as e:
        await interaction.followup.send(
            f"Failed to generate image: {e}",
            ephemeral=True,
        )

@tree.command(name="donate", description="Support the emoji bot")
async def donate(interaction: discord.Interaction):
    await interaction.response.send_message(
        MESSAGE,
        view=DonateView(),
        ephemeral=True,
    )

@bot.event
async def on_ready():
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        await tree.sync(guild=guild)
        print(f"Bot ready in test guild {GUILD_ID}")
    else:
        await tree.sync()
        print("Bot ready globally")

bot.run(TOKEN)

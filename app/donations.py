import os
import discord

PAYPAL = os.getenv("PAYPAL_DONATE_URL")
BTC = os.getenv("BITCOIN_ADDRESS")
BTC_URI = os.getenv("BITCOIN_URI")
MESSAGE = os.getenv(
    "DONATION_MESSAGE",
    "Support the project and help fund hosting costs."
)

class DonateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

        if PAYPAL:
            self.add_item(discord.ui.Button(label="Donate with PayPal", url=PAYPAL))

    @discord.ui.button(label="Show Bitcoin Address", style=discord.ButtonStyle.secondary)
    async def btc(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not BTC:
            await interaction.response.send_message(
                "Bitcoin donations are not configured.",
                ephemeral=True,
            )
            return

        extra = ""
        if BTC_URI:
            extra = f"\n\nBitcoin URI:\n`{BTC_URI}`"

        await interaction.response.send_message(
            f"{MESSAGE}\n\nBitcoin address:\n`{BTC}`{extra}",
            ephemeral=True,
        )
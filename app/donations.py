
import os
import discord

PAYPAL = os.getenv("PAYPAL_DONATE_URL")
BTC = os.getenv("BITCOIN_ADDRESS")
MESSAGE = os.getenv(
    "DONATION_MESSAGE",
    "Support the project and help fund hosting costs."
)

def build_donate_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Support Emoji Combiner",
        description=MESSAGE,
        color=0xF5B301,
    )
    if BTC:
        embed.add_field(
            name="Bitcoin address",
            value=f"```{BTC}```",
            inline=False,
        )
    else:
        embed.add_field(
            name="Bitcoin address",
            value="Not configured.",
            inline=False,
        )
    embed.set_footer(text="Discord does not support a direct text copy button. Select and copy the address above.")
    return embed

class DonateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        if PAYPAL:
            self.add_item(discord.ui.Button(label="Donate with PayPal", url=PAYPAL))

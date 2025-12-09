import os
import asyncio
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv("TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID") or 0)

if not TOKEN:
    raise SystemExit("ERROR: TOKEN tidak ditemukan. Isi TOKEN di file .env pada root project Anda.")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, application_id=None)

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Menampilkan semua perintah moderasi")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Help - Moderation Commands", color=discord.Color.blurple())
        tree = self.bot.tree
        for cmd in tree.walk_commands():
            if isinstance(cmd, app_commands.Command):
                embed.add_field(name=f"/{cmd.name}", value=cmd.description or "—", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def load_cogs():
    for filename in os.listdir(os.path.join(os.path.dirname(__file__), "cogs")):
        if not filename.endswith(".py"):
            continue
        ext = f"cogs.{filename[:-3]}"
        try:
            await bot.load_extension(ext)
            print(f"Loaded extension {ext}")
        except Exception as e:
            print(f"Failed to load extension {ext}: {e}")

@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user} (ID: {bot.user.id})")
    try:
        await bot.tree.sync()
        print("Command tree synced.")
    except Exception as e:
        print("Failed to sync tree:", e)

async def main():
    async with bot:
        
        await load_cogs()
        await bot.add_cog(HelpCog(bot))
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
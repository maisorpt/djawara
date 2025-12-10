# cogs/log_config.py
import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import datetime
import os
import pytz


CONFIG_FILE = "config.json"
LOG_EXPIRY_DAYS = 7

# --- HELPER FUNCTIONS (JSON) ---

def load_config():
    """Memuat konfigurasi dari file JSON."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(config):
    """Menyimpan konfigurasi ke file JSON."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def get_log_channel_id(guild_id: int) -> int | None:
    """Mendapatkan ID channel log untuk guild tertentu."""
    config = load_config()
    return int(config.get(str(guild_id))) if str(guild_id) in config else None

# --- COG CLASS ---

class LogConfig(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log_cleanup_task.start()

    def cog_unload(self):
        self.log_cleanup_task.cancel()
        
    # --- COMMAND: /setlogchannel ---
    @app_commands.command(name="setlogchannel", description="Set channel log")
    @app_commands.default_permissions(administrator=True) 
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        
        guild_id = str(interaction.guild_id)
        config = load_config()
        
        config[guild_id] = channel.id
        save_config(config)
        
        await interaction.response.send_message(
            f"✅ Channel log moderasi berhasil diatur ke {channel.mention}.",
            ephemeral=False
        )
    
    # --- COMMAND: /resetlogchannel ---
    @app_commands.command(name="resetlogchannel", description="Reset log channel")
    @app_commands.default_permissions(administrator=True)
    async def reset_log_channel(self, interaction: discord.Interaction):
        guild_id_str = str(interaction.guild_id)
        config = load_config()

        if guild_id_str in config:
            del config[guild_id_str]
            save_config(config)

            await interaction.response.send_message(
                "❌ Pengaturan channel log moderasi untuk server ini telah **dihapus**.",
                ephemeral=False
            )
        else:
            await interaction.response.send_message(
                "⚠️ Channel log belum pernah diatur atau sudah direset.",
                ephemeral=True
            )

    # --- BACKGROUND TASK: Auto Delete Log ---
    @tasks.loop(hours=24)
    async def log_cleanup_task(self):
        await self.bot.wait_until_ready() 
        
        print("Mulai tugas pembersihan log...")
        
        config = load_config()
        
        seven_days_ago = datetime.datetime.now(pytz.utc) - datetime.timedelta(days=LOG_EXPIRY_DAYS)
        
        for guild_id_str, channel_id in config.items():
            guild = self.bot.get_guild(int(guild_id_str))
            if not guild:
                continue

            log_channel = self.bot.get_channel(channel_id)

            if log_channel and isinstance(log_channel, discord.TextChannel):
                try:
                    deleted = await log_channel.purge(
                        before=seven_days_ago,
                        limit=None
                    )
                    print(f"[{guild.name}] Berhasil menghapus {len(deleted)} pesan log lama.")
                    
                except discord.Forbidden:
                    print(f"ERROR: Bot tidak memiliki izin Manage Messages di log channel {log_channel.name} ({guild.name}).")
                except Exception as e:
                    print(f"ERROR: Gagal membersihkan log di {log_channel.name} ({guild.name}): {e}")

        print("Tugas pembersihan log selesai.")

    @log_cleanup_task.before_loop
    async def before_log_cleanup_task(self):
        print("Menunggu bot siap untuk memulai tugas pembersihan log...")

# --- SETUP COG ---

async def setup(bot: commands.Bot):
    await bot.add_cog(LogConfig(bot))
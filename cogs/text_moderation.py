import discord
from discord import app_commands
from discord.ext import commands
from .log_config import get_log_channel_id
import datetime
import pytz

JAKARTA_TZ = pytz.timezone('Asia/Jakarta')

class TextModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def log_action(self, interaction: discord.Interaction, title: str, description: str, color=discord.Color.dark_gold()):
        log_channel_id = get_log_channel_id(interaction.guild_id)
        
        if not log_channel_id:
             return
             
        log_ch = self.bot.get_channel(log_channel_id)
        
        if not log_ch:
            return
        
        now_wib = datetime.datetime.now(JAKARTA_TZ)
        
        embed = discord.Embed(title=title, description=description, color=color, timestamp=now_wib)
        embed.set_author(name=str(interaction.user), icon_url=getattr(interaction.user, "avatar.url", None) if hasattr(interaction.user, "avatar") else None)
        if log_ch:
            try:
                await log_ch.send(embed=embed)
            except Exception:
                pass

    async def log_deleted_message_details(self, moderator: discord.User, target_msg: discord.Message, reason: str):
        """Mem-forward pesan target ke channel log sebelum dihapus."""
        
        log_channel_id = get_log_channel_id(target_msg.guild.id)
        
        if not log_channel_id:
            return

        log_ch = self.bot.get_channel(log_channel_id)
        if not log_ch:
            return
        
        msg_time_utc = target_msg.created_at 
        
        unix_timestamp = int(msg_time_utc.timestamp())
        
        dynamic_time_full = f"<t:{unix_timestamp}:F>"
        dynamic_time_relative = f"<t:{unix_timestamp}:R>"

        now_wib = datetime.datetime.now(JAKARTA_TZ)
        
        context_embed = discord.Embed(
            title=f"🗑️ Pesan Dihapus oleh {moderator.display_name}",
            description=(
                f"**Target:** {target_msg.author.mention}`)\n"
                f"**Channel:** {target_msg.channel.mention}\n"
                f"**Waktu Pesan:** {dynamic_time_full} ({dynamic_time_relative})\n"
                f"**Alasan:** {reason if reason else 'Tidak ada alasan'}"
            ),
            color=discord.Color.dark_red(),
            timestamp=now_wib
        )
        context_embed.set_footer(text=f"ID Pesan: {target_msg.id}")
        await log_ch.send(embed=context_embed)

        try:
            await target_msg.forward(log_ch)
        except Exception as e:
            await log_ch.send(f"⚠️ Gagal mem-forward pesan asli (ID: {target_msg.id}). Error: {e}")
            
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"Perintah sedang cooldown. Coba lagi setelah {error.retry_after:.1f}s.", ephemeral=True)
            return
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("Anda tidak memiliki izin yang dibutuhkan untuk menjalankan perintah ini.", ephemeral=True)
            return
        try:
            await (interaction.followup.send if interaction.response.is_done() else interaction.response.send_message)(f"Terjadi error: {str(error)}", ephemeral=True)
        except Exception:
            pass


    @commands.command(name="delete", aliases=["del"])
    @commands.has_permissions(manage_messages=True)
    async def delete_cmd(self, ctx: commands.Context, *, reason: str = None):
        """Reply ke pesan yang ingin dihapus lalu jalankan: !delete [alasan]"""
        
        ref = ctx.message.reference
        if not ref:
            await ctx.send("Harap reply pesan yang ingin dihapus.", delete_after=8)
            return
        
        try:
            target = ref.resolved if getattr(ref, "resolved", None) else await ctx.channel.fetch_message(ref.message_id)
        except discord.NotFound:
             await ctx.send("Pesan target tidak ditemukan.", delete_after=8)
             return
        except Exception as e:
            await ctx.send(f"Gagal mengambil pesan: {e}", delete_after=8)
            return

        await self.log_deleted_message_details(
            moderator=ctx.author,
            target_msg=target,
            reason=reason
        )

        try:
            await target.delete()
            
            await ctx.message.delete() 
            confirm_embed = discord.Embed(
                description=f"🗑️ Pesan dari **{target.author.mention}** telah dihapus oleh {ctx.author.mention}.",
                color=discord.Color.red()
            )
            if reason:
                confirm_embed.set_footer(text=f"Alasan: {reason}")
                
            await ctx.send(embed=confirm_embed)

        except discord.Forbidden:
            await ctx.send("Bot tidak memiliki izin untuk menghapus pesan target atau pesan command.", delete_after=8)
        except Exception as e:
            await self.log_action(
                ctx, 
                title="❌ Gagal Operasi Delete", 
                description=f"Gagal menghapus pesan/mengirim konfirmasi:\n{e}"
            )
            await ctx.send(f"Gagal menghapus pesan: {e}", delete_after=8)


async def setup(bot: commands.Bot):
    cog = TextModeration(bot)
    await bot.add_cog(cog)
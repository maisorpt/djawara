import discord
from discord import app_commands
from discord.ext import commands
import datetime
import os

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID") or 0)

class TextModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def log_action(self, interaction: discord.Interaction, title: str, description: str, color=discord.Color.dark_gold()):
        log_ch = self.bot.get_channel(LOG_CHANNEL_ID)
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.utcnow())
        embed.set_author(name=str(interaction.user), icon_url=getattr(interaction.user, "avatar.url", None) if hasattr(interaction.user, "avatar") else None)
        if log_ch:
            try:
                await log_ch.send(embed=embed)
            except Exception:
                pass

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"Perintah sedang cooldown. Coba lagi setelah {error.retry_after:.1f}s.", ephemeral=True)
            return
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("Anda tidak memiliki izin yang dibutuhkan untuk menjalankan perintah ini.", ephemeral=True)
            return
        try:
            await interaction.response.send_message(f"Terjadi error: {str(error)}", ephemeral=True)
        except Exception:
            pass

    # Handler (tidak terdaftar jika versi lama); tetap tersedia jika nanti ingin didaftarkan
    async def delete_message(self, interaction: discord.Interaction, message: discord.Message):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("Anda tidak memiliki izin Manage Messages.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        target = message

        content = target.content or ""
        attachments = [a.url for a in target.attachments] if target.attachments else []
        log_lines = [
            f"Moderator: {interaction.user} ({interaction.user.id})",
            f"Message Author: {target.author} ({target.author.id})",
            f"Channel: {target.channel} ({target.channel.id})",
            "Content:",
            "```",
            content if content else "[no text content]",
            "```"
        ]
        if attachments:
            log_lines.append("Attachments:")
            for a in attachments:
                log_lines.append(a)

        log_ch = self.bot.get_channel(LOG_CHANNEL_ID)
        try:
            if log_ch:
                await log_ch.send("\n".join(log_lines))
        except Exception:
            pass

        try:
            await target.delete()
            # tidak mengirim notifikasi ke channel utama; hanya log ke LOG_CHANNEL_ID dan embed via log_action
            await self.log_action(interaction, "Message Deleted", f"Deleted message by {target.author} ({target.author.id}) in <#{target.channel.id}>", color=discord.Color.red())
        except discord.Forbidden:
            await interaction.followup.send("Bot tidak memiliki izin untuk menghapus pesan.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Gagal menghapus pesan: {e}", ephemeral=True)

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
        except Exception as e:
            await ctx.send(f"Gagal mengambil pesan: {e}", delete_after=8)
            return

        content = target.content or ""
        attachments = [a.url for a in target.attachments] if target.attachments else []
        log_lines = [
            f"Moderator: {ctx.author} ({ctx.author.id})",
            f"Message Author: {target.author} ({target.author.id})",
            f"Channel: {target.channel} ({target.channel.id})",
            f"Reason: {reason or '—'}",
            "Content:",
            "```",
            content if content else "[no text content]",
            "```",
        ]
        if attachments:
            log_lines.append("Attachments:")
            log_lines.extend(attachments)

        log_ch = self.bot.get_channel(LOG_CHANNEL_ID)
        try:
            if log_ch:
                await log_ch.send("\n".join(log_lines))
        except Exception:
            pass

        try:
            await target.delete()
            # hapus notifikasi di channel utama — tidak mengirim ctx.send konfirmasi
            try:
                embed = discord.Embed(
                    title="Message Deleted",
                    description=f"Deleted message by {target.author} ({target.author.id}) in <#{target.channel.id}>",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.set_author(name=str(ctx.author), icon_url=getattr(ctx.author, "avatar.url", None) if hasattr(ctx.author, "avatar") else None)
                embed.set_footer(text=f"Guild: {ctx.guild.id if ctx.guild else 'DM'}")
                if log_ch:
                    await log_ch.send(embed=embed)
            except Exception:
                pass
        except discord.Forbidden:
            await ctx.send("Bot tidak memiliki izin untuk menghapus pesan.", delete_after=8)
        except Exception as e:
            await ctx.send(f"Gagal menghapus pesan: {e}", delete_after=8)

async def setup(bot: commands.Bot):
    cog = TextModeration(bot)
    await bot.add_cog(cog)
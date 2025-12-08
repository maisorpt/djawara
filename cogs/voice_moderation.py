import discord
from discord import app_commands
from discord.ext import commands
import typing
import datetime
import os
import re

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

class ActiveVoiceChannel(app_commands.Transform):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: discord.VoiceChannel) -> discord.VoiceChannel:
        if not isinstance(value, discord.VoiceChannel):
            raise app_commands.AppCommandError("Value is not a voice channel.")
        if len(value.members) == 0:
            raise app_commands.AppCommandError("Channel tidak memiliki anggota aktif.")
        return value

class VoiceModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def log_action(self, interaction: discord.Interaction, title: str, description: str, color=discord.Color.orange()):
        log_ch = self.bot.get_channel(LOG_CHANNEL_ID)
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.utcnow())
        embed.set_author(name=str(interaction.user), icon_url=getattr(interaction.user, "avatar.url", None) if hasattr(interaction.user, "avatar") else None)
        embed.set_footer(text=f"Guild: {interaction.guild.id if interaction.guild else 'DM'}")
        if log_ch:
            try:
                await log_ch.send(embed=embed)
            except Exception:
                pass

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"Perintah sedang cooldown. Coba lagi setelah {error.retry_after:.1f}s.", ephemeral=False)
            return
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("Anda tidak memiliki izin yang dibutuhkan untuk menjalankan perintah ini.", ephemeral=False)
            return
        try:
            await interaction.response.send_message(f"Terjadi error: {str(error)}", ephemeral=False)
        except Exception:
            pass

    def _can_connect(self, channel: discord.VoiceChannel, member: discord.Member) -> bool:
        perms = channel.permissions_for(member)
        return perms.view_channel and perms.connect

    def _find_option_value(self, interaction: discord.Interaction, name: str) -> typing.Optional[str]:
        data = getattr(interaction, "data", None)
        if not data:
            return None
        opts = data.get("options") or []
        for o in opts:
            if o.get("name") == name:
                return o.get("value")
            for sub in (o.get("options") or []):
                if sub.get("name") == name:
                    return sub.get("value")
        return None

    def _member_label(self, m: discord.Member) -> str:
        # label: display_name — username#discriminator (no id)
        disc = getattr(m, "discriminator", None)
        uname = f"{m.name}#{disc}" if disc is not None else m.name
        return f"{m.display_name} — {uname}"

    _MENTION_RE = re.compile(r"<@!?(\d+)>")
    _ID_RE = re.compile(r"^\s*(\d+)\s*$")

    def _parse_user_ids_from_string(self, s: str) -> typing.List[int]:
        # accepts comma separated mentions or numeric ids or mixed
        ids: typing.List[int] = []
        for part in [p.strip() for p in s.split(",") if p.strip()]:
            m = self._MENTION_RE.match(part)
            if m:
                try:
                    ids.append(int(m.group(1)))
                    continue
                except Exception:
                    pass
            m2 = self._ID_RE.match(part)
            if m2:
                try:
                    ids.append(int(m2.group(1)))
                    continue
                except Exception:
                    pass
        return ids

    # ---------- Autocomplete helpers ----------
    async def _voice_member_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice]:
        guild = interaction.guild
        if not guild:
            return []
        invoker = interaction.user
        cmd = interaction.data.get("name") if getattr(interaction, "data", None) else None
        choices: list[app_commands.Choice] = []
        for m in guild.members:
            if not (m.voice and m.voice.channel):
                continue
            # Only show members in channels accessible by invoker
            if not self._can_connect(m.voice.channel, invoker):
                continue
            # filter by command state
            if cmd == "mute" and getattr(m.voice, "mute", False):
                continue
            if cmd == "unmute" and not getattr(m.voice, "mute", False):
                continue
            if cmd == "deafen" and getattr(m.voice, "deaf", False):
                continue
            if cmd == "undeafen" and not getattr(m.voice, "deaf", False):
                continue
            label = self._member_label(m)
            if not current or current.lower() in label.lower():
                value = f"<@{m.id}>"
                choices.append(app_commands.Choice(name=label, value=value))
        return choices[:25]

    async def _dcbulk_users_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice]:
        # autocomplete untuk user1, user2, user3, dst
        # exclude users yang sudah ditambahkan di parameter sebelumnya
        guild = interaction.guild
        if not guild:
            return []
        invoker = interaction.user
        
        # parse users dari parameter sebelumnya
        selected_ids = []
        data = getattr(interaction, "data", None)
        if data:
            opts = data.get("options") or []
            for o in opts:
                name = o.get("name")
                # user1, user2, user3, ... parameter
                if name and name.startswith("user"):
                    val = o.get("value")
                    if val:
                        ids = self._parse_user_ids_from_string(val)
                        selected_ids.extend(ids)
        
        choices: list[app_commands.Choice] = []
        for m in guild.members:
            if not (m.voice and m.voice.channel):
                continue
            # Only show members in channels accessible by invoker
            if not self._can_connect(m.voice.channel, invoker):
                continue
            # Exclude already selected users
            if m.id in selected_ids:
                continue
            label = self._member_label(m)
            if current and current.lower() not in label.lower():
                continue
            choices.append(app_commands.Choice(name=label, value=f"<@{m.id}>"))
        return choices[:25]

    async def _movebulk_users_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice]:
        # autocomplete untuk user1, user2, user3, dst
        # exclude users yang sudah ditambahkan di parameter sebelumnya
        guild = interaction.guild
        if not guild:
            return []
        invoker = interaction.user
        
        # parse users dari parameter sebelumnya
        selected_ids = []
        data = getattr(interaction, "data", None)
        if data:
            opts = data.get("options") or []
            for o in opts:
                name = o.get("name")
                # user1, user2, user3, ... parameter
                if name and name.startswith("user"):
                    val = o.get("value")
                    if val:
                        ids = self._parse_user_ids_from_string(val)
                        selected_ids.extend(ids)
        
        choices: list[app_commands.Choice] = []
        for m in guild.members:
            if not (m.voice and m.voice.channel):
                continue
            # Only show members in channels accessible by invoker
            if not self._can_connect(m.voice.channel, invoker):
                continue
            # Exclude already selected users
            if m.id in selected_ids:
                continue
            label = self._member_label(m)
            if current and current.lower() not in label.lower():
                continue
            choices.append(app_commands.Choice(name=label, value=f"<@{m.id}>"))
        return choices[:25]
    
    async def _voice_channel_source_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice]:
        guild = interaction.guild
        # Keluar jika interaksi tidak terjadi di guild
        if not guild:
            return []

        # Dapatkan anggota yang memanggil perintah (invoker)
        invoker = interaction.user 
        
        choices = []
        
        # 1. Perulangan melalui semua voice channels
        for ch in guild.voice_channels:
            
            # 2. Periksa apakah invoker memiliki izin untuk melihat (VIEW_CHANNEL) VC ini
            #    dan terhubung (CONNECT) ke VC ini.
            permissions = ch.permissions_for(invoker)
            if not permissions.view_channel or not permissions.connect:
                continue  # Abaikan jika invoker tidak dapat melihat atau terhubung

            # 3. Periksa apakah VC memiliki user (Seperti yang sudah ada di kode Anda)
            if len(ch.members) == 0:
                continue
                
            # Jika semua pemeriksaan lolos:
            label = f"{ch.name} ({len(ch.members)} user)"
            
            if not current or current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=str(ch.id)))
                
        return choices[:25]

    async def _voice_channel_destination_for_target_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice]:
        # destination: accessible by target member AND invoker
        guild = interaction.guild
        if not guild:
            return []
        invoker = interaction.user
        user_val = self._find_option_value(interaction, "user")
        if not user_val:
            return []
        target_ids = self._parse_user_ids_from_string(user_val)
        if not target_ids:
            return []
        target_member = guild.get_member(target_ids[0])
        if not target_member:
            return []
        choices = []
        for ch in guild.voice_channels:
            # exclude target's current channel
            if target_member.voice and target_member.voice.channel and ch.id == target_member.voice.channel.id:
                continue
            # require destination accessible by both target_member AND invoker
            if not self._can_connect(ch, target_member):
                continue
            if not self._can_connect(ch, invoker):
                continue
            label = f"{ch.name} ({len(ch.members)} users)" if len(ch.members) > 0 else f"{ch.name} (empty)"
            if not current or current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=str(ch.id)))
        return choices[:25]

    async def _voice_channel_destination_for_bulk_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice]:
        # destination for movebulk: channels accessible by ALL selected members AND invoker
        guild = interaction.guild
        if not guild:
            return []
        invoker = interaction.user
        
        # --- PERBAIKAN DI SINI (Identifikasi User) ---
        all_user_values = []
        for i in range(1, 6): # user1 hingga user5
            user_val = getattr(interaction.namespace, f'user{i}', None)
            if user_val:
                all_user_values.append(user_val)
        
        combined_user_mentions = ", ".join(all_user_values)
        ids = self._parse_user_ids_from_string(combined_user_mentions)
        # --- AKHIR PERBAIKAN (Identifikasi User) ---
        
        # 1. TEMUKAN VC ASAL DAN SIMPAN DALAM SET
        source_vcs = set()
        
        if not ids:
            # Jika belum ada user yang dipilih, hanya tampilkan VC yang dapat diakses invoker
            members = []
        else:
            members = [guild.get_member(i) for i in ids if guild.get_member(i)]
            if not members:
                return []
            
            # Tambahkan ID VC asal dari setiap member ke set source_vcs
            for m in members:
                if m.voice and m.voice.channel:
                    source_vcs.add(m.voice.channel.id)
        
        choices = []
        for ch in guild.voice_channels:
            
            # 2. LOGIKA EKSKLUSI: Lewati VC asal yang sudah teridentifikasi
            if ch.id in source_vcs:
                continue
            
            # Check for permissions for all selected members
            ok = True
            for m in members:
                # Menggunakan _can_connect
                if not self._can_connect(ch, m):
                    ok = False
                    break
            
            # Also check invoker can access
            if not self._can_connect(ch, invoker):
                ok = False
                
            if not ok:
                continue
            
            label = f"{ch.name} ({len(ch.members)} users)" if len(ch.members) > 0 else f"{ch.name} (empty)"
            if not current or current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=str(ch.id)))
                
        return choices[:25]

    async def _voice_channel_destination_for_source_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice]:
        # destination options for movechannel: accessible by all members in source AND invoker
        guild = interaction.guild
        if not guild:
            return []
        invoker = interaction.user
        source_val = self._find_option_value(interaction, "source")
        if not source_val:
            return []
        try:
            src = guild.get_channel(int(source_val))
        except Exception:
            return []
        members = list(src.members) if isinstance(src, discord.VoiceChannel) else []
        choices = []
        for ch in guild.voice_channels:
            if str(ch.id) == str(source_val):
                continue
            ok = True
            for m in members:
                if not ch.permissions_for(m).view_channel or not ch.permissions_for(m).connect:
                    ok = False
                    break
            # Also check invoker can access
            if not self._can_connect(ch, invoker):
                ok = False
            if not ok:
                continue
            label = f"{ch.name} ({len(ch.members)} users)" if len(ch.members) > 0 else f"{ch.name} (empty)"
            if not current or current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=str(ch.id)))
        return choices[:25]

    # ---------- Commands (responses visible to all) ----------
    @app_commands.command(name="mute", description="Mute user")
    @app_commands.describe(user="Pilih user", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    async def mute(self, interaction: discord.Interaction, user: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak dapat di-mute.", ephemeral=True)
            return
        member = interaction.guild.get_member(ids[0])
        if not member or not member.voice or not member.voice.channel or getattr(member.voice, "mute", False):
            await interaction.response.send_message("User tidak dapat di-mute.", ephemeral=True)
            return
        await member.edit(mute=True, reason=reason)
        await interaction.response.send_message(f"✅ Berhasil mute {member.mention}.", ephemeral=True)
        embed = discord.Embed(
                title="🔇 SERVER MUTE",
                description=f"**{member.mention}** telah dibisukan di Voice.",
                color=discord.Color.red()
                 )
        if reason:
                embed.add_field(name="Oleh", value=interaction.user.mention, inline=True)
                embed.add_field(name="Alasan", value=reason, inline=True)
        else:
                embed.add_field(name="\u200b", value=f"**Oleh:** {interaction.user.mention}",inline=True)

        await interaction.channel.send(embed=embed)
        await self.log_action(interaction, "Server Mute", f"Target: {member}\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.orange())

    @app_commands.command(name="unmute", description="Unmute user")
    @app_commands.describe(user="Pilih user", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    async def unmute(self, interaction: discord.Interaction, user: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak dapat di-unmute.", ephemeral=False)
            return
        member = interaction.guild.get_member(ids[0])
        if not member or not member.voice or not member.voice.channel or not getattr(member.voice, "mute", False):
            await interaction.response.send_message("User tidak dapat di-unmute.", ephemeral=False)
            return
        await member.edit(mute=False, reason=reason)
        await interaction.response.send_message(f"🔊 Berhasil unmute {member.mention}.", ephemeral=True)
        embed = discord.Embed(
                title="🔊 SERVER UNMUTE",
                description=f"**{member.mention}** mic telah diaktifkan.",
                color=discord.Color.green()
            )
        if reason:
            embed.add_field(name="Oleh", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alasan", value=reason, inline=True)
        else:
            embed.add_field(name="\u200b", value=f"**Oleh:** {interaction.user.mention}",inline=True)

        await interaction.channel.send(embed=embed)
        await self.log_action(interaction, "Server Unmute", f"Target: {member} ({member.id})\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.green())

    @app_commands.command(name="deafen", description="Deafen user")
    @app_commands.describe(user="Pilih user", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    async def deafen(self, interaction: discord.Interaction, user: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak dapat di-deafen.", ephemeral=False)
            return
        member = interaction.guild.get_member(ids[0])
        if not member or not member.voice or not member.voice.channel or getattr(member.voice, "deaf", False):
            await interaction.response.send_message("User tidak dapat di-deafen.", ephemeral=False)
            return
        await member.edit(deafen=True, reason=reason)
        await interaction.response.send_message(f"🔕 Berhasil deafen {member.mention}.", ephemeral=True)
        embed = discord.Embed(
                title="🔕 SERVER DEAFEN",
                description=f"**{member.mention}** telah di-deafen.",
                color=discord.Color.red()
            )
        if reason:
            embed.add_field(name="Oleh", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alasan", value=reason, inline=True)
        else:
            embed.add_field(name="\u200b", value=f"**Oleh:** {interaction.user.mention}",inline=True)

        await interaction.channel.send(embed=embed)
        await self.log_action(interaction, "Server Deafen", f"Target: {member} ({member.id})\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.orange())

    @app_commands.command(name="undeafen", description="Undeafen user")
    @app_commands.describe(user="Pilih user", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    async def undeafen(self, interaction: discord.Interaction, user: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak dapat di-undeafen.", ephemeral=False)
            return
        member = interaction.guild.get_member(ids[0])
        if not member or not member.voice or not member.voice.channel or not getattr(member.voice, "deaf", False):
            await interaction.response.send_message("Member tidak dapat di-undeafen.", ephemeral=False)
            return
        await member.edit(deafen=False, reason=reason)
        await interaction.response.send_message(f"🔔 Berhasil undeafen {member.mention}.", ephemeral=True)
        embed = discord.Embed(
                title="🔔 SERVER UNDEAFEN",
                description=f"**{member.mention}** telah di-undeafen.",
                color=discord.Color.green()
            )
        if reason:
            embed.add_field(name="Oleh", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alasan", value=reason, inline=True)
        else:
            embed.add_field(name="\u200b", value=f"**Oleh:** {interaction.user.mention}",inline=True)

        await interaction.channel.send(embed=embed)
        await self.log_action(interaction, "Server Undeafen", f"Target: {member} ({member.id})\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.green())
    @app_commands.command(name="move", description="Pindahkan satu user ke channel lain")
    @app_commands.describe(user="Pilih user", destination="Pilih channel tujuan", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    @app_commands.autocomplete(destination=_voice_channel_destination_for_target_autocomplete)
    async def move(self, interaction: discord.Interaction, user: str, destination: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak valid.", ephemeral=True)
            return
        member = interaction.guild.get_member(ids[0])
        dest = interaction.guild.get_channel(int(destination))
        if not member or not member.voice or not member.voice.channel:
            await interaction.response.send_message("User tidak ditemukan atau tidak sedang di voice.", ephemeral=True)
            return
        original_channel = member.voice.channel
        if not isinstance(dest, discord.VoiceChannel) or not self._can_connect(dest, member):
            await interaction.response.send_message("Channel tujuan tidak valid atau tidak dapat diakses oleh member.", ephemeral=True)
            return
        if member.voice.channel.id == dest.id:
            await interaction.response.send_message("Member sudah berada di channel tujuan.", ephemeral=True)
            return
        
        await member.move_to(dest, reason=reason)
        await interaction.response.send_message(f"✅ Berhasil memindahkan {member.mention} dari 🔊 {original_channel.name} ke 🔊 {dest.name}.", ephemeral=True)
        embed = discord.Embed(
            title="🚚 VOICE MOVE",
            description=f"**{member.mention}** telah dipindahkan dari **<#{original_channel.id}>** ke **<#{dest.id}>**.",
            color=discord.Color.blue()
        )
        if reason:
            embed.add_field(name="Oleh", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alasan", value=reason, inline=True)
        else:
            embed.add_field(name="\u200b", value=f"**Oleh:** {interaction.user.mention}",inline=True)

        await interaction.channel.send(embed=embed)
        await self.log_action(interaction, "Voice Move", f"Target: {member}\n{original_channel.name} -> {dest.name}\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.blue())

    @app_commands.command(name="movebulk", description="Pindahkan beberapa user sekaligus ke channel lain")
    @app_commands.describe(
        user1="Pilih user pertama",
        destination="Pilih channel tujuan",
        user2="Pilih user kedua (opsional)",
        user3="Pilih user ketiga (opsional)",
        user4="Pilih user keempat (opsional)",
        user5="Pilih user kelima (opsional)",
        reason="Alasan"
    )
    @app_commands.autocomplete(user1=_movebulk_users_autocomplete)
    @app_commands.autocomplete(user2=_movebulk_users_autocomplete)
    @app_commands.autocomplete(user3=_movebulk_users_autocomplete)
    @app_commands.autocomplete(user4=_movebulk_users_autocomplete)
    @app_commands.autocomplete(user5=_movebulk_users_autocomplete)
    @app_commands.autocomplete(destination=_voice_channel_destination_for_bulk_autocomplete)
    async def movebulk(
        self, 
        interaction: discord.Interaction, 
        user1: str,
        destination: str = None,
        user2: typing.Optional[str] = None,
        user3: typing.Optional[str] = None,
        user4: typing.Optional[str] = None,
        user5: typing.Optional[str] = None,
        reason: typing.Optional[str] = None
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        # Combine all user parameters
        all_users = [u for u in [user1, user2, user3, user4, user5] if u]
        combined = ", ".join(all_users)
        
        ids = self._parse_user_ids_from_string(combined)

        # Inisialisasi daftar anggota yang valid untuk dipindahkan
        valid_members = []
         # Inisialisasi dictionary untuk melacak channel asal
        original_channels = {}

        # Memvalidasi dan Mengumpulkan anggota yang sedang di voice channel
        for member_id in ids:
            m = interaction.guild.get_member(member_id)
            
            # Cek apakah anggota ditemukan DAN sedang di voice channel
            if m and m.voice and m.voice.channel:
                valid_members.append(m)
                # Simpan nama channel asal SEBELUM aksi pemindahan
                original_channels[m.id] = (m.voice.channel.id, m.voice.channel.name)
            elif m:
                # Jika user valid tapi tidak di voice channel, catat sebagai skipped
                original_channels[m.id] = (0, "ERROR: Tidak di Voice")

        if not valid_members:
            await interaction.followup.send("User tidak ditemukan atau tidak sedang di voice.", ephemeral=True)
            return
        
        dest = interaction.guild.get_channel(int(destination))

        if not isinstance(dest, discord.VoiceChannel):
            await interaction.followup.send("Channel tujuan tidak valid.", ephemeral=True)
            return
        # ensure destination accessible by all selected members
        for m in valid_members:
            if not self._can_connect(dest, m):
                await interaction.followup.send("Channel tidak dapat diakses oleh salah satu member yang dipilih.", ephemeral=True)
                return
            
        results_for_logs = []
        results_for_display = []
        moved_count = 0
        for m in valid_members:
            source_id = original_channels.get(m.id, (0, ))[0]
            source_name = original_channels.get(m.id, ("ERROR: Unknown", ))[1]
            # Pengecekan tambahan: pastikan tidak pindah ke channel yang sama
        try:
            if m.voice.channel.id == dest.id:
                results_for_logs.append(f"SKIP: {m.display_name} sudah berada di 🔊 {dest.name}")
                results_for_display.append(f"SKIP: {m.display_name} sudah berada di <#{dest.id}>")

            await m.move_to(dest, reason=reason)
            # Catat hasil pemindahan: [Anggota] (Channel Asal -> Channel Tujuan)
            moved_count += 1

            results_for_logs.append(f"{m.display_name} dari 🔊 {source_name}")
            results_for_display.append(f"{m.display_name} dari <#{source_id}>")
        except Exception as e:
            results_for_logs.append(f"{m.display_name} ({source_name}) -> Error: {e}")
            results_for_display.append(f"{m.display_name} (<#{m.voice.channel.id}>) -> Error: {e}")
            
        await interaction.followup.send(
            f"✅ {moved_count} user berhasil dipindahkan. Detail:\n\n" + "\n".join(results_for_logs),
            ephemeral=True
        )
        embed = discord.Embed(
            title="🚚 VOICE MOVE",
            description=f"**{moved_count}** user telah dipindahkan ke **<#{dest.id}>**: \n\n" + "\n".join(results_for_display),
            color=discord.Color.blue()
        )
        if reason:
            embed.add_field(name="Oleh", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alasan", value=reason, inline=True)
        else:
            embed.add_field(name="\u200b", value=f"**Oleh:** {interaction.user.mention}",inline=True)

        await interaction.channel.send(embed=embed)
        await self.log_action(interaction, "Voice Bulk Move", f"Users: {combined}\nDestination: {dest.name}\nResults:\n\n" + "\n".join(results_for_logs) + f"\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.blue())

    @app_commands.command(name="movechannel", description="Pindahkan semua user di voice channel sekaligus")
    @app_commands.describe(source="Channel asal", destination="Channel tujuan", reason="Alasan")
    @app_commands.autocomplete(source=_voice_channel_source_autocomplete)
    @app_commands.autocomplete(destination=_voice_channel_destination_for_source_autocomplete)
    async def movechannel(self, interaction: discord.Interaction, source: str, destination: str, reason: typing.Optional[str] = None):
        src = interaction.guild.get_channel(int(source))
        dest = interaction.guild.get_channel(int(destination))
        if not isinstance(src, discord.VoiceChannel) or len(src.members) == 0:
            await interaction.response.send_message("Channel tidak valid atau tidak memiliki anggota.", ephemeral=True)
            return
        if not isinstance(dest, discord.VoiceChannel):
            await interaction.response.send_message("Channel tujuan tidak valid.", ephemeral=True)
            return
        # ensure destination accessible by all members in source
        for m in src.members:
            if not self._can_connect(dest, m):
                await interaction.response.send_message("Channel tujuan tidak dapat diakses oleh semua member di source.", ephemeral=True)
                return
        await interaction.response.defer(thinking=True, ephemeral=True)

        results= []
        moved_count = 0
        for m in list(src.members):
            try:
                if m.voice.channel.id == dest.id:
                    results.append(f"SKIP: {m.display_name} sudah berada di {dest.name}")
                    continue
                
                moved_count += 1

                await m.move_to(dest, reason=reason)
                # Catat hasil pemindahan: [Anggota] (Channel Asal -> Channel Tujuan)
                results(f"{m.display_name}")
            except Exception as e:
                results.append(f"❌ {m.display_name} ({src.name}) -> Error: {e}")
   
        await interaction.followup.send(
            f"✅ {moved_count} user berhasil dipindahkan. Detail:\n\n" + "\n".join(results),
            ephemeral=True
        )
        embed = discord.Embed(
            title="🚚 VOICE MOVE",
            description=f"**{moved_count}** user telah dipindahkan dari **<#{src.id}>** ke **<#{dest.id}>**: \n\n" + "\n".join(results),
            color=discord.Color.blue()
        )
        if reason:
            embed.add_field(name="Oleh", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alasan", value=reason, inline=True)
        else:
            embed.add_field(name="\u200b", value=f"**Oleh:** {interaction.user.mention}",inline=True)

        await interaction.channel.send(embed=embed)
        await self.log_action(interaction, "Voice Channel Move", f"Source: {src.name}\nDestination: {dest.name}\nResults:\n\n" + "\n".join(results) + f"\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.blue())
    @app_commands.command(name="dc", description="Disconnect user dari voice")
    @app_commands.describe(user="Pilih user", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    async def dc(self, interaction: discord.Interaction, user: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak valid.", ephemeral=True)
            return
        member = interaction.guild.get_member(ids[0])
        if not member or not member.voice or not member.voice.channel:
            await interaction.response.send_message("User tidak ditemukan atau tidak sedang di voice.", ephemeral=True)
            return
        
        original_channel_id = member.voice.channel.id

        await member.move_to(None, reason=reason)
        await interaction.response.send_message(f"✅ Berhasil disconnect {member.mention}.", ephemeral=True)
        embed = discord.Embed(
            title="🔌 VOICE Disconnect",
            description=f"**{member.mention}** telah di-disconnect dari <#{original_channel_id}>.",
            color=discord.Color.red()
        )
        if reason:
            embed.add_field(name="Oleh", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alasan", value=reason, inline=True)
        else:
            embed.add_field(name="\u200b", value=f"**Oleh:** {interaction.user.mention}",inline=True)

        await interaction.channel.send(embed=embed)
        await self.log_action(interaction, "Voice Disconnect", f"Target: {member} ({member.id})\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.red())

    @app_commands.command(name="dcbulk", description="Disconnect beberapa user sekaligus")
    @app_commands.describe(
        user1="Pilih user pertama",
        user2="Pilih user kedua (opsional)",
        user3="Pilih user ketiga (opsional)",
        user4="Pilih user keempat (opsional)",
        user5="Pilih user kelima (opsional)",
        reason="Alasan"
    )
    @app_commands.autocomplete(user1=_dcbulk_users_autocomplete)
    @app_commands.autocomplete(user2=_dcbulk_users_autocomplete)
    @app_commands.autocomplete(user3=_dcbulk_users_autocomplete)
    @app_commands.autocomplete(user4=_dcbulk_users_autocomplete)
    @app_commands.autocomplete(user5=_dcbulk_users_autocomplete)
    async def dcbulk(
        self, 
        interaction: discord.Interaction, 
        user1: str,
        reason: typing.Optional[str] = None,
        user2: typing.Optional[str] = None,
        user3: typing.Optional[str] = None,
        user4: typing.Optional[str] = None,
        user5: typing.Optional[str] = None
    ):
        await interaction.response.defer(thinking=True)
        
        # Combine all user parameters
        all_users = [u for u in [user1, user2, user3, user4, user5] if u]
        combined = ", ".join(all_users)
        
        ids = self._parse_user_ids_from_string(combined)
        results = []
        disconnected_count = 0
        for uid in ids:
            member = interaction.guild.get_member(uid)
            if not member:
                results.append(f"{uid} -> not in guild")
                continue
            if not member.voice or not member.voice.channel:
                results.append(f"{member} -> not in voice")
                continue
            try:
                await member.move_to(None, reason=reason)

                disconnected_count += 1

                results.append(f"{member}")
            except Exception as e:
                results.append(f"{member} -> error: {e}")
        
        await interaction.followup.send(
            f"✅ {disconnected_count} user berhasil di-disconnect. Detail:\n\n" + "\n".join(results),
            ephemeral=True
        )
        embed = discord.Embed(
            title="🔌 VOICE DISCONNECT",
            description=f"**{disconnected_count}** user telah di-disconnect: \n\n" + "\n".join(results),
            color=discord.Color.red()
        )
        if reason:
            embed.add_field(name="Oleh", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alasan", value=reason, inline=True)
        else:
            embed.add_field(name="\u200b", value=f"**Oleh:** {interaction.user.mention}",inline=True)

        await interaction.channel.send(embed=embed)
        await self.log_action(interaction, "Voice Bulk Disconnect", f"Users: {combined}\nResults:\n\n" + "\n".join(results) + f"\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.red())

    @app_commands.command(name="dcchannel", description="Disconnect semua anggota dari voice channel yang dipilih")
    @app_commands.describe(channel="Pilih channel", reason="Alasan")
    @app_commands.autocomplete(channel=_voice_channel_source_autocomplete)
    async def dcchannel(self, interaction: discord.Interaction, channel: str, reason: typing.Optional[str] = None):
        ch = interaction.guild.get_channel(int(channel))
        if not isinstance(ch, discord.VoiceChannel) or len(ch.members) == 0:
            await interaction.response.send_message("Channel tidak valid atau tidak memiliki anggota.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        results = []
        disconnected_count = 0
        for m in list(ch.members):
            try:
                await m.move_to(None, reason=reason)

                disconnected_count += 1

                results.append(f"{m}")
            except Exception as e:
                results.append(f"{m} -> error: {e}")

        await interaction.followup.send(
            f"✅ berhasil disconnect {disconnected_count}. Detail:\n\n" + "\n".join(results),
            ephemeral=True
        )
        embed = discord.Embed(
            title="🔌 VOICE DISCONNECT",
            description=f"**{disconnected_count}** user telah di-disconnect: \n\n" + "\n".join(results),
            color=discord.Color.red()
        )
        if reason:
            embed.add_field(name="Oleh", value=interaction.user.mention, inline=True)
            embed.add_field(name="Alasan", value=reason, inline=True)
        else:
            embed.add_field(name="\u200b", value=f"**Oleh:** {interaction.user.mention}",inline=True)

        await interaction.channel.send(embed=embed)
        await self.log_action(interaction, "Voice Bulk Disconnect", f"Channel: 🔊 {ch.name}\nResults:\n\n" + "\n".join(results) + f"\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.red())

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceModeration(bot))
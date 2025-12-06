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
        cmd = interaction.data.get("name") if getattr(interaction, "data", None) else None
        choices: list[app_commands.Choice] = []
        for m in guild.members:
            if not (m.voice and m.voice.channel):
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
                # value: mention string (easy to paste into bulk string)
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
        if not guild:
            return []
        choices = []
        for ch in guild.voice_channels:
            if len(ch.members) == 0:
                continue
            label = f"{ch.name} ({len(ch.members)} user)"
            if not current or current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=str(ch.id)))
        return choices[:25]

    async def _voice_channel_destination_for_target_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice]:
        # destination: accessible by target member AND invoker
        # REFRESH setiap user berubah
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
        # destination for movebulk: only channels accessible by ALL selected members
        guild = interaction.guild
        if not guild:
            return []
        users_val = self._find_option_value(interaction, "user_mentions")
        if not users_val:
            return []
        ids = self._parse_user_ids_from_string(users_val)
        members = [guild.get_member(i) for i in ids if guild.get_member(i)]
        if not members:
            return []
        choices = []
        for ch in guild.voice_channels:
            ok = True
            for m in members:
                if not self._can_connect(ch, m):
                    ok = False
                    break
            if not ok:
                continue
            label = f"{ch.name} ({len(ch.members)} users)" if len(ch.members) > 0 else f"{ch.name} (empty)"
            if not current or current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=str(ch.id)))
        return choices[:25]

    async def _voice_channel_destination_for_source_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice]:
        # destination options for movechannel: destination must be accessible by all members in source
        guild = interaction.guild
        if not guild:
            return []
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
            if not ok:
                continue
            label = f"{ch.name} ({len(ch.members)} users)" if len(ch.members) > 0 else f"{ch.name} (empty)"
            if not current or current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=str(ch.id)))
        return choices[:25]

    # ---------- Commands (responses visible to all) ----------
    @app_commands.command(name="dc", description="Disconnect satu anggota dari voice")
    @app_commands.describe(user="Pilih user (hanya yang sedang terhubung)", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    async def dc(self, interaction: discord.Interaction, user: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak valid.", ephemeral=False)
            return
        member = interaction.guild.get_member(ids[0])
        if not member or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Member tidak ditemukan atau tidak sedang di voice.", ephemeral=False)
            return
        await member.move_to(None, reason=reason)
        await interaction.response.send_message(f"{member.mention} telah di-disconnect. Reason: {reason or '—'}", ephemeral=False)
        await self.log_action(interaction, "Voice Disconnect", f"Target: {member} ({member.id})\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.red())

    @app_commands.command(name="dcbulk", description="Disconnect beberapa anggota")
    @app_commands.describe(
        user1="Pilih user pertama (hanya yang sedang terhubung)",
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
        user2: typing.Optional[str] = None,
        user3: typing.Optional[str] = None,
        user4: typing.Optional[str] = None,
        user5: typing.Optional[str] = None,
        reason: typing.Optional[str] = None
    ):
        await interaction.response.defer(thinking=True)
        
        # Combine all user parameters
        all_users = [u for u in [user1, user2, user3, user4, user5] if u]
        combined = ", ".join(all_users)
        
        ids = self._parse_user_ids_from_string(combined)
        results = []
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
                results.append(f"{member} -> disconnected")
            except Exception as e:
                results.append(f"{member} -> error: {e}")
        await interaction.followup.send("Results:\n" + "\n".join(results), ephemeral=False)
        await self.log_action(interaction, "Voice Bulk Disconnect", f"Users: {combined}\nResults:\n" + "\n".join(results) + f"\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.red())

    @app_commands.command(name="dcchannel", description="Disconnect semua anggota dari voice channel yang dipilih")
    @app_commands.describe(channel="Pilih source voice channel (hanya channel dengan user)", reason="Alasan")
    @app_commands.autocomplete(channel=_voice_channel_source_autocomplete)
    async def dcchannel(self, interaction: discord.Interaction, channel: str, reason: typing.Optional[str] = None):
        ch = interaction.guild.get_channel(int(channel))
        if not isinstance(ch, discord.VoiceChannel) or len(ch.members) == 0:
            await interaction.response.send_message("Channel tidak valid atau tidak memiliki anggota.", ephemeral=False)
            return
        await interaction.response.defer(thinking=True)
        results = []
        for m in list(ch.members):
            try:
                await m.move_to(None, reason=reason)
                results.append(f"{m} -> disconnected")
            except Exception as e:
                results.append(f"{m} -> error: {e}")
        await interaction.followup.send(f"Disconnected members from {ch.name}:\n" + "\n".join(results), ephemeral=False)
        await self.log_action(interaction, "Voice Channel Disconnect", f"Channel: {ch.name} ({ch.id})\nResults:\n" + "\n".join(results) + f"\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.red())

    @app_commands.command(name="move", description="Pindahkan satu anggota ke channel tujuan")
    @app_commands.describe(user="Pilih user (hanya yang sedang terhubung)", destination="Pilih destination (dapat diakses oleh user)", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    @app_commands.autocomplete(destination=_voice_channel_destination_for_target_autocomplete)
    async def move(self, interaction: discord.Interaction, user: str, destination: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak valid.", ephemeral=False)
            return
        member = interaction.guild.get_member(ids[0])
        dest = interaction.guild.get_channel(int(destination))
        if not member or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Member tidak ditemukan atau tidak sedang di voice.", ephemeral=False)
            return
        if not isinstance(dest, discord.VoiceChannel) or not self._can_connect(dest, member):
            await interaction.response.send_message("Destination tidak valid atau tidak dapat diakses oleh member.", ephemeral=False)
            return
        if member.voice.channel.id == dest.id:
            await interaction.response.send_message("Member sudah berada di channel tujuan.", ephemeral=False)
            return
        await member.move_to(dest, reason=reason)
        await interaction.response.send_message(f"{member.mention} telah dipindahkan ke {dest.name}. Reason: {reason or '—'}", ephemeral=False)
        await self.log_action(interaction, "Voice Move", f"Target: {member} -> {dest.name}\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.blue())

    @app_commands.command(name="movebulk", description="Pindahkan beberapa anggota")
    @app_commands.describe(
        user1="Pilih user pertama (hanya yang sedang terhubung)",
        user2="Pilih user kedua (opsional)",
        user3="Pilih user ketiga (opsional)",
        user4="Pilih user keempat (opsional)",
        user5="Pilih user kelima (opsional)",
        destination="Destination voice channel (accessible by all selected users)",
        reason="Alasan"
    )
    @app_commands.autocomplete(user1=_movebulk_users_autocomplete)
    @app_commands.autocomplete(user2=_movebulk_users_autocomplete)
    @app_commands.autocomplete(user3=_movebulk_users_autocomplete)
    @app_commands.autocomplete(user4=_movebulk_users_autocomplete)
    @app_commands.autocomplete(user5=_movebulk_users_autocomplete)
    # @app_commands.autocomplete(destination=_movebulk_destination_autocomplete)
    async def movebulk(
        self, 
        interaction: discord.Interaction, 
        user1: str,
        user2: typing.Optional[str] = None,
        user3: typing.Optional[str] = None,
        user4: typing.Optional[str] = None,
        user5: typing.Optional[str] = None,
        destination: str = None,
        reason: typing.Optional[str] = None
    ):
        await interaction.response.defer(thinking=True)
        
        # Combine all user parameters
        all_users = [u for u in [user1, user2, user3, user4, user5] if u]
        combined = ", ".join(all_users)
        
        ids = self._parse_user_ids_from_string(combined)
        members = [interaction.guild.get_member(i) for i in ids if interaction.guild.get_member(i)]
        if not members:
            await interaction.followup.send("Tidak ada member yang valid.", ephemeral=False)
            return
        dest = interaction.guild.get_channel(int(destination))
        if not isinstance(dest, discord.VoiceChannel):
            await interaction.followup.send("Destination tidak valid.", ephemeral=False)
            return
        # ensure destination accessible by all selected members
        for m in members:
            if not self._can_connect(dest, m):
                await interaction.followup.send("Destination tidak dapat diakses oleh salah satu member yang dipilih.", ephemeral=False)
                return
        results = []
        for m in members:
            try:
                await m.move_to(dest, reason=reason)
                results.append(f"{m} -> moved")
            except Exception as e:
                results.append(f"{m} -> error: {e}")
        await interaction.followup.send("Results:\n" + "\n".join(results), ephemeral=False)
        await self.log_action(interaction, "Voice Bulk Move", f"Users: {combined}\nDestination: {dest.name}\nResults:\n" + "\n".join(results) + f"\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.blue())

    @app_commands.command(name="movechannel", description="Pindahkan semua anggota dari source ke destination")
    @app_commands.describe(source="Source voice channel (hanya channel dengan user)", destination="Destination voice channel (user dapat akses oleh semua member source)", reason="Alasan")
    @app_commands.autocomplete(source=_voice_channel_source_autocomplete)
    @app_commands.autocomplete(destination=_voice_channel_destination_for_source_autocomplete)
    async def movechannel(self, interaction: discord.Interaction, source: str, destination: str, reason: typing.Optional[str] = None):
        src = interaction.guild.get_channel(int(source))
        dest = interaction.guild.get_channel(int(destination))
        if not isinstance(src, discord.VoiceChannel) or len(src.members) == 0:
            await interaction.response.send_message("Source tidak valid atau tidak memiliki anggota.", ephemeral=False)
            return
        if not isinstance(dest, discord.VoiceChannel):
            await interaction.response.send_message("Destination tidak valid.", ephemeral=False)
            return
        # ensure destination accessible by all members in source
        for m in src.members:
            if not self._can_connect(dest, m):
                await interaction.response.send_message("Destination tidak dapat diakses oleh semua member di source.", ephemeral=False)
                return
        await interaction.response.defer(thinking=True)
        results = []
        for m in list(src.members):
            try:
                await m.move_to(dest, reason=reason)
                results.append(f"{m} -> moved")
            except Exception as e:
                results.append(f"{m} -> error: {e}")
        await interaction.followup.send(f"Moved members from {src.name} to {dest.name}:\n" + "\n".join(results), ephemeral=False)
        await self.log_action(interaction, "Voice Channel Move", f"Source: {src.name}\nDestination: {dest.name}\nResults:\n" + "\n".join(results) + f"\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.blue())

    @app_commands.command(name="mute", description="Server voice mute a member")
    @app_commands.describe(user="Pilih user (hanya yang sedang terhubung dan belum mute)", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    async def mute(self, interaction: discord.Interaction, user: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak valid untuk mute.", ephemeral=False)
            return
        member = interaction.guild.get_member(ids[0])
        if not member or not member.voice or not member.voice.channel or getattr(member.voice, "mute", False):
            await interaction.response.send_message("Member tidak valid untuk mute.", ephemeral=False)
            return
        await member.edit(mute=True, reason=reason)
        await interaction.response.send_message(f"{member.mention} telah di-server-mute. Reason: {reason or '—'}", ephemeral=False)
        await self.log_action(interaction, "Server Mute", f"Target: {member} ({member.id})\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.orange())

    @app_commands.command(name="unmute", description="Remove server voice mute")
    @app_commands.describe(user="Pilih user (hanya yang sedang terhubung dan sedang mute)", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    async def unmute(self, interaction: discord.Interaction, user: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak valid untuk unmute.", ephemeral=False)
            return
        member = interaction.guild.get_member(ids[0])
        if not member or not member.voice or not member.voice.channel or not getattr(member.voice, "mute", False):
            await interaction.response.send_message("Member tidak valid untuk unmute.", ephemeral=False)
            return
        await member.edit(mute=False, reason=reason)
        await interaction.response.send_message(f"{member.mention} telah di-unmute. Reason: {reason or '—'}", ephemeral=False)
        await self.log_action(interaction, "Server Unmute", f"Target: {member} ({member.id})\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.green())

    @app_commands.command(name="deafen", description="Server deafen a member")
    @app_commands.describe(user="Pilih user (hanya yang sedang terhubung dan belum deafen)", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    async def deafen(self, interaction: discord.Interaction, user: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak valid untuk deafen.", ephemeral=False)
            return
        member = interaction.guild.get_member(ids[0])
        if not member or not member.voice or not member.voice.channel or getattr(member.voice, "deaf", False):
            await interaction.response.send_message("Member tidak valid untuk deafen.", ephemeral=False)
            return
        await member.edit(deafen=True, reason=reason)
        await interaction.response.send_message(f"{member.mention} telah di-deafen. Reason: {reason or '—'}", ephemeral=False)
        await self.log_action(interaction, "Server Deafen", f"Target: {member} ({member.id})\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.orange())

    @app_commands.command(name="undeafen", description="Remove server deafen")
    @app_commands.describe(user="Pilih user (hanya yang sedang terhubung dan sedang deafen)", reason="Alasan")
    @app_commands.autocomplete(user=_voice_member_autocomplete)
    async def undeafen(self, interaction: discord.Interaction, user: str, reason: typing.Optional[str] = None):
        ids = self._parse_user_ids_from_string(user)
        if not ids:
            await interaction.response.send_message("User tidak valid untuk undeafen.", ephemeral=False)
            return
        member = interaction.guild.get_member(ids[0])
        if not member or not member.voice or not member.voice.channel or not getattr(member.voice, "deaf", False):
            await interaction.response.send_message("Member tidak valid untuk undeafen.", ephemeral=False)
            return
        await member.edit(deafen=False, reason=reason)
        await interaction.response.send_message(f"{member.mention} telah di-undeafen. Reason: {reason or '—'}", ephemeral=False)
        await self.log_action(interaction, "Server Undeafen", f"Target: {member} ({member.id})\nBy: {interaction.user}\nReason: {reason or '—'}", color=discord.Color.green())

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceModeration(bot))

import discord
from discord.ext import tasks
import os
import asyncio
import time
from datetime import timedelta

intents = discord.Intents.default()
intents.members = True
bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

TOKEN = os.getenv("DISCORD_TOKEN")
PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID"))
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))

user_sessions = {}

class PlaytimeButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 Online", style=discord.ButtonStyle.success)
    async def online(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        now = time.time()
        session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
        if session["status"] == "afk":
            session["afk_total"] += now - session.get("afk_start", now)
        elif session["status"] == "online":
            await interaction.response.send_message("You are already online.", ephemeral=True)
            return
        session["online_start"] = now
        session["status"] = "online"
        await interaction.response.send_message("✅ You are now marked as Online.", ephemeral=True)

    @discord.ui.button(label="🟡 AFK", style=discord.ButtonStyle.secondary)
    async def afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        now = time.time()
        session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
        if session["status"] == "online":
            session["online_total"] += now - session.get("online_start", now)
        session["afk_start"] = now
        session["status"] = "afk"
        await interaction.response.send_message("🌙 You are now marked as AFK.", ephemeral=True)

    @discord.ui.button(label="🔵 Back from AFK", style=discord.ButtonStyle.primary)
    async def back_from_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        now = time.time()
        session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
        if session["status"] == "afk":
            session["afk_total"] += now - session.get("afk_start", now)
        session["online_start"] = now
        session["status"] = "online"
        await interaction.response.send_message("🟢 You are now marked as back from AFK.", ephemeral=True)

    @discord.ui.button(label="🔴 Offline", style=discord.ButtonStyle.danger)
    async def offline(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        now = time.time()
        session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
        if session["status"] == "online":
            session["online_total"] += now - session.get("online_start", now)
        elif session["status"] == "afk":
            session["afk_total"] += now - session.get("afk_start", now)
        session["status"] = "offline"
        await interaction.response.send_message("🔴 You are now marked as Offline.", ephemeral=True)

def format_time(seconds):
    return str(timedelta(seconds=int(seconds)))

@tasks.loop(seconds=30)
async def update_leaderboard():
    leaderboard_channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if leaderboard_channel:
        leaderboard_text = "**__📊 Leaderboard__**\n"
        status_text = "**__🟢 Live Status__**\n"
        for uid, session in user_sessions.items():
            member = leaderboard_channel.guild.get_member(uid)
            name = member.mention if member else f"<@{uid}>"
            total_online = session["online_total"]
            total_afk = session["afk_total"]
            now = time.time()
            if session["status"] == "online":
                total_online += now - session.get("online_start", now)
            elif session["status"] == "afk":
                total_afk += now - session.get("afk_start", now)
            leaderboard_text += f"{name} — Online: `{format_time(total_online)}`, AFK: `{format_time(total_afk)}`\n"
            status_text += f"{name} ➝ `{session['status'].upper()}`\n"
        messages = [msg async for msg in leaderboard_channel.history(limit=5)]
        if messages:
            await messages[0].edit(content=f"{leaderboard_text}\n{status_text}")
        else:
            await leaderboard_channel.send(f"{leaderboard_text}\n{status_text}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await tree.sync()
    panel_channel = bot.get_channel(PANEL_CHANNEL_ID)
    leaderboard_channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if panel_channel:
        await panel_channel.purge(limit=5)
        await panel_channel.send("**Playtime Tracker**\nClick your current status:", view=PlaytimeButtons())
    if leaderboard_channel:
        await leaderboard_channel.send("Loading leaderboard...\n🟢 Loading live status...")
    update_leaderboard.start()

bot.run(TOKEN)


@tree.command(name="add_time", description="Add online time to a user (admin only).")
async def add_time(interaction: discord.Interaction, member: discord.Member, seconds: int):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
        return
    uid = member.id
    user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
    user_sessions[uid]["online_total"] += seconds
    await interaction.response.send_message(f"✅ Added {seconds} seconds to {member.mention}.", ephemeral=True)

@tree.command(name="set_afk", description="Set a user to AFK (admin only).")
async def set_afk(interaction: discord.Interaction, member: discord.Member):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
        return
    uid = member.id
    now = time.time()
    session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
    if session["status"] == "online":
        session["online_total"] += now - session.get("online_start", now)
    session["afk_start"] = now
    session["status"] = "afk"
    await interaction.response.send_message(f"🌙 {member.mention} is now set to AFK.", ephemeral=True)

@tree.command(name="set_back_from_afk", description="Set a user back from AFK (admin only).")
async def set_back_from_afk(interaction: discord.Interaction, member: discord.Member):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
        return
    uid = member.id
    now = time.time()
    session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
    if session["status"] == "afk":
        session["afk_total"] += now - session.get("afk_start", now)
    session["online_start"] = now
    session["status"] = "online"
    await interaction.response.send_message(f"🟢 {member.mention} is now back from AFK.", ephemeral=True)

@tree.command(name="set_offline", description="Set a user to offline (admin only).")
async def set_offline(interaction: discord.Interaction, member: discord.Member):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
        return
    uid = member.id
    now = time.time()
    session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
    if session["status"] == "online":
        session["online_total"] += now - session.get("online_start", now)
    elif session["status"] == "afk":
        session["afk_total"] += now - session.get("afk_start", now)
    session["status"] = "offline"
    await interaction.response.send_message(f"🔴 {member.mention} has been set to offline.", ephemeral=True)

@tree.command(name="reset_leaderboard", description="Reset all user data (admin only).")
async def reset_leaderboard(interaction: discord.Interaction):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
        return
    user_sessions.clear()
    await interaction.response.send_message("♻️ Leaderboard has been reset.", ephemeral=True)

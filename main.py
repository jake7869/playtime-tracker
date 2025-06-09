import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import time
from datetime import timedelta
import re

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID", "1381017996524257442"))
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID", "1379861500877078721"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "1381056616362803330"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "1379861837075452035"))

user_sessions = {}
leaderboard_message = None
status_message = None
log_channel = None

def format_time(seconds):
    return str(timedelta(seconds=int(seconds)))

def parse_duration(duration_str):
    match = re.fullmatch(r"(\d+)([smh])", duration_str.strip().lower())
    if not match:
        return None
    value, unit = int(match[1]), match[2]
    return value * {"s": 1, "m": 60, "h": 3600}[unit]

async def log_to_discord(message):
    print("[LOG]", message)
    if log_channel:
        await log_channel.send(message)

class PlaytimeButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 Online", style=discord.ButtonStyle.success, custom_id="online")
    async def go_online(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.setdefault(uid, {"status": "offline", "online_total": 0, "afk_total": 0, "online_start": None, "afk_start": None})
        if session["status"] == "online":
            await interaction.response.send_message("You're already online.", ephemeral=True)
            return
        if session["status"] == "afk":
            session["afk_total"] += time.time() - session["afk_start"]
        session["online_start"] = time.time()
        session["status"] = "online"
        await interaction.response.send_message("You're now marked as online.", ephemeral=True)
        await log_to_discord(f"🟢 {interaction.user.display_name} is now ONLINE.")

    @discord.ui.button(label="🟡 AFK", style=discord.ButtonStyle.secondary, custom_id="afk")
    async def go_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.get(uid)
        if not session or session["status"] != "online":
            await interaction.response.send_message("You must be online to go AFK.", ephemeral=True)
            return
        session["online_total"] += time.time() - session["online_start"]
        session["afk_start"] = time.time()
        session["status"] = "afk"
        await interaction.response.send_message("You're now AFK.", ephemeral=True)
        await log_to_discord(f"🟡 {interaction.user.display_name} is now AFK.")

    @discord.ui.button(label="🔁 Back from AFK", style=discord.ButtonStyle.primary, custom_id="back_from_afk")
    async def back_from_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.get(uid)
        if not session or session["status"] != "afk":
            await interaction.response.send_message("You must be AFK to come back.", ephemeral=True)
            return
        session["afk_total"] += time.time() - session["afk_start"]
        session["online_start"] = time.time()
        session["status"] = "online"
        await interaction.response.send_message("You're now back from AFK.", ephemeral=True)
        await log_to_discord(f"🔁 {interaction.user.display_name} is back from AFK.")

    @discord.ui.button(label="🔴 Offline", style=discord.ButtonStyle.danger, custom_id="offline")
    async def go_offline(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.get(uid)
        if not session or session["status"] not in ["online", "afk"]:
            await interaction.response.send_message("You're already offline.", ephemeral=True)
            return
        now = time.time()
        if session["status"] == "online":
            session["online_total"] += now - session["online_start"]
        elif session["status"] == "afk":
            session["afk_total"] += now - session["afk_start"]
        session["status"] = "offline"
        session["online_start"] = None
        session["afk_start"] = None
        await interaction.response.send_message("You're now offline.", ephemeral=True)
        await log_to_discord(f"🔴 {interaction.user.display_name} is now OFFLINE.")

@bot.event
async def on_ready():
    global log_channel, leaderboard_message, status_message
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    guild = bot.guilds[0]
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    panel_channel = bot.get_channel(PANEL_CHANNEL_ID)
    leaderboard_channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)

    await bot.tree.sync()

    if panel_channel:
        await panel_channel.purge(limit=5)
        await panel_channel.send("**Playtime Tracker**\nClick your current status:", view=PlaytimeButtons())

    if leaderboard_channel:
        leaderboard_message = await leaderboard_channel.send("📊 Loading leaderboard...")
        status_message = await leaderboard_channel.send("🟢 Loading live status...")

    update_leaderboard.start()

@tasks.loop(seconds=30)
async def update_leaderboard():
    if not leaderboard_message or not status_message:
        return

    leaderboard_lines = ["🏆 **__Leaderboard__**"]
    status_lines = ["📶 **Live Status**"]
    sorted_users = sorted(user_sessions.items(), key=lambda x: x[1]["online_total"], reverse=True)

    for i, (uid, session) in enumerate(sorted_users, start=1):
        online = session["online_total"]
        afk = session["afk_total"]
        if session["status"] == "online":
            online += time.time() - session["online_start"]
        elif session["status"] == "afk":
            afk += time.time() - session["afk_start"]

        name = f"<@{uid}>"
        line = (
            f"{i}. **{name}**
"
            f"   ⏱️ Online: `{format_time(online)}` | 💤 AFK: `{format_time(afk)}`"
        )
        leaderboard_lines.append(line)

        icon = "🟢" if session["status"] == "online" else "🟡" if session["status"] == "afk" else "🔴"
        status_lines.append(f"{icon} {name} → **{session['status'].upper()}**")

    leaderboard_text = "
".join(leaderboard_lines) + "
━━━━━━━━━━━━━━━━━━"
    status_text = "
".join(status_lines)

    await leaderboard_message.edit(content=leaderboard_text)
    await status_message.edit(content=status_text)

print("🚀 Starting bot...")
bot.run(os.getenv("DISCORD_TOKEN"))
@bot.tree.command(name="add_time", description="Add online time to a user (admin only).")
@app_commands.describe(user="User to add time to", amount="Time to add (e.g. 10m, 2h)")
async def add_time(interaction: discord.Interaction, user: discord.Member, amount: str):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
        return
    seconds = parse_duration(amount)
    if seconds is None:
        await interaction.response.send_message("Invalid time format. Use s, m, or h (e.g. 10m).", ephemeral=True)
        return
    session = user_sessions.setdefault(user.id, {"status": "offline", "online_total": 0, "afk_total": 0, "online_start": None, "afk_start": None})
    session["online_total"] += seconds
    await interaction.response.send_message(f"✅ Added {amount} to {user.display_name}'s time.", ephemeral=True)
    await log_to_discord(f"⏫ **{interaction.user.display_name}** added {amount} to **{user.display_name}**.")

@bot.tree.command(name="remove_time", description="Remove online time from a user (admin only).")
@app_commands.describe(user="User to remove time from", amount="Time to remove (e.g. 10m, 2h)")
async def remove_time(interaction: discord.Interaction, user: discord.Member, amount: str):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
        return
    seconds = parse_duration(amount)
    if seconds is None:
        await interaction.response.send_message("Invalid time format. Use s, m, or h (e.g. 10m).", ephemeral=True)
        return
    session = user_sessions.setdefault(user.id, {"status": "offline", "online_total": 0, "afk_total": 0, "online_start": None, "afk_start": None})
    session["online_total"] = max(0, session["online_total"] - seconds)
    await interaction.response.send_message(f"✅ Removed {amount} from {user.display_name}'s time.", ephemeral=True)
    await log_to_discord(f"⏬ **{interaction.user.display_name}** removed {amount} from **{user.display_name}**.")

@bot.tree.command(name="set_afk", description="Force a user into AFK (admin only).")
@app_commands.describe(user="User to set AFK")
async def set_afk(interaction: discord.Interaction, user: discord.Member):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
        return
    session = user_sessions.setdefault(user.id, {"status": "offline", "online_total": 0, "afk_total": 0, "online_start": None, "afk_start": None})
    if session["status"] == "online":
        session["online_total"] += time.time() - session["online_start"]
    session["afk_start"] = time.time()
    session["status"] = "afk"
    await interaction.response.send_message(f"✅ {user.display_name} is now AFK.", ephemeral=True)
    await log_to_discord(f"🟡 {user.display_name} was set to AFK by admin.")

@bot.tree.command(name="set_back_from_afk", description="Bring a user back from AFK (admin only).")
@app_commands.describe(user="User to bring back from AFK")
async def set_back_from_afk(interaction: discord.Interaction, user: discord.Member):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
        return
    session = user_sessions.get(user.id)
    if not session or session["status"] != "afk":
        await interaction.response.send_message("User is not currently AFK.", ephemeral=True)
        return
    session["afk_total"] += time.time() - session["afk_start"]
    session["online_start"] = time.time()
    session["status"] = "online"
    await interaction.response.send_message(f"✅ {user.display_name} is now back from AFK.", ephemeral=True)
    await log_to_discord(f"🔁 {user.display_name} was brought back from AFK by admin.")

@bot.tree.command(name="set_offline", description="Set a user offline (admin only).")
@app_commands.describe(user="User to set offline")
async def set_offline(interaction: discord.Interaction, user: discord.Member):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
        return
    session = user_sessions.get(user.id)
    if not session or session["status"] == "offline":
        await interaction.response.send_message("User is already offline.", ephemeral=True)
        return
    now = time.time()
    if session["status"] == "online":
        session["online_total"] += now - session["online_start"]
    elif session["status"] == "afk":
        session["afk_total"] += now - session["afk_start"]
    session["status"] = "offline"
    session["online_start"] = None
    session["afk_start"] = None
    await interaction.response.send_message(f"✅ {user.display_name} is now offline.", ephemeral=True)
    await log_to_discord(f"🔴 {user.display_name} was set to OFFLINE by admin.")

@bot.tree.command(name="reset_leaderboard", description="Reset all playtime data (admin only).")
async def reset_leaderboard(interaction: discord.Interaction):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
        return
    user_sessions.clear()
    await interaction.response.send_message("✅ Leaderboard has been reset.", ephemeral=True)
    await log_to_discord(f"♻️ Leaderboard was reset by **{interaction.user.display_name}**.")
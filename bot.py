import random
import subprocess
import os
import discord
from discord.ext import commands, tasks
import asyncio
from discord import app_commands
import psutil
from datetime import datetime
import re
import time

# Configuration
TOKEN = ''  # REPLACE WITH YOUR BOT'S TOKEN
RAM_LIMIT = '2g'
SERVER_LIMIT = 12
LOGS_CHANNEL_ID = 123456789    # CHANGE TO YOUR LOGS CHANNEL ID
ADMIN_ROLE_ID = 123456789     # CHANGE TO YOUR ADMIN ROLE ID

database_file = 'database.txt'

intents = discord.Intents.default()
intents.messages = False
intents.message_content = False
intents.members = True  # Needed for role checking

bot = commands.Bot(command_prefix='/', intents=intents)

# Embed color constant
EMBED_COLOR = 0x9B59B6  # Purple color

# OS Options with fancy emojis and descriptions
OS_OPTIONS = {
    "ubuntu": {
        "image": "ubuntu-vps", 
        "name": "Ubuntu 22.04", 
        "emoji": "🐧",
        "description": "Stable and widely-used Linux distribution"
    },
    "debian": {
        "image": "debian-vps", 
        "name": "Debian 12", 
        "emoji": "🦕",
        "description": "Rock-solid stability with large software repository"
    },
    "alpine": {
        "image": "alpine-vps", 
        "name": "Alpine Linux", 
        "emoji": "⛰️",
        "description": "Lightweight and security-focused"
    },
    "arch": {
        "image": "arch-vps", 
        "name": "Arch Linux", 
        "emoji": "🎯",
        "description": "Rolling release with bleeding-edge software"
    },
    "kali": {
        "image": "kali-vps", 
        "name": "Kali Linux", 
        "emoji": "💣",
        "description": "Penetration testing and security auditing"
    },
    "fedora": {
        "image": "fedora-vps", 
        "name": "Fedora", 
        "emoji": "🎩",
        "description": "Innovative features with Red Hat backing"
    }
}

# Animation frames for different states
LOADING_ANIMATION = ["🔄", "⚡", "✨", "🌀", "🌪️", "🌈"]
SUCCESS_ANIMATION = ["✅", "🎉", "✨", "🌟", "💫", "🔥"]
ERROR_ANIMATION = ["❌", "💥", "⚠️", "🚨", "🔴", "🛑"]
DEPLOY_ANIMATION = ["🚀", "🛰️", "🌌", "🔭", "👨‍🚀", "🪐"]

async def is_admin(interaction: discord.Interaction) -> bool:
    """Check if the user has admin role or administrator permissions"""
    if interaction.user.guild_permissions.administrator:
        return True
    return any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles)

async def is_admin_role_only(interaction: discord.Interaction) -> bool:
    """Check if the user has the specific admin role."""
    return any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles)

def generate_random_port():
    return random.randint(1025, 65535)

def add_to_database(user, container_name, ssh_command):
    with open(database_file, 'a') as f:
        f.write(f"{user}|{container_name}|{ssh_command}\n")

def remove_from_database(ssh_command):
    if not os.path.exists(database_file):
        return
    with open(database_file, 'r') as f:
        lines = f.readlines()
    with open(database_file, 'w') as f:
        for line in lines:
            if ssh_command not in line:
                f.write(line)

def remove_container_from_database_by_id(container_id):
    if not os.path.exists(database_file):
        return
    with open(database_file, 'r') as f:
        lines = f.readlines()
    with open(database_file, 'w') as f:
        for line in lines:
            parts = line.strip().split('|')
            if len(parts) < 2 or parts[1] != container_id:
                f.write(line)

def get_container_info_by_id(container_id):
    if not os.path.exists(database_file):
        return None, None, None
    with open(database_file, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 3 and parts[1].startswith(container_id):
                return parts[0], parts[1], parts[2]
    return None, None, None

def clear_database():
    if os.path.exists(database_file):
        os.remove(database_file)

async def capture_ssh_session_line(process):
    while True:
        output = await process.stdout.readline()
        if not output:
            break
        output = output.decode('utf-8').strip()
        if "ssh session:" in output:
            return output.split("ssh session:")[1].strip()
    return None

def get_user_servers(user):
    if not os.path.exists(database_file):
        return []
    servers = []
    with open(database_file, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 3 and parts[0] == user:
                servers.append(line.strip())
    return servers

def get_all_servers():
    if not os.path.exists(database_file):
        return []
    servers = []
    with open(database_file, 'r') as f:
        for line in f:
            servers.append(line.strip())
    return servers

def count_user_servers(user):
    return len(get_user_servers(user))

def get_container_id_from_database(user, container_name):
    if not os.path.exists(database_file):
        return None
    with open(database_file, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 3 and parts[0] == user and container_name in parts[1]:
                return parts[1]
    return None

def get_system_resources():
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        mem_total = mem.total / (1024 ** 3)
        mem_used = mem.used / (1024 ** 3)
        disk = psutil.disk_usage('/')
        disk_total = disk.total / (1024 ** 3)
        disk_used = disk.used / (1024 ** 3)
        
        return {
            'cpu': cpu_percent,
            'memory': {'total': round(mem_total, 2), 'used': round(mem_used, 2), 'percent': mem.percent},
            'disk': {'total': round(disk_total, 2), 'used': round(disk_used, 2), 'percent': disk.percent}
        }
    except Exception:
        return {
            'cpu': 0,
            'memory': {'total': 0, 'used': 0, 'percent': 0},
            'disk': {'total': 0, 'used': 0, 'percent': 0}
        }

def get_container_stats():
    """Get CPU and memory usage for all running containers."""
    try:
        stats_raw = subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format", "{{.ID}}|{{.CPUPerc}}|{{.MemUsage}}"],
            text=True
        ).strip().split('\n')
        
        stats = {}
        for line in stats_raw:
            parts = line.split('|')
            if len(parts) >= 3:
                container_id = parts[0]
                cpu_percent = parts[1].strip()
                mem_usage_raw = parts[2].strip()

                mem_match = re.match(r"(\d+(\.\d+)?\w+)\s+/\s+(\d+(\.\d+)?\w+)", mem_usage_raw)
                
                mem_used = 'N/A'
                mem_limit = 'N/A'
                
                if mem_match:
                    mem_used = mem_match.group(1)
                    mem_limit = mem_match.group(3)
                else:
                    mem_used = '0B'
                    mem_limit = '0B'

                stats[container_id] = {
                    'cpu': cpu_percent,
                    'mem_used': mem_used,
                    'mem_limit': mem_limit
                }
        return stats
    except Exception as e:
        print(f"Error getting container stats: {e}")
        return {}

async def animate_message(message, embed, animation_frames, duration=5):
    """Animate a message with changing emojis"""
    start_time = time.time()
    frame_index = 0
    
    while time.time() - start_time < duration:
        embed.set_author(name=f"{animation_frames[frame_index]} {message}")
        try:
            await interaction.edit_original_response(embed=embed)
        except:
            pass
        
        frame_index = (frame_index + 1) % len(animation_frames)
        await asyncio.sleep(0.5)

@bot.event
async def on_ready():
    change_status.start()
    print(f'✨ Bot is ready. Logged in as {bot.user} ✨')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@tasks.loop(seconds=5)
async def change_status():
    try:
        instance_count = len(open(database_file).readlines()) if os.path.exists(database_file) else 0
        statuses = [  
            f"🌠 Managing {instance_count} Cloud Instances",  
            f"⚡ Powering {instance_count} Servers",  
            f"🔮 Watching over {instance_count} VMs",
            f"🚀 Hosting {instance_count} Dreams",
            f"💻 Serving {instance_count} Terminals",
            f"🌐 Running {instance_count} Nodes"
        ]  
        await bot.change_presence(activity=discord.Game(name=random.choice(statuses)))  
    except Exception as e:  
        print(f"💥 Failed to update status: {e}")

async def send_to_logs(message):
    try:
        channel = bot.get_channel(LOGS_CHANNEL_ID)
        if channel:
            perms = channel.permissions_for(channel.guild.me)
            if perms.send_messages:
                timestamp = datetime.now().strftime("%H:%M:%S")
                await channel.send(f"`[{timestamp}]` {message}")
    except Exception as e:
        print(f"Failed to send logs: {e}")

@bot.tree.command(name="deploy", description="🚀 [ADMIN] Create a new cloud instance for a user")
@app_commands.describe(
    user="The user to deploy for",
    os="The OS to deploy (ubuntu, debian, alpine, arch, kali, fedora)"
)
async def deploy(interaction: discord.Interaction, user: discord.User, os: str):
    try:
        if not await is_admin_role_only(interaction):
            embed = discord.Embed(
                title="🚫 Permission Denied",
                description="This command is restricted to administrators only.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        os = os.lower()
        if os not in OS_OPTIONS:
            valid_oses = "\n".join([f"{OS_OPTIONS[os_id]['emoji']} **{os_id}** - {OS_OPTIONS[os_id]['description']}" 
                                   for os_id in OS_OPTIONS.keys()])
            embed = discord.Embed(
                title="❌ Invalid OS Selection",
                description=f"**Available OS options:**\n{valid_oses}",
                color=EMBED_COLOR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        os_data = OS_OPTIONS[os]
        
        # Initial response with loading animation
        embed = discord.Embed(
            title=f"🚀 Launching {os_data['emoji']} {os_data['name']} Instance",
            description=f"```diff\n+ Preparing magical {os_data['name']} experience for {user.display_name}...\n```",
            color=EMBED_COLOR
        )
        embed.add_field(
            name="🛠️ System Info",
            value=f"```RAM: {RAM_LIMIT}\nAuto-Delete: 4h Inactivity```",
            inline=False
        )
        embed.set_footer(text="This may take 1-2 minutes...")
        
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()

        # Animate the loading process
        await animate_message("Initializing Deployment", embed, DEPLOY_ANIMATION, 3)

        try:  
            # Step 1: Container creation
            embed.clear_fields()
            embed.description = "```diff\n+ Pulling container image from repository...\n```"
            await msg.edit(embed=embed)
            
            container_id = subprocess.check_output(
                ["docker", "run", "-itd", "--privileged", os_data["image"]]
            ).strip().decode('utf-8')  
            
            await send_to_logs(f"🔧 {interaction.user.mention} deployed {os_data['emoji']} {os_data['name']} for {user.mention} (ID: `{container_id[:12]}`)")
            
            # Step 2: SSH setup
            embed.description = "```diff\n+ Configuring SSH access and security...\n```"
            await msg.edit(embed=embed)
            await animate_message("Configuring SSH", embed, LOADING_ANIMATION, 2)

            exec_cmd = await asyncio.create_subprocess_exec(
                "docker", "exec", container_id, "tmate", "-F",
                stdout=asyncio.subprocess.PIPE, 
                stderr=asyncio.subprocess.PIPE
            )  
            
            ssh_session_line = await capture_ssh_session_line(exec_cmd)
            
            if ssh_session_line:  
                # Success - send to admin and user
                admin_embed = discord.Embed(  
                    title=f"🎉 {os_data['emoji']} {os_data['name']} Instance Ready!",  
                    description=f"**Successfully deployed for {user.mention}**\n\n**🔑 SSH Command:**\n```{ssh_session_line}```",  
                    color=0x00FF00
                )
                admin_embed.add_field(
                    name="📦 Container Info",
                    value=f"```ID: {container_id[:12]}\nOS: {os_data['name']}\nStatus: Running```",
                    inline=False
                )
                admin_embed.set_footer(text="💎 This instance will auto-delete after 4 hours of inactivity")
                await interaction.followup.send(embed=admin_embed, ephemeral=True)
                
                try:
                    user_embed = discord.Embed(  
                        title=f"✨ Your {os_data['name']} Instance is Ready!",  
                        description=f"**SSH Access Details:**\n```{ssh_session_line}```\n\nDeployed by: {interaction.user.mention}",  
                        color=EMBED_COLOR  
                    )
                    user_embed.add_field(
                        name="💡 Getting Started",
                        value="```Connect using any SSH client\nUsername: root\nNo password required```",
                        inline=False
                    )
                    user_embed.set_footer(text="💎 This instance will auto-delete after 4 hours of inactivity")
                    await user.send(embed=user_embed)
                except discord.Forbidden:
                    pass
                
                add_to_database(str(user), container_id, ssh_session_line)  
                
                # Final success message
                embed = discord.Embed(  
                    title=f"✅ Deployment Complete! {random.choice(SUCCESS_ANIMATION)}",  
                    description=f"**{os_data['emoji']} {os_data['name']}** instance created for {user.mention}!",
                    color=0x00FF00  
                )  
                embed.set_thumbnail(url="https://i.imgur.com/W7D8e3i.png")  # Success icon
                await msg.edit(embed=embed)
            else:  
                embed = discord.Embed(  
                    title=f"⚠️ Timeout {random.choice(ERROR_ANIMATION)}",  
                    description="```diff\n- SSH configuration timed out...\n- Rolling back deployment\n```",  
                    color=0xFF0000  
                )  
                await msg.edit(embed=embed)
                subprocess.run(["docker", "kill", container_id], stderr=subprocess.DEVNULL)  
                subprocess.run(["docker", "rm", container_id], stderr=subprocess.DEVNULL)
                
        except subprocess.CalledProcessError as e:  
            embed = discord.Embed(  
                title=f"❌ Deployment Failed {random.choice(ERROR_ANIMATION)}",  
                description=f"```diff\n- Error during deployment:\n{e}\n```",  
                color=0xFF0000  
            )  
            await msg.edit(embed=embed)
            await send_to_logs(f"💥 Deployment failed for {user.mention} by {interaction.user.mention}: {e}")
            
    except Exception as e:
        print(f"Error in deploy command: {e}")
        try:
            embed = discord.Embed(
                title="💥 Critical Error",
                description="```diff\n- An unexpected error occurred\n- Please try again later\n```",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed)
        except:
            pass

@bot.tree.command(name="start", description="🟢 Start your cloud instance")
@app_commands.describe(container_id="Your instance ID (first 4+ characters)")
async def start_server(interaction: discord.Interaction, container_id: str):
    try:
        user = str(interaction.user)
        container_info = None
        ssh_command = None
        
        if not os.path.exists(database_file):
            embed = discord.Embed(  
                title="📭 No Instances Found",  
                description="You don't have any active instances!",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)  
            return

        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 3 and user == parts[0] and container_id in parts[1]:
                    container_info = parts[1]
                    ssh_command = parts[2]
                    break

        if not container_info:  
            embed = discord.Embed(  
                title="🔍 Instance Not Found",  
                description="No instance found with that ID that belongs to you!",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)  
            return  

        # Initial response with loading animation
        embed = discord.Embed(
            title=f"🔌 Starting Instance {container_info[:12]}",
            description="```diff\n+ Powering up your cloud instance...\n```",
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        
        await animate_message("Booting System", embed, LOADING_ANIMATION, 2)

        try:  
            check_cmd = subprocess.run(
                ["docker", "inspect", "--format='{{.State.Status}}'", container_info], 
                capture_output=True, text=True
            )
            
            if check_cmd.returncode != 0:
                embed = discord.Embed(  
                    title="❌ Container Not Found",  
                    description=f"Container `{container_info[:12]}` doesn't exist in Docker!",
                    color=0xFF0000  
                )  
                await msg.edit(embed=embed)
                remove_from_database(ssh_command)
                return
            
            subprocess.run(["docker", "start", container_info], check=True)
            
            try:
                embed.description = "```diff\n+ Generating new SSH connection...\n```"
                await msg.edit(embed=embed)
                
                exec_cmd = await asyncio.create_subprocess_exec(
                    "docker", "exec", container_info, "tmate", "-F",
                    stdout=asyncio.subprocess.PIPE, 
                    stderr=asyncio.subprocess.PIPE
                )  
                ssh_session_line = await capture_ssh_session_line(exec_cmd)
                
                if ssh_session_line:
                    remove_from_database(ssh_command)
                    add_to_database(user, container_info, ssh_session_line)
                    
                    try:
                        dm_embed = discord.Embed(  
                            title=f"🟢 Instance Started {random.choice(SUCCESS_ANIMATION)}",  
                            description=f"**Your instance is now running!**\n\n**🔑 New SSH Command:**\n```{ssh_session_line}```",  
                            color=0x00FF00  
                        )
                        dm_embed.add_field(
                            name="💡 Note",
                            value="The old S

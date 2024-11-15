"""
This is a main program file for the bot
"""

import discord

import os
import json

from Models.ReturnInfo import ReturnInfo

from constants import *

settings = {}
client = discord.Client(intents=discord_intents)
command_tree = discord.app_commands.CommandTree(client)

# Function to load all the settings and assign them to a global variable
def load_settings(setting_path: str = settings_filename, required_keys: list = []) -> ReturnInfo:
    global settings
    result = ReturnInfo(returnCode=0, Messages={
        1: f'Error: File \"{setting_path}\" not found',
        2: 'Error: Unable to open the file',
        3: 'Error: Unable to read json',
        4: 'Error: Missing required key(s): {}'
    })
    if os.path.isfile(setting_path):
        try:
            with open(setting_path, 'r') as setting_file:
                settings_temp = json.load(setting_file)
            missing_keys = []
            for key in required_keys:
                if not key in settings_temp.keys():
                    result.returnCode = 4
                    missing_keys.append(key)
            if result:
                settings = settings_temp
            else:
                result.format_message(4, missing_keys)
        except IOError:
            result.returnCode = 2
        except json.JSONDecodeError:
            result.returnCode = 3
        except:
            result.returnCode = -1
    else:
        result.returnCode = 1
    return result

# Easier way to get a setting without worrying if it's been set if it's negligable
def get_setting(setting_name: str, type_of_setting: type = str) -> str | int | bool:
    if setting_name in settings.keys():
        return settings[setting_name]
    if type_of_setting == str:
        return ''
    if type_of_setting == int:
        return 0
    if type_of_setting == bool:
        return False
    return None

# Sets up commands that require context earlier
def set_up_functions() -> None:
    if get_setting('home_guild_id') != '':
        global turn_off_bot_command
        @command_tree.command(
            name='off',
            description=get_setting('off_command_description'),
            guild=discord.Object(id=settings['home_guild_id'])
        )
        async def turn_off_bot_command(context: discord.Interaction):
            await context.response.send_message('Turning off bot...')
            await client.close()
    else:
        print('Unable to set up off command')

# Called when bot connects to discord
@client.event
async def on_ready() -> None:
    print(f'Logged in as {client.user.name}')
    print(client.user.id)
    set_up_functions()

# Main function of the program
def main() -> None:
    result = load_settings(required_keys=required_settings)
    if not result:
        print(result)
        return
    client.run(settings['app_token'])

if __name__ == '__main__':
    main()
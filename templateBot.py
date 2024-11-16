"""
This is a main program file for the bot
"""

import discord

import logging
import os
import json
import sys

from datetime import datetime
from Models.ReturnInfo import ReturnInfo

from constants import *

settings = {}
client = discord.Client(intents=discord_intents)
command_tree = discord.app_commands.CommandTree(client)

logger = logging.getLogger(__name__)
logging_into_file = False

# Prints out output both to stdout/stderr and potentially to a file 
def log_output(output_string: str, level: int = logging.INFO) -> None:
    level_name = ''
    string_levels = {
        logging.INFO: 'INFO',
        logging.ERROR: 'ERROR',
        logging.CRITICAL: 'CRITICAL'
    }
    for level_int, level_str in string_levels.items():
        if level_int == level:
            level_name = level_str
            break
    print_file = sys.stderr if level in (logging.ERROR, logging.CRITICAL) else sys.stdout
    timestamp = datetime.now().strftime(date_format)
    if logging_into_file:
        logger.log(level, output_string)
    print(f'{timestamp} {level_name}\t{__name__} {output_string}', file=print_file)

# Function to load all the settings and assign them to a global variable
def load_settings(setting_path: str = settings_filename, required_keys: list = []) -> ReturnInfo:
    global settings
    result = ReturnInfo(returnCode=0, Messages={
        1: f'File \"{setting_path}\" not found',
        2: 'Unable to open the file',
        3: 'Unable to read json',
        4: 'Missing required key(s): {}'
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
        log_output('Unable to set up off command', level=logging.ERROR)

# Called when bot connects to discord
@client.event
async def on_ready() -> None:
    log_output(f'Logged in as {client.user.name}')
    log_output(client.user.id)
    set_up_functions()

# Main function of the program
def main() -> None:
    global logging_into_file
    result = load_settings(required_keys=required_settings)
    if not result:
        log_output(result, level=logging.CRITICAL)
        return
    
    log_filename = get_setting('log_file')
    if log_filename == '':
        log_output('No logging file ha been set. Logging into file will not be possible', level=logging.ERROR)
    else:
        logging.basicConfig(
            filename=log_filename,
            encoding='utf-8',
            filemode='a',
            level=logging.DEBUG,
            format='%(asctime)s %(levelname)s\t%(name)s %(message)s',
            datefmt=date_format
        )
        logging_into_file = True

    try:
        client.run(settings['app_token'])
    except discord.errors.LoginFailure:
        log_output('There was a problem with logging in. Check your app token in the settings file', level=logging.CRITICAL)
        return

if __name__ == '__main__':
    main()
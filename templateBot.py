"""
This is a main program file for the bot
"""

import discord

import logging
import sys

from datetime import datetime

from constants import discord_intents, date_format, main_required_settings
from functions.utils import load_settings, get_setting

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

# Sets up commands that require context earlier
def set_up_functions() -> None:
    if get_setting(settings, 'home_guild_id') != '':
        global turn_off_bot_command
        @command_tree.command(
            name='off',
            description=get_setting(settings, 'off_command_description'),
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
    global settings
    result = load_settings(required_keys=main_required_settings)
    if not result:
        log_output(result, level=logging.CRITICAL)
        return
    settings = result.returnValue

    log_filename = get_setting(settings, 'log_file')
    if not log_filename:
        log_output('No logging file has been set. Logging into file will not be possible', level=logging.ERROR)
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
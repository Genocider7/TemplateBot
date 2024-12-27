"""
This is a main program file for the bot
"""

import discord
from discord.app_commands import describe as command_describe

import logging
import sys

from datetime import datetime

from constants import discord_intents, date_format, main_required_settings, db_required_settings, default_color_hex
from functions.utils import load_settings, get_setting, load_descriptions, get_description
from functions.database_functions import connect_database

from commands import setup_commands, turn_off_command_prototype, create_template_command_prototype, view_command_prototype, add_field_command_prototype, remove_field_command_prototype

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
    command_guilds = []
    if get_setting('testing', bool) and get_setting('home_guild_id', bool):
        command_guilds.append(discord.Object(id=get_setting('home_guild_id')))
    # Command to turn off bot, should only be in a home guild
    if get_setting('home_guild_id', bool):
        try:
            global turn_off_bot_command
            @command_tree.command(
                name='off',
                description=get_description('turn_off_command'),
                guild=discord.Object(id=get_setting('home_guild_id'))
            )
            async def turn_off_bot_command(context: discord.Interaction) -> None:
                return await turn_off_command_prototype(context)
        except discord.app_commands.CommandAlreadyRegistered:
            pass #if command already registered there's no need to do anything. Could add logging this part later
    else:
        log_output('Unable to set up off command', level=logging.ERROR)
    # Command to create a template
    global create_template_command
    try:
        @command_tree.command(
            name='create_template',
            description=get_description('create_template_command'),
            guilds=command_guilds
        )
        @command_describe(
            template=get_description('template_option'),
            template_number=get_description('template_number_option')
        )
        async def create_template_command(context: discord.Interaction, template: discord.Attachment, template_number: discord.app_commands.Range[int, 1, 3]) -> None:
            return await create_template_command_prototype(context, template, template_number)
    except discord.app_commands.CommandAlreadyRegistered:
        pass 
    # Command to view templates
    global view_command
    try:
        @command_tree.command(
            name='view',
            description=get_description('view_command'),
            guilds=command_guilds
        )
        @command_describe(
            template_number=get_description('template_number_option'),
            show_fields=get_description('show_fields_option')
        )
        async def view_command(context: discord.Interaction, template_number: discord.app_commands.Range[int, 1, 3] = 0, show_fields: bool = False) -> None:
            return await view_command_prototype(context, template_number, show_fields)
    except discord.app_commands.CommandAlreadyRegistered:
        pass
    #command to add field
    global add_field_command
    try:
        @command_tree.command(
            name='add_field',
            description=get_description('add_field_command'),
            guilds=command_guilds
        )
        @command_describe(
            field_type=get_description('field_type_option'),
            name=get_description('name_option'),
            template_number=get_description('template_number_option'),
            up_bound=get_description('top_bound_option'),
            left_bound=get_description('left_bound_option'),
            down_bound=get_description('down_bound_option'),
            right_bound=get_description('right_bound_option'),
            reference_image=get_description('reference_image_option'),
        )
        @discord.app_commands.choices(field_type=[
            discord.app_commands.Choice(name='Text', value='text'),
            discord.app_commands.Choice(name='Image', value='image')
        ])
        async def add_field_command(context: discord.Interaction, field_type: discord.app_commands.Choice[str], name: str, template_number: discord.app_commands.Range[int, 1, 3], up_bound: int | None = None, left_bound: int | None = None, down_bound: int | None = None, right_bound: int | None = None, reference_image: discord.Attachment | None = None, color: str = default_color_hex) -> None:
            return await add_field_command_prototype(context, field_type, name, template_number, up_bound, left_bound, down_bound, right_bound, reference_image, color)
    except discord.app_commands.CommandAlreadyRegistered:
        pass
    #command to remove field
    global remove_field_command
    try:
        @command_tree.command(
            name='remove_field',
            description=get_description('remove_field_command'),
            guilds=command_guilds
        )
        @command_describe(
            template_number=get_description('template_number_option'),
            field_name=get_description('field_name_option')
        )
        async def remove_field_command(context: discord.Interaction, template_number: discord.app_commands.Range[int, 1, 3], field_name: str):
            return await remove_field_command_prototype(context, template_number, field_name)
    except discord.app_commands.CommandAlreadyRegistered:
        pass

# Called when bot connects to discord
@client.event
async def on_ready() -> None:
    log_output(f'Logged in as {client.user.name}')
    log_output(client.user.id)
    set_up_functions()
    if '--global-sync' in sys.argv or ('--sync' in sys.argv and not get_setting('testing', bool)):
        await command_tree.sync()
        log_output('synced slash commands globally')
    if '--sync' in sys.argv and get_setting('testing', bool) and get_setting('home_guild_id', bool):
        await command_tree.sync(guild=discord.Object(id=get_setting('home_guild_id')))
        log_output('synced slash commands in home server')

@client.event
async def on_disconnect() -> None:
    if not db_handle is None and db_handle.is_connected():
        if not db_cursor is None:
            db_cursor.close()
        db_handle.close()
        log_output('Database disconnected')

# Main function of the program
def main() -> None:
    global logging_into_file
    global db_handle
    global db_cursor
    result = load_settings(required_keys=main_required_settings + db_required_settings)
    if not result:
        log_output(result, level=logging.CRITICAL)
        return

    log_filename = get_setting('log_file')
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

    result = connect_database(get_setting('db_username'), get_setting('db_password'), get_setting('database_name'))
    if not result:
        log_output(result, level=logging.CRITICAL)
        return
    db_handle, db_cursor = result.returnValue

    result = load_descriptions(db_cursor)
    if not result:
        log_output(result, level=logging.ERROR)
        log_output('Unable to access descriptions. Descriptions might be missing', level=logging.ERROR)

    data_for_commands = {
        'client': client,
        'db_cursor': db_cursor,
        'db_handle': db_handle,
        'logging_ref': log_output
    }
    success = setup_commands(data_for_commands)
    if not success:
        log_output('Unable to setupcommands', logging.CRITICAL)

    try:
        client.run(get_setting('app_token'))
    except discord.errors.LoginFailure:
        log_output('There was a problem with logging in. Check your app token in the settings file', level=logging.CRITICAL)
        return

if __name__ == '__main__':
    main()
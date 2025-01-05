"""
This is a main program file for the bot
"""

import discord
from discord.app_commands import describe as command_describe

import asyncio
import logging
import sys
from shutil import move as move_file
from os import makedirs, path

from datetime import datetime, date
from zoneinfo import ZoneInfo

from constants import discord_intents, logging_format, date_format, main_required_settings, db_required_settings, default_color_hex, project_name, absolute_path_to_project, log_file_split_check_timer
from functions.utils import load_settings, get_setting, load_descriptions, get_description, custom_time
from functions.database_functions import connect_database, set_logger as set_database_logger
from functions.ReturnInfo import ReturnInfo

from commands import setup_commands, reconnect_database as commands_reconnect_database, turn_off_command_prototype, create_template_command_prototype, view_command_prototype, add_field_command_prototype, remove_field_command_prototype, use_template_command_prototype, fill_image_field_command_prototype, fill_text_field_command_prototype, using_template_check, possible_fonts

client = discord.Client(intents=discord_intents)
command_tree = discord.app_commands.CommandTree(client)

logger = None
log_handler = None
logging_into_file = False

sql_logger = None
sql_log_handler = None

log_date = None
timezone = None

def get_discord_loggers() -> dict[str, logging.Logger]:
    discord_loggers = {}
    for logger_name, logger_ref in logging.root.manager.loggerDict.items():
        if logger_name.startswith('discord.'):
            if isinstance(logger_ref, logging.PlaceHolder):
                logger_ref = logging.getLogger(logger_name)
            discord_loggers[logger_name] = logger_ref
    return discord_loggers

def setup_logging(log_filename: str = '', sql_log_filename: str = '') -> ReturnInfo:
    global logger
    global log_handler
    global sql_logger
    global sql_log_handler
    ret = ReturnInfo(Messages={
        1: 'No file handlers found. Logging into file will not be possible',
        2: 'More than 1 file handlers found. Logging into file will not be possible'
    })
    if log_filename:
        logging.basicConfig(
            filemode='a',
            level=logging.DEBUG,
            format=logging_format,
            datefmt=date_format
        )
        logger = logging.getLogger()
        logger.name = project_name
        formatter = logging.Formatter(logging_format, date_format)
        formatter.converter = custom_time
        log_handler = logging.FileHandler(log_filename, encoding='utf-8')
        log_handler.setFormatter(formatter)
        log_handler.setLevel(logging.DEBUG)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.DEBUG)
        logger.handlers = [log_handler, stream_handler]
        for logger_ref in get_discord_loggers().values():
            logger_ref.handlers = [log_handler, stream_handler]
            logger_ref.propagate = False
    if sql_log_filename:
        formatter = logging.Formatter(logging_format, date_format)
        formatter.converter = custom_time
        sql_log_handler = logging.FileHandler(sql_log_filename, encoding='utf-8')
        sql_log_handler.setFormatter(formatter)
        sql_log_handler.setLevel(logging.INFO)
        sql_logger = logging.getLogger('mysql_template_bot')
        sql_logger.addHandler(sql_log_handler)
        sql_logger.setLevel(logging.INFO)
        sql_logger.propagate = False
        set_database_logger(sql_logger)
    return ret

def seperate_log_file():
    global log_date
    if not all((get_setting('log_dir', bool), get_setting('log_file', bool), logging_into_file)) or any((item is None for item in (logger, log_handler, log_date))):
        return
    today = datetime.now(timezone).date()
    makedirs(get_setting('log_dir', str), exist_ok=True)
    if log_date < today:
        log_handler.close()
        logger.removeHandler(log_handler)
        log_filename = path.join(absolute_path_to_project, get_setting('log_file', str))
        date_formatted = log_date.strftime('%Y_%m_%d')
        target_filename = path.join(absolute_path_to_project, get_setting('log_dir'), date_formatted + '_' + get_setting('log_file', str))
        counter = 1
        while path.exists(target_filename):
            (basename, ext) = path.splitext(get_setting('log_file', str))
            target_filename = path.join(absolute_path_to_project, get_setting('log_dir'), date_formatted + '_' + basename + '_' + str(counter) + '.' + ext)
            counter += 1
        move_file(log_filename, target_filename)
        if isinstance(sql_logger, logging.Logger) and get_setting('mysql_log_file', bool):
            sql_log_handler.close()
            sql_logger.removeHandler(sql_log_handler)
            mysql_log_filename = path.join(absolute_path_to_project, get_setting('mysql_log_file', str))
            date_formatted = log_date.strftime('%Y_%m_%d')
            target_filename = path.join(absolute_path_to_project, get_setting('log_dir'), date_formatted + '_' + get_setting('mysql_log_file', str))
            counter = 1
            while path.exists(target_filename):
                (basename, ext) = path.splitext(get_setting('mysql_log_file', str))
                target_filename = path.join(absolute_path_to_project, get_setting('log_dir'), date_formatted + '_' + basename + '_' + str(counter) + ext)
                counter += 1
            move_file(mysql_log_filename, target_filename)
        else:
            mysql_log_filename = ''
        result = setup_logging(log_filename, mysql_log_filename)
        if not result:
            log_output(result, logging.ERROR)
            
        log_date = today
    asyncio.get_running_loop().call_later(log_file_split_check_timer, seperate_log_file)

# Prints out output both to stdout/stderr and potentially to a file 
def log_output(output_string: str, level: int = logging.INFO, exc_info: bool = False) -> None:
    if logging_into_file:
        logger.log(level, output_string, exc_info=exc_info)
    else:
        string_levels = {
            logging.INFO: 'INFO',
            logging.ERROR: 'ERROR',
            logging.CRITICAL: 'CRITICAL',
            logging.WARNING: 'WARNING'
        }
        level_name = string_levels[level] if level in string_levels.keys() else ''
        print_file = sys.stderr if level in (logging.ERROR, logging.CRITICAL) else sys.stdout
        timestamp = datetime.now(timezone).strftime(date_format)
        values = {
            'asctime': timestamp,
            'levelname': level_name,
            'name': project_name,
            'message': output_string
        }
        print(logging_format % values, file=print_file)

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
            color=get_description('reference_color_option'),
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
        async def remove_field_command(context: discord.Interaction, template_number: discord.app_commands.Range[int, 1, 3], field_name: str) -> None:
            return await remove_field_command_prototype(context, template_number, field_name)
    except discord.app_commands.CommandAlreadyRegistered:
        pass
    #command to use a template
    global use_template_command
    try:
        @command_tree.command(
            name='use_template',
            description=get_description('use_template_command'),
            guilds=command_guilds
        )
        @command_describe(
            template_number=get_description('template_number_option')
        )
        async def use_template_command(context: discord.Interaction, template_number: discord.app_commands.Range[int, 1, 3]) -> None:
            return await use_template_command_prototype(context, template_number)
    except discord.app_commands.CommandAlreadyRegistered:
        pass
    #command to fill out a text field
    global fill_text_field_command
    try:
        @command_tree.command(
            name='fill_text_field',
            description=get_description('fill_text_field_command'),
            guilds=command_guilds
        )
        @command_describe(
            field_name=get_description('field_name_option'),
            text=get_description('text_option'),
            font=get_description('font_option'),
            font_size=get_description('font_size_option'),
            color=get_description('color_option')
        )
        @discord.app_commands.choices(font=[discord.app_commands.Choice(name=font_name, value=font_name) for font_name in possible_fonts.keys()])
        @discord.app_commands.check(using_template_check)
        async def fill_text_field_command(context: discord.Interaction, field_name: str, text: str, font: discord.app_commands.Choice[str], font_size: float = 3., color: str = default_color_hex) -> None:
            return await fill_text_field_command_prototype(context, field_name, text, font, font_size, color)
    except discord.app_commands.CommandAlreadyRegistered:
        pass
    #command to fill out a image field
    global fill_image_field_command
    try:
        @command_tree.command(
            name='fill_image_field',
            description=get_description('fill_image_field_command'),
            guilds=command_guilds
        )
        @command_describe(
            field_name=get_description('field_name_option'),
            image=get_description('image_option')
        )
        @discord.app_commands.check(using_template_check)
        async def fill_image_field_command(context: discord.Interaction, field_name: str, image: discord.Attachment) -> None:
            return await fill_image_field_command_prototype(context, field_name, image)
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
    if '--sync' in sys.argv and get_setting('home_guild_id', bool):
        await command_tree.sync(guild=discord.Object(id=get_setting('home_guild_id')))
        log_output('synced slash commands in home server')
    if logging_into_file:
        seperate_log_file()

@client.event
async def on_disconnect() -> None:
    if not db_handle is None and db_handle.is_connected():
        if not db_cursor is None:
            db_cursor.close()
        db_handle.close()
        log_output('Database disconnected')

@client.event
async def on_resumed() -> None:
    global db_handle, db_cursor
    if db_handle is None or not db_handle.is_connected():
        result = connect_database(get_setting('db_username'), get_setting('db_password'), get_setting('database_name'))
        if not result:
            log_output(result, level=logging.CRITICAL)
            return
        db_handle, db_cursor = result.returnValue
        commands_reconnect_database(db_handle, db_cursor)
        log_output('Database reconnected')

@command_tree.error
async def on_error(context: discord.Interaction, error: discord.app_commands.AppCommandError) -> None:
    if type(error) == discord.app_commands.errors.CheckFailure:
        await context.response.send_message('You cannot use this command', ephemeral=True)
        return
    logging.error("An error occured", exc_info=True)

# Main function of the program
def main() -> None:
    global db_handle
    global db_cursor
    global timezone
    global logging_into_file
    global log_date
    result = load_settings(required_keys=main_required_settings + db_required_settings)
    if not result:
        log_output(result, level=logging.CRITICAL)
        return
    if get_setting('timezone', bool):
        timezone = ZoneInfo(get_setting('timezone', str))
    else:
        timezone = None

    log_filename = get_setting('log_file')
    if get_setting('log_file', bool):
        log_filename = path.join(absolute_path_to_project, get_setting('log_file', str))
        result = setup_logging(log_filename, get_setting('mysql_log_file', str))
        if result:
            logging_into_file = True
        else:
            log_output(result, logging.ERROR)
    else:
        log_output('No logging file has been set. Logging into file will not be possible', logging.ERROR)
    if not isinstance(sql_logger, logging.Logger):
        log_output('No logging for mysql has been set. Logging mysql queries to file will not be possible', logging.ERROR)
    
    if timezone is None:
        log_output('The timezone parameter has not been found in options or was set to None', logging.WARNING)

    if '--log-date' in sys.argv:
        position = sys.argv.index('--log-date')
        if position + 1 >= len(sys.argv):
            log_output('No date provided', logging.CRITICAL)
            return
        date_str = sys.argv[position + 1]
        try:
            log_date = datetime.fromisoformat(date_str).date()
        except ValueError:
            log_output('Incorrect date format. Use YYYY-MM-DD (ISO 8601 format)', logging.CRITICAL)
            return
    if not isinstance(log_date, date):
        log_date = datetime.now(timezone).date()        

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
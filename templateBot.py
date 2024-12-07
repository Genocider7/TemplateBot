"""
This is a main program file for the bot
"""

import discord
from discord.app_commands import describe as command_describe

import logging
import sys
import os.path
import asyncio

from os import remove as remove_file
from datetime import datetime

from constants import discord_intents, date_format, main_required_settings, db_required_settings, absolute_path_to_project
from functions.utils import load_settings, get_setting, load_descriptions, get_description
from functions.database_functions import connect_database, select as mysql_select, execute_query
from Models.ReturnInfo import ReturnInfo

settings = {}
descriptions = {}
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

async def register_template(user_id: int | str, template_number: int, file: discord.Attachment) -> ReturnInfo:
    ret = ReturnInfo(returnCode=0, Messages={
        1: "Saving image failed"
    })
    assert not file.content_type is None and file.content_type.startswith('image/')
    extension = file.content_type[(len('image/')):]
    filename = str(user_id) + '_' + str(template_number) + '.' + extension
    try:
        await file.save(os.path.join(absolute_path_to_project, 'Images', filename))
        query = 'INSERT INTO images (image_extension, user_id, enumeration, created_at) VALUES (\"{}\", \"{}\", {}, NOW())'.format(extension, user_id, template_number)
        result = execute_query(db_handle, db_cursor, query)
        if not result:
            return result
    except discord.HTTPException:
        ret.returnCode = 1
        return ret
    return ret

def delete_template(user_id: int | str, template_number: int, filename: str | None = None) -> ReturnInfo:
    if filename is None:
        query = 'SELECT CONCAT(im.user_id, "_", im.enumeration, ".", im.image_extension) FROM images AS im WHERE im.user_id=\"{}\" AND im.enumeration={}'.format(user_id, template_number)
        result = mysql_select(db_cursor, query)
        if not result:
            return result
        filename = result.returnValue[0]
    else:
        filename = os.path.basename(filename)
    ret = ReturnInfo(returnCode=0, Messages={
        1: 'File \"{}\" not found'.format(filename)
    })
    query = 'DELETE FROM images AS im WHERE im.user_id=\"{}\" AND im.enumeration={}'.format(user_id, template_number)
    result = execute_query(db_handle, db_cursor, query)
    if not result:
        return result
    try:
        remove_file(os.path.join(absolute_path_to_project, 'Images', filename))
    except FileNotFoundError:
        ret.returnCode = 1
    return ret

# Sets up commands that require context earlier
def set_up_functions() -> None:
    command_guilds = []
    if get_setting(settings, 'testing', bool) and get_setting(settings, 'home_guild_id', bool):
        command_guilds.append(discord.Object(id=settings['home_guild_id']))
    # Command to turn off bot, should only be in a home guild
    if get_setting(settings, 'home_guild_id', bool):
        try:
            global turn_off_bot_command
            @command_tree.command(
                name='off',
                description=get_description(descriptions, 'turn_off_command'),
                guild=discord.Object(id=settings['home_guild_id'])
            )
            async def turn_off_bot_command(context: discord.Interaction) -> None:
                await context.response.send_message('Turning off bot...')
                await client.close()
        except discord.app_commands.CommandAlreadyRegistered:
            pass
    else:
        log_output('Unable to set up off command', level=logging.ERROR)
    # Command to create a template
    global create_template_command
    try:
        @command_tree.command(
            name='create_template',
            description=get_description(descriptions, 'create_template_command'),
            guilds=command_guilds
        )
        @command_describe(
            template=get_description(descriptions, 'template_option'),
            template_number=get_description(descriptions, 'template_number_option')
        )
        async def create_template_command(context: discord.Interaction, template: discord.Attachment, template_number: int) -> None:
            if template_number < 1 or template_number > 3:
                await context.response.send_message('Incorrect template number. Should be between 1 and 3')
            if type(template.content_type) != str or not template.content_type.startswith('image/'):
                await context.response.send_message('Unable to read attachment as image', ephemeral=True)
                return
            query = 'SELECT CONCAT(im.user_id, "_", im.enumeration, ".", im.image_extension) FROM images AS im WHERE im.user_id=\"{}\" AND im.enumeration={}'.format(context.user.id, template_number)
            result = mysql_select(db_cursor, query)
            result.okCodes.append(1)
            empty_query = result.returnCode == 1
            if not result:
                log_output('Error while processing a mysql query: \n\t{}\n{}'.format(query, result), logging.ERROR)
                await context.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
                return
            if empty_query:
                result = await register_template(context.user.id, template_number, template)
                if result:
                    await context.response.send_message('Template successfully registered', ephemeral=True)
                else:
                    log_output('Error: Failed to register a template. user_id={} template_number={}\n{}'.format(context.user.id, template_number, result))
                    await context.response.send_message('Sorry, something went wrong. Template not registered', ephemeral=True)
            else:
                filename = result.returnValue[0]
                embed = discord.Embed(
                    title = 'Template already exists',
                    description = 'Template with existing number already exists for user {}\nWould you like to replace that template with a new one? (This will delete all fields attached to it)'.format(context.user.display_name),
                    color = discord.Color.orange()
                )
                embed.set_image(url='attachment://{}'.format(filename))
                attachment = discord.File(os.path.join(absolute_path_to_project, 'Images', filename), filename=filename)
                replace_button = discord.ui.Button(label='Replace', style=discord.ButtonStyle.primary, emoji='✅')
                cancel_button = discord.ui.Button(label='Cancel', style=discord.ButtonStyle.secondary, emoji='❌')
                async def replace_action(interaction: discord.Interaction):
                    if interaction.user != context.user:
                        await interaction.response.send_message('This command was not run by you and you cannot respond to it', ephemeral=True)
                        return
                    result = delete_template(context.user.id, template_number, filename)
                    if not result:
                        log_output('Error trying to delete from table images. user_id={}, template_number={}\n{}'.format(context.user.id, template_number, result))
                        asyncio.gather(
                            interaction.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True),
                            interaction.message.delete()
                        )
                        return
                    result = await register_template(context.user.id, template_number, template)
                    if not result:
                        log_output('Error: Failed to register a template. user_id={} template_number={}\n{}'.format(context.user.id, template_number, result))
                        asyncio.gather(
                            interaction.message.delete(),
                            interaction.response.send_message('Template successfully deleted but there has been problem with registering a new one. Try again in a moment', ephemeral=True)
                        )
                        return
                    asyncio.gather(
                        interaction.message.delete(),
                        interaction.response.send_message('Old template has been deleted and a new one has been successfully created', ephemeral=True)
                    )
                async def cancel_action(interaction: discord.Interaction):
                    if interaction.user != context.user:
                        await interaction.response.send_message('This command was not run by you and you cannot respond to it', ephemeral=True)
                        return
                    await interaction.message.delete()
                replace_button.callback = replace_action
                cancel_button.callback = cancel_action
                buttons = discord.ui.View()
                buttons.add_item(replace_button)
                buttons.add_item(cancel_button)
                await context.response.send_message(embed=embed, view=buttons, file=attachment)
    except discord.app_commands.CommandAlreadyRegistered:
        pass

# Called when bot connects to discord
@client.event
async def on_ready() -> None:
    log_output(f'Logged in as {client.user.name}')
    log_output(client.user.id)
    set_up_functions()
    if '--global-sync' in sys.argv or ('--sync' in sys.argv and not get_setting(settings, 'testing', bool)):
        await command_tree.sync()
        log_output('synced slash commands globally')
    if '--sync' in sys.argv and get_setting(settings, 'testing', bool) and get_setting(settings, 'home_guild_id', bool):
        await command_tree.sync(guild=discord.Object(id=settings['home_guild_id']))
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
    global settings
    global descriptions
    global db_handle
    global db_cursor
    result = load_settings(required_keys=main_required_settings + db_required_settings)
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

    result = connect_database(settings['db_username'], settings['db_password'], settings['database_name'])
    if not result:
        log_output(result, level=logging.CRITICAL)
        return
    db_handle, db_cursor = result.returnValue

    result = load_descriptions(db_cursor)
    if not result:
        log_output(result, level=logging.ERROR)
        log_output('Unable to access descriptions. Descriptions might be missing', level=logging.ERROR)
    descriptions = result.returnValue

    try:
        client.run(settings['app_token'])
    except discord.errors.LoginFailure:
        log_output('There was a problem with logging in. Check your app token in the settings file', level=logging.CRITICAL)
        return

if __name__ == '__main__':
    main()
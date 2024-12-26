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
from cv2 import imread, imwrite

from constants import discord_intents, date_format, main_required_settings, db_required_settings, absolute_path_to_project, embed_default_color, temporary_file_timer, default_color_hex, default_hue_range, default_saturation_range, default_value_range
from functions.utils import load_settings, get_setting, load_descriptions, get_description, generate_temp_hash
from functions.database_functions import connect_database, select as mysql_select, execute_query
from Models.ReturnInfo import ReturnInfo
from functions.image_functions import show_fields, find_biggest_rectangle, hex_to_bgr

settings = {}
descriptions = {}
client = discord.Client(intents=discord_intents)
command_tree = discord.app_commands.CommandTree(client)
to_delete = []

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

async def followup_and_delete(context: discord.Interaction, message: str, delay: int = 10) -> None:
    await context.followup.send(message)
    asyncio.get_event_loop().call_later(delay, asyncio.create_task, context.delete_original_response())

def delete_image(filename: str) -> None:
    global to_delete
    os.remove(os.path.join(absolute_path_to_project, 'Images', filename))
    if filename in to_delete:
        to_delete.remove(filename)
    log_output('Deleted image \"{}\"'.format(filename))

async def get_template_with_fields(filename: str, field_coords: list[tuple[int, int, int, int]], field_names: list[str], color: tuple[int, int, int]) -> ReturnInfo:
    global to_delete
    ret = ReturnInfo(returnCode=0, Messages={})
    original_image = imread(os.path.join(absolute_path_to_project, 'Images', filename))
    result = show_fields(original_image, field_coords, field_names, color, 2)
    if not result:
        return result
    temp_filename = generate_temp_hash() + '.' + filename.split('.')[-1]
    imwrite(os.path.join(absolute_path_to_project, 'Images', temp_filename), result.returnValue)
    ret.returnValue = temp_filename
    to_delete.append(temp_filename)
    asyncio.get_event_loop().call_later(temporary_file_timer, delete_image, temp_filename)
    log_output('Created image \"{}\"'.format(temp_filename))
    return ret

async def turn_off_command_prototype(context: discord.Interaction) -> None:
    await context.response.send_message('Turning off bot...')
    await client.close()

async def create_template_command_prototype(context: discord.Interaction, template: discord.Attachment, template_number: int) -> None:
    if template_number < 1 or template_number > 3:
        await context.response.send_message('Incorrect template number. Should be between 1 and 3')
    if type(template.content_type) != str or not template.content_type.startswith('image/'):
        await context.response.send_message('Unable to read attachment as image', ephemeral=True)
        return
    query = 'SELECT filename FROM images AS im WHERE im.user_id=\"{}\" AND im.enumeration={}'.format(context.user.id, template_number)
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
            color = embed_default_color
        )
        embed.set_image(url='attachment://{}'.format(filename))
        attachment = discord.File(os.path.join(absolute_path_to_project, 'Images', filename), filename=filename)
        replace_button = discord.ui.Button(label='Replace', style=discord.ButtonStyle.primary, emoji='✅')
        cancel_button = discord.ui.Button(label='Cancel', style=discord.ButtonStyle.secondary, emoji='❌')
        async def replace_action(interaction: discord.Interaction) -> None:
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
        async def cancel_action(interaction: discord.Interaction) -> None:
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

async def view_command_prototype(context: discord.Interaction, template_number: int = 0, show_fields: bool = False) -> None:
    await context.response.defer(ephemeral=True, thinking=True)
    if template_number == 0:
        return await view_all_templates(context)
    return await view_one_template(context, template_number, show_fields)

async def view_all_templates(context: discord.Interaction) -> None:
    embed = discord.Embed(
        title = '{}\'s templates'.format(context.user.display_name),
        color = embed_default_color
    )
    query = 'SELECT image_extension, created_at, enumeration FROM images WHERE user_id=\"{}\"'.format(context.user.id)
    result = mysql_select(db_cursor, query, True, True)
    if not result:
        log_output('Error while processing a mysql query: \n\t{}\n{}'.format(query, result), logging.ERROR)
        await context.followup.send('Sorry, something went wrong. Try again later', ephemeral=True)
        return
    entries = result.returnValue
    templates = ['No registered template'] * 3
    for entry in entries:
        templates[entry[2] - 1] = '{} image. Created at: {}'.format(entry[0], entry[1])
    desc = ''
    for i in range(len(templates)):
        desc += str(i + 1) + ': ' + templates[i] + '\n'
    desc += 'To view a chosen template use /view number_of_template'
    embed.description = desc
    await context.followup.send(embed=embed, ephemeral=True)

async def view_one_template(context: discord.Interaction, template_number: int, show_fields: bool) -> None:
    embed = discord.Embed(
        title='{}\'s template no. {}'.format(context.user.display_name, template_number),
        color = embed_default_color
    )
    query = 'SELECT filename, image_extension, created_at, id FROM images WHERE user_id=\"{}\" AND enumeration={}'.format(context.user.id, template_number)
    result = mysql_select(db_cursor, query)
    if not result:
        if result.returnCode == 1:
            await context.followup.send('Sorry, looks like you don\'t have a template with a given number. Try using the command with no template_number to show you all the templates you have registered', ephemeral=True)
            return
        else:
            log_output('Error while processing a mysql query: \n\t{}\n{}'.format(query, result), logging.ERROR)
            await context.followup.send('Sorry, something went wrong. Try again later', ephemeral=True)
            return
    filename = result.returnValue[0]
    if show_fields:
        query = 'SELECT field_name, type, up_bound, left_bound, down_bound, right_bound FROM editable_fields WHERE image_id={}'.format(result.returnValue[3])
        result = mysql_select(db_cursor, query, True, True)
        if not result:
            log_output('Error while processing a mysql query: \n\t{}\n{}'.format(query, result), logging.ERROR)
            await context.followup.send('Sorry, something went wrong. Try again later', ephemeral=True)
            return
        desc = ''
        counter = 0
        field_coords = []
        field_names = []
        for field in result.returnValue:
            counter += 1
            desc += str(counter) + ': ' + field[0] + '(' + field[1] + ')\n'
            field_coords.append((field[2], field[3], field[4], field[5]))
            field_names.append(field[0])
        if desc:
            # delete the last newline
            desc = desc[:-1]
        else:
            desc = 'No registered fields'
        embed.description = desc
        result = hex_to_bgr(default_color_hex)
        bgr_color = result.returnValue
        result = await get_template_with_fields(filename, field_coords, field_names, bgr_color)
        if not result:
            log_output('Error while generating a template with fields for file: {}'.format(filename), logging.ERROR)
            await context.followup.send('Sorry, something went wrong. Try again later', ephemeral=True)
            return
        filename = result.returnValue
    else:
        embed.description = '{} file\n Created at: {}\nTo show registered fields, use this command with show_fields=true'.format(result.returnValue[1], result.returnValue[2])
    filepath = os.path.join(absolute_path_to_project, 'Images', filename)
    embed.set_image(url='attachment://{}'.format(filename))
    attachment = discord.File(filepath, filename=filename)
    await context.followup.send(embed=embed, file=attachment, ephemeral=True)

async def add_field_command_prototype(context: discord.Interaction, field_type: discord.app_commands.Choice[str], name: str, template_number: int, up_bound: int | None = None, left_bound: int | None = None, down_bound: int | None = None, right_bound: int | None = None, reference_image: discord.Attachment | None = None, color: str = default_color_hex) -> None:
    await context.response.defer(thinking=True)
    bounds = (up_bound, left_bound, down_bound, right_bound)
    use_bounds = not any([b is None for b in bounds])
    use_image = not reference_image is None
    if not (use_bounds or use_image):
        await followup_and_delete(context, 'Please specify either all bounds for the field or send a reference image')
        return
    if use_bounds:
        use_image = False
    query = 'SELECT id, filename FROM images WHERE user_id=\"{}\" AND enumeration={}'.format(context.user.id, template_number)
    result = mysql_select(db_cursor, query)
    if not result:
        if result.returnCode == 1:
            await followup_and_delete(context, 'No template with a give number for user {} exists. Please create a template with /create_template command'.format(context.user.display_name))
            return
        log_output('Error while processing a mysql query: \n\t{}\n{}'.format(query, result), logging.ERROR)
        await followup_and_delete(context, 'Sorry, something went wrong. Try again later')
        return
    template_id, filename = result.returnValue
    filepath = os.path.join(absolute_path_to_project, 'Images', filename)
    result = hex_to_bgr(color)
    if not result:
        await followup_and_delete(context, result)
        return
    bgr_color = result.returnValue
    if use_image:
        template_image = imread(filepath)
        result = find_biggest_rectangle(template_image, bgr_color, default_hue_range, default_saturation_range, default_value_range)
        if not result:
            await followup_and_delete(context, 'Unable to find a specified color ({}) in a chosen template'.format(color))
            return
        bounds = result.returnValue
    result = await get_template_with_fields(filename, [bounds], [name], bgr_color)
    if not result:
        log_output('Error while trying to create a template with fields: {}'.format(result), logging.ERROR)
        await followup_and_delete(context, 'Sorry, something went wrong. Try again later')
        return
    filename = result.returnValue
    filepath = os.path.join(absolute_path_to_project, 'Images', filename)
    attachment = discord.File(filepath, filename=filename)
    embed = discord.Embed(
        title = 'Adding field',
        color = embed_default_color,
        description = 'Here\'s a preview of a new field. To confirm click on a corresponding button'
    )
    embed.set_image(url='attachment://{}'.format(filename))
    confirm_button = discord.ui.Button(label='Confirm', style=discord.ButtonStyle.primary, emoji='✅')
    cancel_button = discord.ui.Button(label='Cancel', style=discord.ButtonStyle.primary, emoji='❌')
    async def confirm_action(interaction: discord.Interaction) -> None:
        if interaction.user != context.user:
            await interaction.response.send_message('This command was not run by you and you cannot respond to it', ephemeral=True)
            return
        query = 'INSERT INTO editable_fields (field_name, type, up_bound, left_bound, down_bound, right_bound, image_id) VALUES (\"{}\", \"{}\", {}, {}, {}, {}, {})'.format(name, field_type.value, bounds[0], bounds[1], bounds[2], bounds[3], template_id)
        result = execute_query(db_handle, db_cursor, query)
        if not result:
            log_output('Error while processing a mysql query: \n\t{}\n{}'.format(query, result), logging.ERROR)
            await interaction.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
            return
        asyncio.gather(
            interaction.message.delete(),
            interaction.response.send_message('Field successfully added', ephemeral=True)
        )
    async def cancel_action(interaction: discord.Interaction) -> None:
        if interaction.user != context.user:
            await interaction.response.send_message('This command was not run by you and you cannot respond to it', ephemeral=True)
            return
        await interaction.message.delete()
    confirm_button.callback = confirm_action
    cancel_button.callback = cancel_action
    buttons = discord.ui.View()
    buttons.add_item(confirm_button)
    buttons.add_item(cancel_button)
    await context.followup.send(embed=embed, view=buttons, file=attachment)

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
            description=get_description(descriptions, 'create_template_command'),
            guilds=command_guilds
        )
        @command_describe(
            template=get_description(descriptions, 'template_option'),
            template_number=get_description(descriptions, 'template_number_option')
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
            description=get_description(descriptions, 'view_command'),
            guilds=command_guilds
        )
        @command_describe(
            template_number=get_description(descriptions, 'template_number_option'),
            show_fields=get_description(descriptions, 'show_fields_option')
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
            description=get_description(descriptions, 'add_field'),
            guilds=command_guilds
        )
        @command_describe(
            field_type=get_description(descriptions, 'field_type_option'),
            name=get_description(descriptions, 'name_option'),
            template_number=get_description(descriptions, 'template_number_option'),
            up_bound=get_description(descriptions, 'top_bound_option'),
            left_bound=get_description(descriptions, 'left_bound_option'),
            down_bound=get_description(descriptions, 'down_bound_option'),
            right_bound=get_description(descriptions, 'right_bound_option'),
            reference_image=get_description(descriptions, 'reference_image_option'),
        )
        @discord.app_commands.choices(field_type=[
            discord.app_commands.Choice(name='Text', value='text'),
            discord.app_commands.Choice(name='Image', value='image')
        ])
        async def add_field_command(context: discord.Interaction, field_type: discord.app_commands.Choice[str], name: str, template_number: discord.app_commands.Range[int, 1, 3], up_bound: int | None = None, left_bound: int | None = None, down_bound: int | None = None, right_bound: int | None = None, reference_image: discord.Attachment | None = None, color: str = default_color_hex) -> None:
            return await add_field_command_prototype(context, field_type, name, template_number, up_bound, left_bound, down_bound, right_bound, reference_image, color)
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
    for filename in to_delete.copy():
        delete_image(filename)
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
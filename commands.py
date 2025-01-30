"""
    File with all the commands that are meant to be registered as bot commands
"""

import discord
import logging
import asyncio
from mysql.connector import MySQLConnection
from mysql.connector.cursor import MySQLCursor
from os import path, remove as remove_file
from io import BytesIO
from cv2 import imread, imencode, imdecode, IMREAD_COLOR, LINE_8, FONT_HERSHEY_SIMPLEX
from numpy import asarray, uint8, copy as np_copy

from constants import absolute_path_to_project, embed_default_color, default_color_hex, default_hue_range, default_saturation_range, default_value_range
from functions.database_functions import select as mysql_select, execute_query
from functions.image_functions import hex_to_bgr, show_fields as show_fields_image, find_biggest_rectangle, insert_image_into_image, write_on_image
from functions.ReturnInfo import ReturnInfo

needed_data = ['client', 'db_cursor', 'db_handle', 'logging_ref']

using_template = {}

possible_fonts = {
    'Simple': FONT_HERSHEY_SIMPLEX
}

async def error_with_mysql_query(context: discord.Interaction, query: str, error_message: str, use_followup: bool = False):
    log_output('Error while processing a mysql query: \n\t{}\n{}'.format(query, error_message), logging.ERROR)
    method = context.followup.send if use_followup else context.response.send_message
    await method('Sorry, something went wrong. Try again later', ephemeral=True)

def setup_commands(data: dict[str, any]) -> bool:
    global client, db_cursor, db_handle, log_output
    for key in needed_data:
        if key not in data.keys():
            return False
    client = data['client']
    db_cursor = data['db_cursor']
    db_handle = data['db_handle']
    log_output = data['logging_ref']
    return True

def reconnect_database(database_connection: MySQLConnection, database_cursor: MySQLCursor):
    global db_handle, db_cursor
    db_handle, db_cursor = database_connection, database_cursor

async def followup_and_delete(context: discord.Interaction, message: str, delay: int = 10):
    await context.followup.send(message)
    asyncio.get_running_loop().call_later(delay, asyncio.create_task, context.delete_original_response())

async def register_template(user_id: int | str, template_number: int, file: discord.Attachment) -> ReturnInfo:
    ret = ReturnInfo(Messages={
        1: "Saving image failed"
    })
    assert not file.content_type is None and file.content_type.startswith('image/')
    extension = file.content_type[(len('image/')):]
    filename = str(user_id) + '_' + str(template_number) + '.' + extension
    try:
        await file.save(path.join(absolute_path_to_project, 'Images', filename))
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
        filename = path.basename(filename)
    ret = ReturnInfo(Messages={
        1: 'File \"{}\" not found'.format(filename)
    })
    query = 'DELETE FROM images AS im WHERE im.user_id=\"{}\" AND im.enumeration={}'.format(user_id, template_number)
    result = execute_query(db_handle, db_cursor, query)
    if not result:
        return result
    try:
        remove_file(path.join(absolute_path_to_project, 'Images', filename))
    except FileNotFoundError:
        ret.returnCode = 1
    return ret

async def turn_off_command_prototype(context: discord.Interaction):
    await context.response.send_message('Turning off bot...')
    await client.close()

async def create_template_command_prototype(context: discord.Interaction, template: discord.Attachment, template_number: int):
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
        await error_with_mysql_query(context, query, str(result))
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
        attachment = discord.File(path.join(absolute_path_to_project, 'Images', filename), filename=filename)
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

async def view_command_prototype(context: discord.Interaction, template_number: int = 0, show_fields: bool = False):
    await context.response.defer(ephemeral=True, thinking=True)
    if template_number == 0:
        return await view_all_templates(context)
    return await view_one_template(context, template_number, show_fields)

async def view_all_templates(context: discord.Interaction):
    embed = discord.Embed(
        title = '{}\'s templates'.format(context.user.display_name),
        color = embed_default_color
    )
    query = 'SELECT image_extension, created_at, enumeration FROM images WHERE user_id=\"{}\"'.format(context.user.id)
    result = mysql_select(db_cursor, query, True, True)
    if not result:
        await error_with_mysql_query(context, query, str(result), True)
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

async def view_one_template(context: discord.Interaction, template_number: int, show_fields: bool):
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
            await error_with_mysql_query(context, query, str(result), True)
            return
    filename = result.returnValue[0]
    if show_fields:
        query = 'SELECT field_name, type, up_bound, left_bound, down_bound, right_bound FROM editable_fields WHERE image_id={}'.format(result.returnValue[3])
        result = mysql_select(db_cursor, query, True, True)
        if not result:
            await error_with_mysql_query(context, query, str(result), True)
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
        original_image = imread(path.join(absolute_path_to_project, 'Images', filename))
        result = show_fields_image(original_image, field_coords, field_names, bgr_color)
        if not result:
            log_output('Error while generating a template with fields for file: {}'.format(filename), logging.ERROR)
            await context.followup.send('Sorry, something went wrong. Try again later')
            return
        fields_image = result.returnValue
        success, buff = imencode('.' + filename.split('.')[-1], fields_image)
        if not success:
            log_output('Error while converting file \"{}\" with fields to bytes'.format(filename), logging.ERROR)
            await context.followup.send('Sorry, something went wrong. Try again later')
            return
        filepath = BytesIO(buff.tobytes())
    else:
        embed.description = '{} file\n Created at: {}\nTo show registered fields, use this command with show_fields=true'.format(result.returnValue[1], result.returnValue[2])
        filepath = path.join(absolute_path_to_project, 'Images', filename)
    embed.set_image(url='attachment://{}'.format(filename))
    attachment = discord.File(filepath, filename=filename)
    await context.followup.send(embed=embed, file=attachment)

async def add_field_command_prototype(context: discord.Interaction, field_type: discord.app_commands.Choice[str], name: str, template_number: int, up_bound: int | None = None, left_bound: int | None = None, down_bound: int | None = None, right_bound: int | None = None, reference_image: discord.Attachment | None = None, color: str = default_color_hex):
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
            await followup_and_delete(context, 'No template with a given number for user {} exists. Please create a template with /create_template command'.format(context.user.display_name))
            return
        await error_with_mysql_query(context, query, str(result), True)
        return
    template_id, filename = result.returnValue
    filepath = path.join(absolute_path_to_project, 'Images', filename)
    query = f'SELECT 1 FROM editable_fields WHERE field_name=\"{name}\" AND image_id={template_id}'
    result = mysql_select(db_cursor, query)
    result.okCodes.append(1)
    if result.returnCode == 0:
        await followup_and_delete(context, 'A field with that name already exists for this template')
        return
    if not result:
        await error_with_mysql_query(context, query, str(result), True)
        return
    result = hex_to_bgr(color)
    if not result:
        await followup_and_delete(context, result)
        return
    bgr_color = result.returnValue
    if use_image:
        reference_bytes = asarray(bytearray(await reference_image.read()), dtype=uint8)
        template_image = imdecode(reference_bytes, IMREAD_COLOR)
        result = find_biggest_rectangle(template_image, bgr_color, default_hue_range, default_saturation_range, default_value_range)
        if not result:
            await followup_and_delete(context, 'Unable to find a specified color ({}) in a chosen template'.format(color))
            return
        bounds = result.returnValue
    original_image = imread(path.join(absolute_path_to_project, 'Images', filename))
    result = show_fields_image(original_image, [bounds], [name], bgr_color)
    if not result:
        log_output('Error while trying to create a template with fields: {}'.format(result), logging.ERROR)
        await followup_and_delete(context, 'Sorry, something went wrong. Try again later')
        return
    fields_image = result.returnValue
    success, buffer = imencode('.' + filename.split('.')[-1], fields_image)
    if not success:
        log_output('Error while converting file \"{}\" with fields to bytes'.format(filename), logging.ERROR)
        await context.followup.send('Sorry, something went wrong. Try again later')
        return
    filepath = BytesIO(buffer.tobytes())
    attachment = discord.File(filepath, filename=filename)
    embed = discord.Embed(
        title = 'Adding field',
        color = embed_default_color,
        description = 'Here\'s a preview of a new field. To confirm click on a corresponding button'
    )
    embed.set_image(url='attachment://{}'.format(filename))
    confirm_button = discord.ui.Button(label='Confirm', style=discord.ButtonStyle.primary, emoji='✅')
    cancel_button = discord.ui.Button(label='Cancel', style=discord.ButtonStyle.primary, emoji='❌')
    async def confirm_action(interaction: discord.Interaction):
        if interaction.user != context.user:
            await interaction.response.send_message('This command was not run by you and you cannot respond to it', ephemeral=True)
            return
        query = 'INSERT INTO editable_fields (field_name, type, up_bound, left_bound, down_bound, right_bound, image_id) VALUES (\"{}\", \"{}\", {}, {}, {}, {}, {})'.format(name, field_type.value, bounds[0], bounds[1], bounds[2], bounds[3], template_id)
        result = execute_query(db_handle, db_cursor, query)
        if not result:
            await error_with_mysql_query(context, query, str(result), True)
            return
        asyncio.gather(
            interaction.message.delete(),
            interaction.response.send_message('Field successfully added', ephemeral=True)
        )
    async def cancel_action(interaction: discord.Interaction):
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

async def remove_field_command_prototype(context: discord.Interaction, template_number: int, field_name: str):
    query = 'SELECT f.id FROM editable_fields AS f JOIN images AS i WHERE i.enumeration={} AND i.user_id=\"{}\" AND LOWER(f.field_name)=\"{}\"'.format(template_number, context.user.id, field_name.lower())
    result = mysql_select(db_cursor, query)
    if result.returnCode == 1:
        await context.response.send_message('No field with name \"{}\" found for template number {}\nUse /view to check your templates and fields'.format(field_name, template_number), ephemeral=True)
        return
    if not result:
        await error_with_mysql_query(context, query, str(result))
        return
    query = 'DELETE FROM editable_fields WHERE id={}'.format(result.returnValue[0])
    result = execute_query(db_handle, db_cursor, query)
    if not result:
        await error_with_mysql_query(context, query, str(result))
        return
    await context.response.send_message('Field \"{}\" successfully removed'.format(field_name), ephemeral=True)

async def delete_from_template_dict(user_id: int):
    global using_template
    data = using_template.pop(user_id, None)
    if data is None:
        return
    # interaction = data['interaction']
    message = (await client.fetch_channel(data['channel_id'])).get_partial_message(data['message_id'])
    embed = discord.Embed(
        color=embed_default_color,
        title='Out of time!',
        description='An hour has passed and because the template usage was not completed, this interaction has expired'
    )
    button = discord.ui.Button(label='Delete this', style=discord.ButtonStyle.red, emoji='🗑️')
    async def button_click(button_interaction: discord.Interaction):
        if button_interaction.user.id != user_id:
            await button_interaction.response.send_message('This command was not run by you so you cannot delete this message', ephemeral=True)
            return
        await button_interaction.message.delete()
    button.callback = button_click
    view = discord.ui.View(timeout=None)
    view.add_item(button)
    await message.edit(embed=embed, view=view, attachments=[])

def using_template_check(context: discord.Interaction) -> bool:
    return context.user.id in using_template.keys()

async def use_template_command_prototype(context: discord.Interaction, template_number: int):
    global using_template
    if context.user.id in using_template.keys():
        embed = discord.Embed(
            title='Template is already being used',
            description='A template is already being used. Would you like to abandon the old template and use this one?',
            color=embed_default_color
        )
        new_button = discord.ui.Button(label='Use a new one', style=discord.ButtonStyle.primary, emoji='✅')
        cancel_button = discord.ui.Button(label='Cancel', style=discord.ButtonStyle.secondary, emoji='❌')
        async def new_button_action(button_interaction: discord.Interaction):
            if button_interaction.user != context.user:
                await button_interaction.response.send_message('This command was not run by you so you cannot interact with it', ephemeral=True)
                return
            if context.user.id not in using_template.keys():
                return
            message = (await client.fetch_channel(using_template[context.user.id]['channel_id'])).get_partial_message(using_template[context.user.id]['message_id'])
            asyncio.gather(
                use_template_command_prototype(button_interaction, template_number),
                button_interaction.message.delete(),
                message.delete()
            )
            del using_template[context.user.id]
        async def cancel_button_action(button_interaction: discord.Interaction):
            if button_interaction.user != context.user:
                await button_interaction.response.send_message('This command was not run by you so you cannot interact with it', ephemeral=True)
                return
            await context.delete_original_response()
        new_button.callback = new_button_action
        cancel_button.callback = cancel_button_action
        buttons = discord.ui.View()
        buttons.add_item(new_button)
        buttons.add_item(cancel_button)
        await context.response.send_message(embed=embed, view=buttons)
        return
    query = 'SELECT id, filename FROM images WHERE user_id=\"{}\" AND enumeration={}'.format(context.user.id, template_number)
    result = mysql_select(db_cursor, query)
    if result.returnCode == 1:
        await context.response.send_message('No template found with a given number. Use /add_template to add your template and use /view to see what templates you have', ephemeral=True)
        return
    if not result:
        await error_with_mysql_query(context, query, str(result))
        return
    template_id, filename = result.returnValue
    filepath = path.join(absolute_path_to_project, 'Images', filename)
    image = imread(filepath)
    data = {'template_id': template_id, 'filename': filename, 'image': image, 'channel_id': context.channel_id}
    fields = {}
    query = 'SELECT LOWER(field_name), type, up_bound, left_bound, down_bound, right_bound FROM editable_fields WHERE image_id={}'.format(template_id)
    result = mysql_select(db_cursor, query, True, True)
    if not result:
        await error_with_mysql_query(context, query, str(result))
        return
    for field_data in result.returnValue:
        fields[field_data[0]] = {'type': field_data[1], 'bounds': tuple(field_data[2:]), 'value': None, 'updated': False}
    data['fields'] = fields
    using_template[context.user.id] = data
    asyncio.get_running_loop().call_later(60 * 60, asyncio.create_task, delete_from_template_dict(context.user.id))
    embed = discord.Embed(
        title='Using template',
        description='Template is being used. Use /fill_text_field or /fill_image_field to fill a field of a chosen type for the chosen template\nA template will no long be available to fill in an hour from now on. Make sure to finish using it by then',
        color=embed_default_color
    )
    embed.set_image(url='attachment://{}'.format(filename))
    finish_button = discord.ui.Button(label='Finish', style=discord.ButtonStyle.primary, emoji='✅')
    update_view_button = discord.ui.Button(label='Update', style=discord.ButtonStyle.secondary, emoji='🔄')
    cancel_button = discord.ui.Button(label='Cancel', style=discord.ButtonStyle.red, emoji='🗑️')
    async def update_image() -> ReturnInfo:
        global using_template
        ret = ReturnInfo(okCodes=[0, 1], returnValue='Done', Messages={
            1: 'Template shown is up-to-date',
            2: 'Error while trying to insert image',
            3: 'Error while trying to write on image'
        })
        image_fields = [field_name for field_name, field in using_template[context.user.id]['fields'].items() if not field['value'] is None and not field['updated'] and field['type'] == 'image']
        text_fields = [field_name for field_name, field in using_template[context.user.id]['fields'].items() if not field['value'] is None and not field['updated'] and field['type'] == 'text']
        if len(image_fields) + len(text_fields) == 0:
            ret.returnCode = 1
            return ret
        for field_name in image_fields:
            field = using_template[context.user.id]['fields'][field_name]
            result = insert_image_into_image(using_template[context.user.id]['image'], field['value'], field['bounds'])
            if not result:
                ret.returnCode = 2
                ret.returnValue = result
                return ret
            new_image = result.returnValue
            using_template[context.user.id]['image'] = new_image
            using_template[context.user.id]['fields'][field_name]['updated'] = True
        for field_name in text_fields:
            field = using_template[context.user.id]['fields'][field_name]
            text, font, font_scale, color = field['value']
            result = write_on_image(using_template[context.user.id]['image'], text, font, font_scale, color, 2, LINE_8, field['bounds'])
            if not result:
                ret.returnCode = 3
                ret.returnValue = result
                return ret
            if result.returnCode == 1:
                ret.returnValue += '\n' + field_name + ': ' + str(result)
            new_image = result.returnValue
            using_template[context.user.id]['image'] = new_image
            using_template[context.user.id]['fields'][field_name]['updated'] = True
        return ret
    async def finish_action(button_interaction: discord.Interaction):
        global using_template
        if context.user != button_interaction.user:
            await button_interaction.response.send_message('This command was not run by you so you cannot interact with it', ephemeral=True)
            return
        if context.user.id not in using_template.keys():
            asyncio.gather(
                button_interaction.message.delete(),
                button_interaction.response.send_message('The time has run out and the message has been deleted', ephemeral=True)
            )
            return
        if not context.user.id in using_template.keys():
            await button_interaction.response.send_message('Something went wrong. Try using a template again', ephemeral=True)
            return
        result = await update_image()
        if not result:
            await button_interaction.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
            log_output('{}\ttemplate_number={}\t{}user_id={}\n{}'.format(result, template_id, context.user.id, result.returnValue))
            return
        filename = using_template[context.user.id]['filename']
        success, buffor = imencode('.' + filename.split('.')[-1], using_template[context.user.id]['image'])
        if not success:
            log_output('Error while converting file \"{}\" to bytes'.format(filename), logging.ERROR)
            await button_interaction.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
            return
        file = discord.File(BytesIO(buffor.tobytes()), filename=filename)
        message = 'Image created from a template'
        del using_template[context.user.id]
        asyncio.gather(
            button_interaction.response.send_message(message, file=file),
            button_interaction.message.delete()
        )
    async def cancel_action(button_interaction: discord.Interaction):
        global using_template
        if context.user != button_interaction.user:
            await button_interaction.response.send_message('This command was not run by you so you cannot interact with it', ephemeral=True)
            return
        using_template.pop(context.user.id, None)
        await button_interaction.message.delete()
    async def update_view(button_interaction: discord.Interaction):
        if context.user != button_interaction.user:
            await button_interaction.response.send_message('This command was not run by you so you cannot interact with it', ephemeral=True)
            return
        if context.user.id not in using_template.keys():
            asyncio.gather(
                button_interaction.message.delete(),
                button_interaction.response.send_message('The time has run out and the message has been deleted', ephemeral=True)
            )
            return
        result = await update_image()
        if not result:
            await button_interaction.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
            log_output('{}\ttemplate_number={}\t{}user_id={}\n{}'.format(result, template_id, context.user.id, result.returnValue))
            return
        if result.returnCode == 1:
            await button_interaction.response.send_message(str(result), ephemeral=True)
            return
        message = result.returnValue
        empty_fields_temp = [(field_name, field['bounds']) for field_name, field in using_template[context.user.id]['fields'].items() if field['value'] is None]
        empty_field_names = [item[0] for item in empty_fields_temp]
        empty_field_bounds = [item[1] for item in empty_fields_temp]
        image = np_copy(using_template[context.user.id]['image'])
        result = show_fields_image(image, empty_field_bounds, empty_field_names)
        if not result:
            await button_interaction.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
            log_output('Error while generating fields for image\n{}'.format(result), logging.ERROR)
            return
        image = result.returnValue
        filename = using_template[context.user.id]['filename']
        new_embed = embed.copy()
        new_embed.set_image(url='attachment://{}'.format(filename))
        success, buffer = imencode('.' + filename.split('.')[-1], image)
        if not success:
            log_output('Error while converting file \"{}\" to bytes'.format(filename), logging.ERROR)
            await button_interaction.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
            return
        new_file = discord.File(BytesIO(buffer.tobytes()), filename=filename)
        await button_interaction.response.edit_message(embed=embed, attachments=[new_file])
        await button_interaction.followup.send(message, ephemeral=True)
    finish_button.callback = finish_action
    update_view_button.callback = update_view
    cancel_button.callback = cancel_action
    buttons = discord.ui.View(timeout=60 * 60)
    # buttons = discord.ui.View(timeout=None)
    buttons.add_item(finish_button)
    buttons.add_item(update_view_button)
    buttons.add_item(cancel_button)
    image = np_copy(using_template[context.user.id]['image'])
    field_temp = [(field_name, field['bounds']) for field_name, field in fields.items()]
    field_names = [item[0] for item in field_temp]
    field_bounds = [item[1] for item in field_temp]
    result = show_fields_image(image, field_bounds, field_names)
    if not result:
        await context.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
        log_output('Error while generating fields for image\n{}'.format(result), logging.ERROR)
        return
    image = result.returnValue
    success, buffer = imencode('.' + filename.split('.')[-1], image)
    if not success:
        await context.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
        log_output('Error while converting image \"{}\"to bytes'.format(filename), logging.ERROR)
        return
    attachment = discord.File(BytesIO(buffer.tobytes()), filename=filename)
    await context.response.send_message(embed=embed, view=buttons, file=attachment)
    using_template[context.user.id]['message_id'] = (await context.original_response()).id

async def fill_image_field_command_prototype(context: discord.Interaction, field_name: str, image: discord.Attachment):
    global using_template
    if not context.user.id in using_template.keys():
        await context.response.send_message('An error occurred, try again later', ephemeral=True)
        log_output('Error: command use_image_field used without permission', logging.ERROR)
        return
    if not field_name.lower() in using_template[context.user.id]['fields'].keys():
        await context.response.send_message('Field \"{}\" not found for the template in use'.format(field_name), ephemeral=True)
        return
    if using_template[context.user.id]['fields'][field_name.lower()]['type'] != 'image':
        await context.response.send_message('This field is a text field. Please use command /fill_text_field', ephemeral=True)
        return
    image_array = imdecode(asarray(bytearray(image.read()), dtype=uint8), IMREAD_COLOR)
    using_template[context.user.id]['fields'][field_name.lower()]['value'] = image_array
    await context.response.send_message('Field \"{}\" has been filled'.format(field_name), ephemeral=True)

async def fill_text_field_command_prototype(context: discord.Interaction, field_name: str, text: str, font: discord.app_commands.Choice[str], font_size: float = 3., color: str = default_color_hex):
    global using_template
    if not context.user.id in using_template.keys():
        await context.response.send_message('An error occurred, try again later', ephemeral=True)
        log_output('Error: command use_image_field used without permission', logging.ERROR)
        return
    if not field_name.lower() in using_template[context.user.id]['fields'].keys():
        await context.response.send_message('Field \"{}\" not found for the template in use'.format(field_name), ephemeral=True)
        return
    if using_template[context.user.id]['fields'][field_name.lower()]['type'] != 'text':
        await context.response.send_message('This field is an image field. Please use command /fill_image_field', ephemeral=True)
        return
    result = hex_to_bgr(color)
    if not result:
        await context.response.send_message('Could not convert \"{}\" to a color. To describe a color use a hex code'.format(color), ephemeral=True)
        return
    values = text, possible_fonts[font.value], font_size, result.returnValue
    using_template[context.user.id]['fields'][field_name.lower()]['value'] = values
    await context.response.send_message('Field \"{}\" has been filled'.format(field_name), ephemeral=True)
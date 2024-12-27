"""
    File with all the commands that are meant to be registered as bot commands
"""

import discord
import logging
import asyncio
from Models.ReturnInfo import ReturnInfo
from os import path, remove as remove_file
from io import BytesIO
from cv2 import imread, imencode, imdecode, IMREAD_COLOR
from numpy import asarray, uint8

from constants import absolute_path_to_project, embed_default_color, default_color_hex, default_hue_range, default_saturation_range, default_value_range
from functions.database_functions import select as mysql_select, execute_query
from functions.image_functions import hex_to_bgr, show_fields as show_fields_image, find_biggest_rectangle

needed_data = ['client', 'db_cursor', 'db_handle', 'logging_ref']

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

async def followup_and_delete(context: discord.Interaction, message: str, delay: int = 10) -> None:
    await context.followup.send(message)
    asyncio.get_event_loop().call_later(delay, asyncio.create_task, context.delete_original_response())

async def register_template(user_id: int | str, template_number: int, file: discord.Attachment) -> ReturnInfo:
    ret = ReturnInfo(returnCode=0, Messages={
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
    ret = ReturnInfo(returnCode=0, Messages={
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
        attachment = discord.File(path.join(absolute_path_to_project, 'Images', filename), filename=filename)
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
            await context.followup.send('Sorry, something went wrong. Try again later')
            return
    filename = result.returnValue[0]
    if show_fields:
        query = 'SELECT field_name, type, up_bound, left_bound, down_bound, right_bound FROM editable_fields WHERE image_id={}'.format(result.returnValue[3])
        result = mysql_select(db_cursor, query, True, True)
        if not result:
            log_output('Error while processing a mysql query: \n\t{}\n{}'.format(query, result), logging.ERROR)
            await context.followup.send('Sorry, something went wrong. Try again later')
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
        result = show_fields_image(original_image, field_coords, field_names, bgr_color, 2)
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
    filepath = path.join(absolute_path_to_project, 'Images', filename)
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
    result = show_fields_image(original_image, [bounds], [name], bgr_color, 2)
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

async def remove_field_command_prototype(context: discord.Interaction, template_number: int, field_name: str):
    query = 'SELECT f.id FROM editable_fields AS f JOIN images AS i WHERE i.enumeration={} AND i.user_id=\"{}\" AND LOWER(f.field_name)=\"{}\"'.format(template_number, context.user.id, field_name.lower())
    result = mysql_select(db_cursor, query)
    if result.returnCode == 1:
        await context.response.send_message('No field with name \"{}\" found for template number {}\nUse /view to check your templates and fields'.format(field_name, template_number), ephemeral=True)
        return
    if not result:
        log_output('Error while processing a mysql query: \n\t{}\n{}'.format(query, result), logging.ERROR)
        await context.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
        return
    query = 'DELETE FROM editable_fields WHERE id={}'.format(result.returnValue[0])
    result = execute_query(db_handle, db_cursor, query)
    if not result:
        log_output('Error while processing a mysql query: \n\t{}\n{}'.format(query, result), logging.ERROR)
        await context.response.send_message('Sorry, something went wrong. Try again later', ephemeral=True)
        return
    await context.response.send_message('Field \"{}\" successfully removed'.format(field_name), ephemeral=True)
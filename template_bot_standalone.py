import logging
import cv2
import threading
from numpy import copy as copy_array
from typing import Callable
from os import path, access, W_OK
from sys import argv
from shutil import copy as copy_file
from functions.utils import find_option_in_args, load_settings, get_setting, settings_filename as default_settings_filename
from constants import db_required_settings, logging_format, date_format, absolute_path_to_project, default_color_hex, default_hue_range, default_saturation_range, default_value_range
from functions.database_functions import connect_database, set_logger, select as mysql_select, execute_query
from functions.image_functions import show_fields as show_image_fields, hex_to_bgr, find_biggest_rectangle, write_on_image, insert_image_into_image, get_recommended_font_size
from functions.ReturnInfo import ReturnInfo

db_handle = None
db_cursor = None
name = ''
default_color = hex_to_bgr(default_color_hex).returnValue
availible_fonts = {
    cv2.FONT_HERSHEY_SIMPLEX: 'Simple'
}

def show_image_task(window_name: str, image: cv2.Mat, threading_flag: threading.Event | None = None) -> None:
    cv2.imshow(window_name, image)
    while threading_flag is None or not threading_flag.is_set():
        if cv2.waitKey(100) & 0xFF == 27:
            break
    cv2.destroyAllWindows()

def show_dialog_menu(options: dict[int, str], title: str | None = None, error_msg: str = 'Invalid option. Please try again', forbidden_keys: list[int] = [], forbidden_message: str = 'You cannot choose this option. Please pick another') -> int:
    def is_number(number: str) -> bool:
        return number.isdigit() or (number.startswith(('+', '-')) and number[1:].isdigit())
    while True:
        print()
        keys = list(options.keys())
        keys.sort()
        if not title is None:
            print(title)
        for key in keys:
            print(f'{key}: {options[key]}')
        user_input = input('Choose an option: ')
        # Only accepting numbers
        if is_number(user_input):
            user_input = int(user_input)
            if user_input in forbidden_keys:
                print(forbidden_message)
                continue
            elif user_input in keys:
                return user_input
            else:
                print(error_msg)
        else:
            print(error_msg)

def choose_available_templates(no_templates_message = 'No templates found. Create a template first') -> ReturnInfo:
    ret = ReturnInfo(Messages={
        2: 'Something went wrong with mysql statement\nQuery: {query}\n{errMsg}',
        3: no_templates_message
    })
    query = f'SELECT id, image_extension, created_at, enumeration, filename FROM images WHERE user_id=\"{name}\"'
    result = mysql_select(db_cursor, query, True, True)
    if not result:
        ret.returnCode = 2
        ret.format_message(2, query=query, errMsg=result)
        return ret
    if len(result.returnValue) == 0:
        ret.returnCode = 3
        return ret
    option = {}
    number_to_id = {}
    temp_filenames = {}
    for record in result.returnValue:
        option[record[3]] = f'{record[1]} image. Created at: {record[2]}'
        number_to_id[record[3]] = record[0]
        temp_filenames[record[3]] = record[4]
    exit_key = max(option.keys()) + 1
    option[exit_key] = 'Exit'
    template_number = show_dialog_menu(option, 'Choose a template to add a field to')
    if template_number == exit_key:
        result.returnCode = 1
        return ret
    image_id = number_to_id[template_number]
    template_filename = temp_filenames[template_number]
    ret.returnValue = {'id': image_id, 'enumeration': template_number, 'filename': template_filename}
    return ret

def prepare(args: list[str]) -> bool:
    global db_handle
    global db_cursor
    result = find_option_in_args(args, 'settings', 'S', path.isfile, '\"{value}\" doesn\'t exist')
    if not result:
        print(result)
        return False
    settings_filename = result.returnValue if result.returnCode == 0 else default_settings_filename
    result = load_settings(setting_path=settings_filename, required_keys=db_required_settings)
    if not result:
        print(result)
        return False
    
    result = connect_database(get_setting('db_username'), get_setting('db_password'), get_setting('database_name'))
    if not result:
        print(result)
        return False
    db_handle, db_cursor = result.returnValue
    if get_setting('mysql_log_file', bool):
        formatter = logging.Formatter(logging_format, date_format)
        handler = logging.FileHandler(get_setting('mysql_log_file'), encoding='utf-8')
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        logger = logging.getLogger('standalone_templateBot')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        set_logger(logger)
    
def login() -> None:
    global name
    def validate_username(username: str) -> bool:
        if len(username) > 18:
            return False
        return username.isalnum()
    print('Please enter your username')
    print('Usernames can consist of up to 18 alphanumeric characters')
    print('To use your discord account, use your user id')
    name = input('Username: ')
    while not validate_username(name):
        print('Incorrect username. Try again')
        name = input('Username: ')
    
def view_command() -> None:
    query = f'SELECT image_extension, created_at, enumeration FROM images WHERE user_id=\"{name}\"'
    result = mysql_select(db_cursor, query, True, True)
    if not result:
        print('Something went wrong with mysql statement')
        print(f'Query: {query}')
        print(result)
        return
    template_options = {}
    forbidden_keys = []
    for i in range(1, 4):
        template_options[i] = 'No registered template'
        forbidden_keys.append(i)
    for record in result.returnValue:
        template_options[record[2]] = f'{record[0]} image. Created at: {record[1]}'
        try:
            forbidden_keys.remove(record[2])
        except ValueError:
            # This shouldn't happen without manipulating database by hand
            pass
    exit_code = max(template_options.keys()) + 1
    template_options[exit_code] = 'Exit'
    template_number = show_dialog_menu(options=template_options, title='These are your templates. Pick one to view', forbidden_keys=forbidden_keys, forbidden_message='There\'s no template to view')
    if template_number == exit_code:
        return
    show_fields = show_dialog_menu({1: 'Yes', 2: 'No'}, 'Would you like to view fields as well?') == 1
    query = f'SELECT id, filename FROM images WHERE user_id=\"{name}\" AND enumeration={template_number}'
    result = mysql_select(db_cursor, query)
    if not result:
        print('Something went wrong with mysql statement')
        print(f'Query: {query}')
        print(result)
        return
    filename = path.join(absolute_path_to_project, 'Images', result.returnValue[1])
    image = cv2.imread(filename)
    if show_fields:
        query = f'SELECT field_name, up_bound, left_bound, down_bound, right_bound, type FROM editable_fields WHERE image_id={result.returnValue[0]}'
        result = mysql_select(db_cursor, query, True, True)
        if not result:
            print('Something went wrong with mysql statement')
            print(f'Query: {query}')
            print(result)
            return
        field_names = []
        field_bounds = []
        field_types = []
        for record in result.returnValue:
            field_names.append(record[0])
            field_bounds.append((record[1], record[2], record[3], record[4]))
            field_types.append(record[5])

        result = show_image_fields(image, field_bounds, field_names, default_color)
        if not result:
            print('Error while trying to add fields to an image:')
            print(result)
            return
        image = result.returnValue
        print('Fields on this image:')
        for i in range(len(field_names)):
            print(f'{i+1}: {field_names[i]} ({field_types[i]})')
    thread = threading.Thread(target=show_image_task, args=(f'Template no. {template_number}', image))
    thread.daemon = True
    thread.start()

def create_template_command() -> None:
    print('Please provide a filepath for the template image')
    filepath = input('Filepath: ')
    while not path.isfile(filepath):
        print(f'\"{filepath}\" is not a correct filepath. Please try again')
        filepath = input('Filepath: ')
    basename = path.basename(filepath)
    if '.' in basename:
        extension = basename.split('.')[-1]
    else:
        print('Error: file has no extension')
        return
    print('Please choose a template number. Template numbers can be 1, 2 or 3 and has to have an extension')
    template_number = input('Template number: ')
    while not template_number.isdigit() or int(template_number) < 1 or int(template_number) > 3:
        print(f'\"{template_number}\" is not a correct template number. Please try again')
        template_number = input('Template number: ')
    query = f'SELECT id, image_extension, created_at FROM images WHERE user_id=\"{name}\" AND enumeration={template_number}'
    result = mysql_select(db_cursor, query)
    # 0 means record found. 1 means no record was found
    result.okCodes.append(1)
    if not result:
        print('Something went wrong with mysql statement')
        print(f'Query: {query}')
        print(result)
        return
    if result.returnCode == 0:
        record = result.returnValue
        print(f'{record[1]} file created at {record[2]} already exists for template number {template_number}')
        print('Do you want to delete this template and create a new one?')
        if show_dialog_menu({1: 'Yes, delete', 2: 'No, keep the old one'},'Do you want to delete this template and create a new one?') == 2:
            return
        query = f'DELETE FROM images WHERE id={record[0]}'
        result = execute_query(db_handle, db_cursor, query)
        if not result:
            print('Something went wrong with mysql statement')
            print(f'Query: {query}')
            print(result)
            return
        print('Deleted old template')
    query = f'INSERT INTO images (image_extension, user_id, enumeration, created_at) VALUES (\"{extension}\", \"{name}\", {template_number}, NOW())'
    result = execute_query(db_handle, db_cursor, query)
    if not result:
        print('Something went wrong with mysql statement')
        print(f'Query: {query}')
        print(result)
        return
    copy_file(filepath, path.join(absolute_path_to_project, 'Images', f'{name}_{template_number}.{extension}'))
    print('New template created')

def add_field_commad() -> None:
    result = choose_available_templates('No templates to add a field to. Create a template first')
    if not result:
        if result.returnCode != 1:
            print(result)
        return
    image_id = result.returnValue['id']
    template_filename = result.returnValue['filename']
    field_type = 'text' if show_dialog_menu({1: 'Text', 2: 'Image'}, 'What kind of field do you want to add?') == 1 else 'image'
    query = 'SELECT 1 from editable_fields WHERE field_name=\"{}\" AND image_id=' + str(image_id)
    do_loop = True
    while do_loop:
        field_name = input('Pick a name for the field: ')
        result = mysql_select(db_cursor, query.format(field_name))
        result.okCodes.append(1)
        if not result:
            print('Something went wrong with mysql statement')
            print(f'Query: {query}')
            print(result)
            return
        do_loop = result.returnCode == 0
        if do_loop:
            print('A field with that name already exists. Please choose another one')
    if show_dialog_menu({1: 'Use a reference image', 2: 'Set them by hand'}, 'What way do you want to describe boundaries for the field rectangle?') == 1:
        print('A reference image is the same image you have as your template but with a marked rectangle filled with a single color')
        filename = input('Reference image filepath: ')
        image = None
        if path.isfile(filename):
            image = cv2.imread(filename)
        while image is None:
            if not path.isfile(filename):
                print(f'Couldn\'t find file \"{filename}\"')
            else:
                print(f'Couldn\'t parse file \"{filename}\" as image')
            filename = input('Reference image filepath: ')
            if path.isfile(filename):
                image = cv2.imread(filename)
        color_hex = input('Please give an RGB hex color code for the color you\'ve used to fill the reference rectangle: ')
        result = hex_to_bgr(color_hex)
        while not result:
            print(f'{result}. Please try again')
            color_hex = input('Hex color code: ')
            result = hex_to_bgr(color_hex)
        bgr_color = result.returnValue
        result = find_biggest_rectangle(image, bgr_color, default_hue_range, default_saturation_range, default_value_range)
        if not result:
            print(result)
            return
        bounds = result.returnValue
    else:
        bounds = []
        bounds_names = ('top', 'left', 'down', 'right')
        print('Please give coordinates for a field rectangle. Top left coordinate is (0, 0)')
        for bound_name in bounds_names:
            prompt = f'Coordinate for {bound_name} boundary: '
            temp_bound = input(prompt)
            while not temp_bound.isdigit():
                print('Incorrect boundary. Only accepting positive integers')
                temp_bound = input(prompt)
            bounds.append(int(temp_bound))
        bounds = tuple(bounds)
        bgr_color = hex_to_bgr(default_color_hex).returnValue
    image = cv2.imread(path.join(absolute_path_to_project, 'Images', template_filename))
    result = show_image_fields(image, [bounds], [field_name], bgr_color)
    if not result:
        print('Error while trying to generate an image with the new field')
        print(result)
        return
    image_with_field = result.returnValue
    shared_flag = threading.Event()
    thread = threading.Thread(target=show_image_task, args=(field_name, image_with_field, shared_flag))
    thread.daemon = True
    print('Showing image...')
    thread.start()
    stop_command = show_dialog_menu({1: 'Yes', 2: 'No'}, 'Is this correct?') == 2
    shared_flag.set()
    if stop_command:
        return
    query = f'INSERT INTO editable_fields (field_name, type, up_bound, left_bound, down_bound, right_bound, image_id) VALUES (\"{field_name}\", \"{field_type}\", {bounds[0]}, {bounds[1]}, {bounds[2]}, {bounds[3]}, {image_id})'
    result = execute_query(db_handle, db_cursor, query)
    if not result:
        print('Something went wrong with mysql statement')
        print(f'Query: {query}')
        print(result)
        return
    print(f'Field {field_name} has been created!')

def remove_field() -> None:
    result = choose_available_templates('No templates to remove a field from. Create a template first')
    if not result:
        if result.returnCode != 1:
            print(result)
        return
    image_id = result.returnValue['id']
    query = f'SELECT field_name, type FROM editable_fields WHERE image_id={image_id}'
    result = mysql_select(db_cursor, query, True, True)
    if not result:
        print('Something went wrong with mysql statement')
        print(f'Query: {query}')
        print(result)
        return
    if len(result.returnValue) == 0:
        print('There are not fields associated with the chosen template')
        return
    options = {}
    names = {}
    for idx, record in enumerate(result.returnValue):
        options[idx + 1] = f'{record[0]} ({record[1]} field)'
        names[idx + 1] = record[0]
    exit_code = max(options.keys()) + 1
    options[exit_code] = 'Exit'
    chosen_key = show_dialog_menu(options, 'Choose a field to delete')
    if chosen_key == exit_code:
        return
    field_name = names[chosen_key]
    query = f'DELETE FROM editable_fields WHERE field_name=\"{field_name}\" AND image_id={image_id}'
    result = execute_query(db_handle, db_cursor, query)
    if not result:
        print('Something went wrong with mysql statement')
        print(f'Query: {query}')
        print(result)
        return
    print(f'Field {field_name} has been deleted')
    
# def use_template_command(template_info: tuple[str] | None = None, fields: dict | None = None) -> None:
def use_template_command(data: dict | None = None) -> None:
    if data is None:
        result = choose_available_templates()
        if not result:
            if result.returnCode != 1:
                print(result)
            return
        image_filepath = path.join(absolute_path_to_project, 'Images', result.returnValue['filename'])
        template_image = cv2.imread(image_filepath)
        image_id = result.returnValue['id']
        query = f'SELECT field_name, type, up_bound, left_bound, down_bound, right_bound FROM editable_fields WHERE image_id={image_id}'
        result = mysql_select(db_cursor, query, True, True)
        if not result:
            print('Something went wrong with mysql statement')
            print(f'Query: {query}')
            print(result)
            return
        text_fields = {}
        image_fields = {}
        for record in result.returnValue:
            field_data = {
                'bounds': (record[2], record[3], record[4], record[5]),
                'value': None,
                'updated': False
            }
            if record[1] == 'text':
                text_fields[record[0]] = field_data
            else:
                image_fields[record[0]] = field_data
        fields = {'text': text_fields, 'image': image_fields}
        data = {
            'original_image': template_image,
            'image': copy_array(template_image),
            'fields': fields
        }
    else:
        fields = data['fields']
    text_fields_count = len(fields['text'])
    image_fields_count = len(fields['image'])
    options = {
        1: 'Preview template with fields',
        2: f'Fill text field ({text_fields_count} field{"" if text_fields_count == 1 else "s"})',
        3: f'Fill image field ({image_fields_count} field{"" if image_fields_count == 1 else "s"})',
        4: 'Finish and save image as file',
        5: 'Cancel and exit'
    }
    forbidden_options = []
    if text_fields_count == 0:
        forbidden_options.append(2)
    if image_fields_count == 0:
        forbidden_options.append(3)
    forbidden_message = 'There\'s no fields to fill'
    title = 'Template in use. What would you like to do?'
    chosen_option = show_dialog_menu(options, title, forbidden_keys=forbidden_options, forbidden_message=forbidden_message)
    if chosen_option == 1:
        preview_template(data)
        use_template_command(data)
    elif chosen_option == 2:
        fill_text_field(data)
        use_template_command(data)
    elif chosen_option == 3:
        fill_image_field(data)
        use_template_command(data)
    elif chosen_option == 4:
        save_image(data)
    
def update_image(data: dict) -> bool:
    text_fields_to_update = [(field_name, field['bounds'], field['value']) for field_name, field in data['fields']['text'].items() if not field['updated'] and not field['value'] is None]
    image_fields_to_update = [(field_name, field['bounds'], field['value']) for field_name, field in data['fields']['image'].items() if not field['updated'] and not field['value'] is None]
    for field in text_fields_to_update:
        field_name = field[0]
        bounds = field[1]
        text, font, font_size, color = field[2]
        result = write_on_image(data['image'], text, font, font_size, color, 2, cv2.LINE_8, bounds)
        if not result:
            print(f'Error while updating field \"{field_name}\"')
            print(result)
            return False
        data['image'] = result.returnValue
        data['fields']['text'][field_name]['updated'] = True
    for field in image_fields_to_update:
        field_name = field[0]
        bounds = field[1]
        image = field[2]
        result = insert_image_into_image(data['image'], image, bounds)
        if not result:
            print(f'Error while updating field \"{field_name}\"')
            print(result)
            return False
        data['image'] = result.returnValue
        data['fields']['image'][field_name]['updated'] = True
    return True

def preview_template(data: dict) -> None:
    if update_image(data):
        threading.Thread(target=show_image_task, args=('Previewing imge', data['image']), daemon=True).start()

def fill_text_field(data: dict) -> None:
    options = {}
    id_to_name = {}
    for idx, (field_name, field) in enumerate(data['fields']['text'].items()):
        text = field['value'][0] if not field['value'] is None else '-no text set-'
        options[idx + 1] = f'{field_name} ({text})'
        id_to_name[idx + 1] = field_name
    exit_code = max(options.keys()) + 1
    options[exit_code] = 'Cancel'
    result = show_dialog_menu(options, 'Choose a text field to fill out')
    if result == exit_code:
        return
    field_name = id_to_name[result]
    field = data['fields']['text'][field_name]
    is_update = not field['value'] is None
    id_to_key = {}
    options = {}
    for idx, (font, font_name) in enumerate(availible_fonts.items()):
        options[idx + 1] = font_name
        id_to_key[idx + 1] = font
    font = id_to_key[show_dialog_menu(options, 'Which font do you want to use?')]
    print('Which text do you want to display on the field?')
    text = input('Text: ')
    estimated_font_size = get_recommended_font_size(field['bounds'], len(text))
    print(f'What size do you want your text to be? For this field and text recommended size is {estimated_font_size:.2f}')
    font_size = None
    while font_size is None:
        size_raw = input('Size: ')
        try:
            font_size = float(size_raw)
        except ValueError:
            print(f'Couldn\'t convert \"{size_raw}\" to a float')
            print('Please try again')
    print('What color do you want your text to be?')
    color = None
    while color is None:
        color_raw = input('Color\'s RGB hex code: ')
        result = hex_to_bgr(color_raw)
        if result:
            color = result.returnValue
        else:
            print(result)
            print('Please try again')
    data['fields']['text'][field_name]['value'] = text, font, font_size, color
    if is_update:
        # For text field if I don't do it, text could overlap with itself
        # This isn't issue for image fields because this program doesn't support transparent images yet
        for field_type in data['fields'].keys():
            for field_name in data['fields'][field_type].keys():
                data['fields'][field_type][field_name]['updated'] = False
        data['image'] = copy_array(data['original_image'])
    print(f'Field {field_name} filled out!')

def fill_image_field(data: dict) -> None:
    options = {}
    id_to_name = {}
    for idx, (field_name, field) in enumerate(data['fields']['image'].items()):
        text = field['value'][0] if not field['value'] is None else '-no image set-'
        options[idx + 1] = f'{field_name} ({text})'
        id_to_name[idx + 1] = field_name
    exit_code = max(options.keys()) + 1
    options[exit_code] = 'Cancel'
    result = show_dialog_menu(options, 'Choose an image field to fill out')
    if result == exit_code:
        return
    field_name = id_to_name[result]
    print('Provide a filepath to an image you\'d like to use to fill out this field')
    check_ok = False
    while not check_ok:
        filepath = input('Filepath: ')
        if not path.isfile(filepath):
            print(f'{filepath} is not a path to a file')
            print('Please try again')
            continue
        image = cv2.imread(filepath)
        if image is None:
            print(f'Couldn\'t open {filepath} as image')
            print('Please try again')
            continue
        check_ok = True
    data['fields']['image'][field_name]['value'] = image
    print(f'Field {field_name} filled out!')

def save_image(data: dict) -> None:
    print('Please provide a filepath for the image to be saved to')
    check_ok = False
    while not check_ok:
        filepath = input('Filepath: ')
        if filepath == '':
            continue
        if path.isdir(filepath):
            print(f'{filepath} is dir, can\'t overwrite')
            print('Please try again')
            continue
        parent_dir = path.dirname(filepath)
        if not parent_dir:
            parent_dir = '.'
        if not path.isdir(parent_dir):
            print(f'{parent_dir} does not exist')
            print('Please try again')
            continue
        if not access(parent_dir, W_OK):
            print(f'Cannot create a file in {parent_dir}')
            print('Please try again')
            continue
        check_ok = True
    update_image(data)
    cv2.imwrite(filepath, data['image'])
    print(f'image saved to {filepath}')

def main() -> None:
    prepare(argv[1:])
    login()
    options: dict[int, Callable[[], None]] = {
        1: view_command,
        2: create_template_command,
        3: add_field_commad,
        4: remove_field,
        5: use_template_command
    }
    names: dict[int, str] = {
        1: 'View',
        2: 'Create template',
        3: 'Add field',
        4: 'Remove field',
        5: 'Use a template'
    }
    exit_code = max(names.keys()) + 1
    names[exit_code] = 'Exit'
    while True:
        result = show_dialog_menu(names, 'Please pick an option')
        if result == exit_code:
            break
        options[result]()

if __name__ == '__main__':
    main()
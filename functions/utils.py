import os
import sys
import json
from mysql.connector.cursor import MySQLCursor
from hashlib import sha256
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Callable
from .ReturnInfo import ReturnInfo
from .database_functions import select as mysql_select
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import settings_filename, description_placeholder

settings = {}
descriptions = {}

def find_option_in_args(args: list[str], option_name: str, option_short: str | None = None, verify_function: Callable[[str], bool] = lambda _: True, custom_failure_message: str = '\"{value}\" is not a correct value for option \"{option_name}\"') -> ReturnInfo:
    ret = ReturnInfo(okCodes=[0,1], Messages={
        1: 'No option found',
        2: 'No value given for option \"{option_name}\"',
        3: custom_failure_message
    })
    if not option_name.startswith('--'):
        option_name = '--' + option_name
    if not option_short is None and not option_short.startswith('-'):
        option_short = '-' + option_short
    index = None
    value = None
    if option_name in args:
        index = args.index(option_name)
    elif option_short in args:
        index = args.index(option_short)
    if not index is None:
        try:
            value = args[index + 1]
        except IndexError:
            ret.format_message(2, option_name=option_name)
            ret.returnCode = 2
            return ret
        if not verify_function(value):
            ret.format_message(3, value=value, option_name=option_name)
            ret.returnCode = 3
            return ret
    else:
        # Guaranteed for each argument to not be exactly option name or short option name
        for arg in args:
            for opt in (option_name, option_short):
                if opt is None:
                    continue
                if arg.startswith(opt):
                    value = arg[(len(opt)):]
                    if not verify_function(value):
                        ret.format_message(3, value=value, option_name=opt)
                        ret.returnCode = 3
                        return ret
    # If value is still None it means that no option was found
    if value is None:
        ret.returnCode = 1
        return ret
    ret.returnValue = value
    return ret

# Function to load all the settings
def load_settings(setting_path: str = settings_filename, required_keys: list = []) -> ReturnInfo:
    global settings
    result = ReturnInfo(Messages={
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

def load_descriptions(db_cursor: MySQLCursor) -> ReturnInfo:
    global descriptions
    query = 'SELECT d.field_name, d.description_text FROM descriptions AS d'
    result = mysql_select(db_cursor, query, True, True)
    if not result:
        return result
    for row in result.returnValue:
        descriptions[row[0]] = row[1]
    return ReturnInfo()

# Easier way to get a setting without worrying if it's been set if it's negligable
def get_setting(setting_name: str, type_of_setting: type | None = None) -> str | int | bool | None:
    if setting_name in settings.keys():
        if type_of_setting is None:
            return settings[setting_name]
        return type_of_setting(settings[setting_name])
    if type_of_setting == str:
        return ''
    if type_of_setting == int:
        return 0
    if type_of_setting == bool:
        return False
    return None

def is_setting(setting_name):
    return setting_name in settings

def get_description(field_name: str) -> str:
    return descriptions[field_name] if field_name in descriptions.keys() else description_placeholder

def generate_temp_hash() -> str:
    return sha256(os.urandom(32)).hexdigest()

def custom_time(*_):
    timezone = ZoneInfo(get_setting('timezone', str)) if get_setting('timezone', bool) else None
    now = datetime.now(timezone)
    return now.timetuple()
import os
import sys
import json
from mysql.connector.cursor import MySQLCursor
from hashlib import sha256
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Models.ReturnInfo import ReturnInfo
from constants import settings_filename, description_placeholder
from functions.database_functions import select as mysql_select

settings = {}
descriptions = {}

# Function to load all the settings
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

def load_descriptions(db_cursor: MySQLCursor) -> ReturnInfo:
    global descriptions
    query = 'SELECT d.field_name, d.description_text FROM descriptions AS d'
    result = mysql_select(db_cursor, query, True, True)
    if not result:
        return result
    for row in result.returnValue:
        descriptions[row[0]] = row[1]
    return ReturnInfo(returnCode=0)

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
""""""

import discord

import os
import json

from Models.ReturnInfo import ReturnInfo

settings = {}
required_settings = ['app_token']

def load_settings(setting_path: str = 'settings.json', required_keys: list = []) -> ReturnInfo:
    global settings
    result = ReturnInfo(returnCode=0, Messages={
        1: f'Error: File \"{setting_path}\" not found',
        2: 'Error: Unable to open the file',
        3: 'Error: Unable to read json',
        4: 'Error: Missing required key(s): {}'
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

def main():
    result = load_settings(required_keys=required_settings)
    if not result:
        print(result)
        return
    print(settings)


if __name__ == '__main__':
    main()
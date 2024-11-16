"""
File used to store all constants
These are meant to not be changed, thus are not in the settings file
"""

from discord import Intents

required_settings = ['app_token']
settings_filename = 'settings.json'
discord_intents = Intents.default()
date_format = '%Y-%m-%d %H:%M:%S'
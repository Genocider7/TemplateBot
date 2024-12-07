"""
File used to store all constants
These are meant to not be changed, thus are not in the settings file
"""

from discord import Intents
import os.path

absolute_path_to_project = os.path.dirname(os.path.abspath(__file__))

main_required_settings = ['app_token']
db_required_settings = ['db_username', 'db_password', 'database_name']

settings_filename = os.path.join(absolute_path_to_project, 'settings.json')

discord_intents = Intents.default()

date_format = '%Y-%m-%d %H:%M:%S'

description_placeholder = 'Missing description'

setup_database_script = os.path.join(absolute_path_to_project, 'Database', 'setup_database_script.sql')
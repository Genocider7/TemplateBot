"""
File used to store all constants
These are meant to not be changed, thus are not in the settings file
"""

from discord import Intents, Color
import os.path

project_name = 'TemplateBot'
absolute_path_to_project = os.path.dirname(os.path.abspath(__file__))

main_required_settings = ['app_token']
db_required_settings = ['db_username', 'db_password', 'database_name']

settings_filename = os.path.join(absolute_path_to_project, 'settings.json')

discord_intents = Intents.default()

logging_format = '%(asctime)s %(levelname)s\t%(name)s %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'

description_placeholder = 'Missing description'

setup_database_script = os.path.join(absolute_path_to_project, 'Database', 'setup_database_script.sql')

skip_tables_for_testdata = ['descriptions']
priority_fields = ['images']

embed_default_color = Color.orange()

temporary_file_timer = 60
log_file_split_check_timer = 60

default_hue_range = 20
default_saturation_range = 30
default_value_range = 20
default_color_hex = '#0000FF'
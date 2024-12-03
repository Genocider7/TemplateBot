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

setup_database_mysql_script = """
DROP TABLE IF EXISTS editable_fields;
DROP TABLE IF EXISTS images;

CREATE TABLE images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_name VARCHAR(255) NOT NULL,
    image_extension VARCHAR(5) NOT NULL,
    user_id VARCHAR(18) NOT NULL,
    enumeration TINYINT NOT NULL
);

CREATE TABLE editable_fields (
    id INT AUTO_INCREMENT PRIMARY KEY,
    field_name VARCHAR(255) NOT NULL,
    type ENUM("text", "image") NOT NULL DEFAULT "text",
    up_bound SMALLINT NOT NULL,
    left_bound SMALLINT NOT NULL,
    down_bound SMALLINT NOT NULL,
    right_bound SMALLINT NOT NULL,
    image_id INT NOT NULL,
    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
);
"""
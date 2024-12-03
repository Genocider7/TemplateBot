import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from functions.database_functions import connect_database
from functions.utils import load_settings
from constants import db_required_settings, setup_database_mysql_script

def main():
    settings = load_settings(required_keys=db_required_settings)
    if not settings:
        print(settings)
        return
    settings = settings.returnValue
    connection = connect_database(settings['db_username'], settings['db_password'])
    if not connection:
        print(connection)
        return
    _, db_cursor = connection.returnValue
    db_cursor.execute('CREATE DATABASE IF NOT EXISTS {}'.format(settings['database_name']))
    db_cursor.execute('USE {}'.format(settings['database_name']))
    for statement in [s.strip() for s in setup_database_mysql_script.strip().split(';')]:
        if statement:
            db_cursor.execute(statement)
            print('Executed: {}'.format(statement))
    print('Done')

if __name__ == '__main__':
    main()
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from functions.database_functions import connect_database
from functions.utils import load_settings
from constants import db_required_settings, setup_database_script
from mysql.connector import Error as mysql_error, errorcode

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
    ok = False
    try:
        with open(setup_database_script, 'r') as query_file:
            statements = [s.strip() for s in query_file.read().split(';')]
        statements = ['CREATE DATABASE IF NOT EXISTS {}'.format(settings['database_name']), 'USE {}'.format(settings['database_name'])] + statements
        for statement in statements:
            if statement:
                db_cursor.execute(statement)
                print('Executed: {}'.format(statement))
        ok = True
    except mysql_error as err:
        if err.errno == errorcode.ER_DBACCESS_DENIED_ERROR:
            print('Program was not able to continue due to insufficient privileges for {}@localhost'.format(settings['db_username']))
            print('Needed global privileges: CREATE')
            print('Privileges needed at least for table {} (if already exists): DROP, REFERENCES'.format(settings['database_name']))
        else:
            print(err)
    except FileNotFoundError:
        print('File \"{}\" does not exist'.format(setup_database_script))
        return
    except PermissionError:
        print('Program could not access file \"{}\" due to missing permissions'.format(setup_database_script))
        return
    if ok:
        print('Done')

if __name__ == '__main__':
    main()
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import db_required_settings
from functions.utils import load_settings
from functions.database_functions import connect_database, execute_query

def main(args: str) -> None:
    if len(args) == 0:
        print('Usage: {} script'.format(os.path.basename(__file__)))
        return
    filename = args[0]
    try:
        with open(filename, 'r') as file:
            statements = [s.strip() for s in file.read().split(';') if s.strip()]
    except FileNotFoundError:
        print('File \"{}\" does not exist'.format(filename))
        return
    except PermissionError:
        print('Program could not access file \"{}\" due to missing permissions'.format(filename))
        return
    result = load_settings(required_keys=db_required_settings)
    if not result:
        print(result)
        return
    settings = result.returnValue
    result = connect_database(settings['db_username'], settings['db_password'], settings['database_name'])
    if not result:
        print(result)
        return
    db_handle, db_cursor = result.returnValue
    for statement in statements:
        query_result = execute_query(db_handle, db_cursor, statement)
        if not query_result:
            print(query_result)
            return
        print('Executed: {}'.format(statement))
    print('Done')

if __name__ == '__main__':
    main(sys.argv[1:])
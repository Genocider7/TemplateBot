import sys
import os
from typing import Any
from datetime import datetime
from copy import deepcopy
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import absolute_path_to_project, db_required_settings, skip_tables_for_testdata, priority_fields
from functions.utils import load_settings, get_setting
from functions.database_functions import connect_database, select

default_target_filename = os.path.join(absolute_path_to_project, 'Database', 'testdata.sql')

db_connection = None
db_cursor = None

def setup():
    global db_connection
    global db_cursor
    result = load_settings(required_keys=db_required_settings)
    if not result:
        print(result)
        return
    result = connect_database(get_setting('db_username'), get_setting('db_password'), get_setting('database_name'))
    if not result:
        print(result)
        return
    # db_connection is needed because db_cursor has to exist in the same scope as connection
    db_connection, db_cursor = result.returnValue

def get_data() -> dict[str, dict[str, list[str] | list[tuple[Any]]]] | None:
    query = 'SHOW TABLES'
    result = select(db_cursor, query, True)
    if not result:
        print(result)
        return
    table_names = [res[0] for res in result.returnValue if not res[0] in skip_tables_for_testdata]
    data = {}
    main_query = 'SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME="{table_name}" AND TABLE_SCHEMA="{database_name}" AND EXTRA NOT IN ("auto_increment", "VIRTUAL GENERATED")'
    for table_name in table_names:
        formatted_query = main_query.format(table_name=table_name, database_name=get_setting('database_name'))
        result = select(db_cursor, formatted_query, True)
        if not result:
            print(result)
            return
        # Given in a set order
        field_names = [res[0] for res in result.returnValue]
        query = 'SELECT ' + ', '.join(field_names) + f' FROM {table_name}'
        result = select(db_cursor, query, True)
        result.okCodes += [1]
        if not result:
            print(result)
            return
        # if no values in the table, skip
        if result.returnCode == 1:
            continue
        data[table_name] = {'fields': field_names, 'values': result.returnValue}
    return data

def put_data_in_file(data: dict[str, dict[str, list[str] | list[tuple[Any]]]], filename: str) -> bool:
    # Have to make sure that tables that have a foreign key are considered later
    higher_priority = {}
    lower_priority = {}
    for key in data.keys():
        if key in priority_fields:
            higher_priority[key] = data[key]
        else:
            lower_priority[key] = data[key]
    queries = []
    for hierarchy_data in [higher_priority, lower_priority]:
        for table_name, v in hierarchy_data.items():
            field_names = v['fields']
            field_values = v['values']
            table_query = f'INSERT INTO {table_name} (' + ', '.join(field_names) + ') VALUES'
            for values in field_values:
                formatted_values = []
                for value in values:
                    formatted_value = deepcopy(value)
                    if isinstance(formatted_value, datetime):
                        formatted_value = '\"' + formatted_value.strftime("%Y-%m-%d %H:%M:%S") + '\"'
                    elif type(formatted_value) == str:
                        formatted_value = '\"' + formatted_value + '\"'
                    else:
                        formatted_value = str(formatted_value)
                    formatted_values.append(formatted_value)
                table_query += '\n\t(' + ', '.join(formatted_values) + '),'
            # Guaranteed at least one iteration of the loop
            # Exchange last "," for newline and ";"
            table_query = table_query[:-1] + '\n;'
            queries.append(table_query)
    total_query = '\n\n'.join(queries)
    try:
        with open(filename, 'w') as file:
            file.write(total_query)
    except PermissionError:
        print(f'Couldn\'t access file \"{filename}\"')
        return False
    except IsADirectoryError:
        print(f'\"{filename}\" is a directory')
        return False
    return True    

if __name__ == '__main__':
    setup()
    data = get_data()
    if data is None:
        exit()
    target_filename = sys.argv[1] if len(sys.argv) > 1 else default_target_filename
    success = put_data_in_file(data, target_filename)
    if success:
        print('ok')
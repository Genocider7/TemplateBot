import mysql.connector
from mysql.connector import errorcode
from mysql.connector.cursor import MySQLCursor
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Models.ReturnInfo import ReturnInfo

def connect_database(username: str, password: str, database: None | str = None) -> ReturnInfo:
    ret = ReturnInfo(returnCode=0, Messages={
        1: 'Error: incorrect username or password',
        2: 'Database \"{}\" does not exist'.format(database)
    })
    config = {
        'user': username,
        'password': password,
        'host': 'localhost'
    }
    if not database is None:
        config['database'] = database
    try:
        db_handle = mysql.connector.connect(**config)
        db_cursor = db_handle.cursor()
        ret.returnValue = db_handle, db_cursor
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            ret.returnCode = 1
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            ret.returnCode = 2
        else:
            ret.returnCode = 3
            ret.Messages[3] = str(err)
    return ret

def select(db_cursor: MySQLCursor, query: str, multiple: bool = False, return_empty_list: bool = False) -> ReturnInfo:
    ret = ReturnInfo(returnCode=0, Messages={
        1: 'Query returned no entries'
    })
    errorcode_offset = max(ret.Messages.keys())
    try:
        db_cursor.execute(query)
        result = db_cursor.fetchall() if multiple else db_cursor.fetchone()
        if result is None or (multiple and not return_empty_list and len(result) == 0):
            ret.returnCode = 1
            return ret
        ret.returnValue = result
    except mysql.connector.Error as err:
        ret.returnCode = err.errno + errorcode_offset
        ret.Messages[err.errno + errorcode_offset] = str(err)
    return ret

def execute_query(db_handle: mysql.connector.MySQLConnection, db_cursor: MySQLCursor, query: str) -> ReturnInfo:
    ret = ReturnInfo(returnCode=0, Messages={})
    try:
        db_cursor.execute(query)
        db_handle.commit()
    except mysql.connector.Error as err:
        ret.returnCode = err.errno
        ret.Messages[err.errno] = str(err)
    return ret
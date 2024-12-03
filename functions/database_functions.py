import mysql.connector
from mysql.connector import errorcode
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
    except mysql.connector.error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            ret.returnCode = 1
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            ret.returnCode = 2
        else:
            ret.returnCode = 3
            ret.Messages[3] = str(err)
    return ret
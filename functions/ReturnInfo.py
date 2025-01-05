from typing import Any

class ReturnInfo():
    def __init__(self, returnCode: int = 0, okCodes: list[int] = [0], Messages: dict[int, str] = {}, returnValue: Any = None):
        self.returnCode = returnCode
        self.okCodes = okCodes
        self.Messages = Messages
        self.returnValue = returnValue
    
    def format_message(self, key: int, *args, **kwargs):
        self.Messages[key] = self.Messages[key].format(*args, **kwargs)
        
    def __bool__(self):
        if self.returnCode is None:
            return False
        return self.returnCode in self.okCodes

    def __str__(self):
        if self.returnCode is None:
            return 'Error: return code is None'
        if type(self.Messages) == dict and self.returnCode in self.Messages.keys():
            return self.Messages[self.returnCode]
        return 'OK' if self else 'Error'
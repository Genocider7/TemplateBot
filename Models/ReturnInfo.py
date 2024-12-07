""""""

from .Model import Model

class ReturnInfo(Model):
    @property
    def argumentOrder(self):
        return ['returnCode', 'okCodes', 'Messages', 'returnValue']
    
    def __init__(self, *args, **kwargs):
        self.returnCode = None
        self.okCodes = None
        self.Messages = None
        self.returnValue = None
        for var_name, var_value in self.organizeArguments(*args, **kwargs).copy().items():
            setattr(self, var_name, var_value)
        if self.okCodes is None:
            self.okCodes = [0]
        if self.Messages is None:
            self.Messages = {}
    
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
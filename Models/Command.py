"""class for all commands for organized and easy use"""

from .Model import Model

class Command(Model):
    @property
    def argumentOrder(self):
        return ['name', 'description']
    
    def __init__(self, *args, **kwargs):
        self.name = None
        self.description = None
        for var_name, var_value in self.organizeArguments(*args, **kwargs).copy().items():
            setattr(self, var_name, var_value)
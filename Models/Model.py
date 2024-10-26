"""Abstract class for all models to use.
It simplifies argument use in constructors"""

from abc import ABC
from .Exceptions import *
import sys

class Model(ABC):
    @property
    def argumentOrder(self):
        return []

    def organizeArguments(self, *args, **kwargs):
        local_variables = self.__dict__.copy()
        if len(args) > len(local_variables.keys()):
            print(f'Too many positional arguments were given ({len(args)}) while class only takes up to {len(local_variables.keys())} variables', file=sys.stderr)
            raise TooManyArgumentsException
        for i in range(len(args)):
            local_variables[self.argumentOrder[i]] = args[i]
        
        for var_name, var_value in kwargs.items():
            if var_name not in local_variables.keys():
                print(f'Argument \"{var_name}\" not found in class\' variables')
                raise AttributeError
            if var_name not in self.argumentOrder:
                print(f'Argument \"{var_name}\" is not accessible to be set')
                raise AttributeError
            if local_variables[var_name] != None:
                print(f'Value \"{var_name}\" has been set twice', file=sys.stderr)
                raise TwiceSetException
            local_variables[var_name] = var_value
        
        return local_variables
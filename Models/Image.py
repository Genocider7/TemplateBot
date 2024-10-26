""""""

from .Model import Model
from pathlib import Path
from ReturnInfo import ReturnInfo

class Image(Model):
    @property
    def argumentOrder(self):
        return ['id', 'filepath']
    
    def verifyFilepath(self):
        result = ReturnInfo(Messages={
            1: 'Error: Filepath has not been set',
            2: f'Error: File \"{self.filepath}\" not found',
            3: 'Filepath is not str or Path'
        })
        if self.filepath is None:
            result.returnCode = 1
            return result
        if isinstance(self.filepath, Path):
            filepath = self.filepath
        elif type(self.filepath) == str:
            filepath = Path(self.filepath)
        else:
            result.returnCode = 3
            return result
        if filepath.is_file():
            result.returnCode = 0
        else:
            result.returnCode = 2
        return result
            

    def __init__(self, *args, **kwargs):
        self.id = None
        self.filepath = None
        for var_name, var_value in self.organizeArguments(*args, **kwargs).copy().items():
            setattr(self, var_name, var_value)
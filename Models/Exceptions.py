"""Custom Exceptions"""

class TwiceSetException(Exception):
    # Exception that is raised when an argument is being set twice
    pass

class TooManyArgumentsException(Exception):
    # Exception that is raised when there are too many arguments in any context
    pass
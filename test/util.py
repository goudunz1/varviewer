from enum import Enum

class VariableType(Enum):
    INVALID = -1
    MEM_GLOABL = 0
    MEM_CFA = 1
    MEM_SINGLE = 2
    MEM_MULTI = 3

    REG_PARAM = 4
    REG_OTHER = 5

    IMPLICIT = 6

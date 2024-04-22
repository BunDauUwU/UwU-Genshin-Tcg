from enum import Enum


class CostType(Enum):
    NONE = 0
    SAME = 1
    ANY = 2


class ElementType(Enum):
    NONE = -1
    OMNI = 0
    CRYO = 1 
    HYDRO = 2 
    PYRO = 3 
    ELECTRO = 4 
    GEO = 5 
    DENDRO = 6
    ANEMO = 7 


class WeaponType(Enum):
    NONE = 0
    BOW = 1 
    SWORD = 2 
    CLAYMORE = 3 
    POLEARM = 4 
    CATALYST = 5 
    OTHER_WEAPONS = 6 


class PlayerAction(Enum):
    USING_SKILLS = 1
    ELEMENT_TUNING = 2
    END_ROUND = 3
    CHANGE_CHARACTER = 4
    PLAY_CARD = 5


class GameStage(Enum):
    NONE = 0
    GAME_START = 1
    ROUND_START = 2
    ROLL = 3
    ACTION = 4
    ROUND_END = 5
    GAME_END = 6

    REROLL = 10


class Nation(Enum):
    NONE = 0
    Mondstadt = 1
    Liyue = 2 
    Inazuma = 3 
    Sumeru = 4 
    Monster = 5 
    Fatui = 6 
    Hilichurl = 7


class SkillType(Enum):
    NORMAL_ATTACK = 1 
    ELEMENTAL_SKILL = 2
    ELEMENTAL_BURST = 3 
    PASSIVE_SKILL = 4 


class CardType(Enum):
    ANY = 0
    TALENT = 1
    WEAPON = 2
    ELEMENTAL_RESONANCE = 3
    FOOD = 4
    NORMAL_EVENT = 5
    ARTIFACT = 6


class TimeLimit(Enum):
    INFINITE = 1 
    IMMEDIATE = 2 
    ROUND = 3 
    USAGE = 4 
    DURATION = 5 

    ACT = 8 
    USE_UP = 9 
    PREPARE = 10 


class EffectObj(Enum):
    ACTIVE = 1 
    STANDBY = 2 
    OPPOSE_ACTIVE = 3
    OPPOSE_STANDBY = 4 
    ALL = 5
    OPPOSE_ALL = 6 
    SELF = 7
    TEAM = 8 
    OPPOSE_SELF = 9 
    OPPOSE_TEAM = 10
    SUMMON = 11
    OPPOSE_SUMMON = 12
    ALL_SUMMON = 13 
    ALL_TEAM = 14
    SUPPORT = 15
    OPPOSE_SUPPORT = 16 
    ALL_SUPPORT = 17 
    DECK = 18 
    OPPOSE = 19 
    CARD = 20
    OPPOSE_CARD = 21 
    NO_SELF = 22
    NO_OPPOSE_SELF = 23
    SUPER = 24
    STATE = 25
    PLAYER = 26
    ALL_BUT_ONE = 27

    COUNTER = 30


class ConditionType(Enum):
    BEING_HIT = 1  

    STAGE_ROUND_START = 2
    STAGE_ROLL = 3
    STAGE_ACTION = 4
    STAGE_ROUND_END = 5

    IS_ACTIVE = 6
    BEING_HIT_BY = 7 
    USE_SKILL = 8
    NEED_HEAL = 9

    CHANGE_AVATAR = 10 
    BE_CHANGED_AS_ACTIVE = 11
    CHANGE_TO_STANDBY = 12 

    HAVE_CARD = 13
    DONT_HAVE_CARD = 14

    HAVE_STATE = 15  
    HAVE_SUMMON = 16
    HAVE_MODIFY = 17

    IS_NOT_ACTIVE = 18

    GET = 19 

    CHECK = 20 

    EXCLUSIVE = 21 

    ELEMENT_REACTION = 22
    ELEMENT_HURT = 23
    ELEMENT_DMG = 24
    NORMAL_ATTACK = 25
    ELEMENTAL_SKILL = 26
    ELEMENTAL_BURST = 27
    ATTACK = 28
    SKILL = 29 

    REMOVE = 30
    EQUIP = 31
    PLAY_CARD = 32 

    PYRO_RELATED = 33
    HYDRO_RELATED = 34
    ELECTRO_RELATED = 35
    DENDRO_RELATED = 36
    CRYO_RELATED = 37
    ANEMO_RELATED = 38
    GEO_RELATED = 39

    OPPOSE_USE_SKILL = 40
    DIE = 41
    OPPOSE_DIE = 42

    HAVE_SHIELD = 43

    REPLACE = 45
    FORCE = 46

    GET_SELECT = 47
    GET_ENERGY = 48
    GET_SKILL_NAME = 49
    GET_ELEMENT = 50
    SWIRL = 51 
    ACTIVE_FIRST = 52 
    DIFFERENCE_FIRST = 53 
    GET_MOST_HURT = 54
    COMPARE = 55 
    IS_ALIVE = 56

    OR = 60 
    NEED_REMOVE = 61 
    TRY = 62
    ONLY = 63  
    GET_TRY = 64


class EffectType(Enum):
    HURT = 1 
    DMG = 2  

    CRYO_DMG = 17 
    HYDRO_DMG = 18  
    PYRO_DMG = 19 
    ELECTRO_DMG = 20  
    GEO_DMG = 21 
    DENDRO_DMG = 22  
    ANEMO_DMG = 23 
    PHYSICAL_DMG = 26 

    CHANGE_CHARACTER = 30 
    CHANGE_COST = 31 
    CHANGE_ACTION = 32 
    CHANGE_TO = 33

    SHIELD = 34 

    PIERCE = 35 
    PIERCE_DMG = 36

    HEAL = 38 
    FROZEN = 39  

    INFUSION = 40 
    APPLICATION = 41 

    SKILL_ADD_ENERGY = 43
    CHANGE_ENERGY = 44 
    SET_ENERGY = 45

    DRAW_CARD = 47
    ADD_CARD = 48  
    ADD_MODIFY = 50 
    REMOVE_CARD = 51
    REROLL = 52

    TRIGGER = 55 
    CONSUME_SUMMON_USAGE = 56 
    CONSUME_STATE_USAGE = 57 
    REMOVE_SUMMON = 58

    COST_ANY = 60
    COST_PYRO = 61
    COST_CRYO = 62
    COST_HYDRO = 63
    COST_DENDRO = 64
    COST_GEO = 65
    COST_ANEMO = 66
    COST_ELECTRO = 67
    COST_ELEMENT = 68
    COST_ALL = 69

    APPEND_DICE = 71
    ROLL_NUM = 72
    FIXED_DICE = 73

    ADD_STATE = 74
    ADD_SUMMON = 75

    CHANGE_SKILL_DAMAGE = 80
    CHANGE_SKILL_MODIFY = 81
    CHANGE_STATE_MODIFY = 82
    MODIFY_MODIFY = 83

    CHANGE_SUMMON_ELEMENT = 101
    RANDOM = 102 

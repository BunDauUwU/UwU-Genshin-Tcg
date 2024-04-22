

import json
from typing import Union, Any, Iterator
from collections.abc import MutableMapping
from collections import Counter
import re


def read_json(file: str) -> dict[str]:
    with open(file, "r", encoding="utf-8") as f:
        text = json.load(f)
    return text


def pre_check(mode: str, characters:list, cards:list) -> Union[bool, list]:
    invalid = []
    config = read_json("config.json")
    character_dict = read_json("character.json")
    card_dict = read_json("card.json")
    game_config = config["Game"][mode]
    char_pack_limit = game_config["enable_character"]
    card_pack_limit = game_config["enable_deck"]
    each_player_config = game_config["Player"]
    enable_characters = {}
    for pack_name, pack in character_dict.items():
        if pack_name in char_pack_limit:
            enable_characters.update(pack)
    enable_cards = {}
    for pack_name, pack in card_dict.items():
        if pack_name in card_pack_limit:
            enable_cards.update(pack)
    if len(characters) != each_player_config["character_num"]:
        invalid.append("3 character cards are required")
    if len(cards) != each_player_config["deck_num"]:
        invalid.append("Wrong desk")
    if len(set(characters)) != len(characters):
        invalid.append("Same character is banned")
    character_elements = []
    for character in characters:
        if character in enable_characters:
            character_info = enable_characters[character]
            character_elements.append(character_info["element_type"])
        else:
            invalid.append("Error %s" % character)
    count_card = dict(Counter(cards))
    for card_name, count in count_card.items():
        if count > 3:
            invalid.append("Too much cards %s" % card_name)
        if card_name in enable_cards:
            card_info = enable_cards[card_name]
            if "deck_limit" in card_info:
                deck_limit = card_info["deck_limit"]
                if "character" in deck_limit:
                    if deck_limit["character"] not in characters:
                        invalid.append("Error %s" % card_name)
                else:
                    for element in ["CRYO", "HYDRO", "PYRO", "ELECTRO", "DENDRO", "ANEMO", "GEO"]:
                        if element in deck_limit:
                            if character_elements.count(element) < deck_limit[element]:
                                invalid.append("Error %s" % card_name)
        else:
            invalid.append("Error %s" % card_name)
    if invalid:
        return invalid
    return True

def update_or_append_dict(target_dict: dict, element:dict[Any, Union[int, float]]) -> None:
    for key, value in element.items():
        if key in target_dict:
            target_dict[key] += value
        else:
            target_dict.update({key: value})

def evaluate_expression(expression: str, constant_values: dict): 
    special = re.search('\{(__\w+)}', expression)
    if special:
        special_key = special.group(1)
        try:
            if "{%s}" % special_key == expression: 
                return constant_values[special_key]
            else:
                return expression.format(**constant_values)
        except KeyError as e:
            print("special_const %s" % e)
    return expression

def reverse_delete(target_list: list, index_list: Union[set, list]):
    if index_list:
        for index in sorted(index_list, reverse=True):
            target_list.pop(index)


class ModifyContainer:
    def __init__(self, init_data=None):
        if init_data is None:
            self.data = []
        elif isinstance(init_data, dict):
            self.data = list(init_data.items())
        elif isinstance(init_data, list):
            self.data = init_data
        else:
            raise ValueError("Invalid initial data")

    def __iter__(self) -> Iterator:
        for item in self.data:
            yield item[0]

    def update(self, new_data):
        if not isinstance(new_data, dict):
            raise ValueError("Invalid data type")
        self.data.extend(new_data.items())

    def modify(self, index, new_value):  # key
        if not isinstance(index, int):
            raise ValueError("Invalid index type")
        if index < 0 or index >= len(self.data):
            raise ValueError("Index out of range")
        self.data[index][1] = new_value

    def pop(self, index):
        if not isinstance(index, int):
            raise ValueError("Invalid index type")
        if index < 0 or index >= len(self.data):
            raise ValueError("Index out of range")
        del self.data[index]

    def items(self) -> Iterator:
        for item in self.data:
            yield item

    def enumerate(self):
        for index, item in enumerate(self.data):
            yield index, item[0], item[1]


class DuplicateDict(MutableMapping):  
    def __init__(self, init: list[Union[dict, tuple]]=None):
        self._key_value_list = []
        if init is not None:
            for item in init:
                if isinstance(item, dict):
                    for key, value in item.items():
                        self._key_value_list.append((key, value))
                elif isinstance(item, tuple):
                    self._key_value_list.append(item)

    def __setitem__(self, key: Any, value: Any) -> None:
        self._key_value_list.append((key, value))

    def __delitem__(self, key: Any) -> None:
        pop_index = -1
        for index, item in enumerate(self._key_value_list):
            if item[0] == key:
                pop_index = index
                break
        if pop_index != -1:
            self._key_value_list.pop(pop_index)

    def __getitem__(self, key: Any) -> Any:
        for item in self._key_value_list:
            if item[0] == key:
                return item[1]

    def __len__(self) -> int:
        return len(self._key_value_list)

    def __iter__(self) -> Iterator:
        for item in self._key_value_list:
            yield item[0]

    def __contains__(self, key: Any) -> bool:
        if self.__getitem__(key) is not None:
            return True
        else:
            return False

    def index(self, key: Any) -> int:
        key_list = [item[0] for item in self._key_value_list]
        return key_list.index(key)

    def count(self, key:Any) -> int:
        key_list = [item[0] for item in self._key_value_list]
        return key_list.count(key)

    def enumerate(self) -> Iterator:
        for index, item in enumerate(self._key_value_list):
            yield index, item[0], item[1]

    def to_list(self) -> list[tuple]:
        return self._key_value_list

    def copy(self) -> "DuplicateDict":
        return DuplicateDict(self._key_value_list)



import random


class Dice:
    def __init__(self):
        self.element = 0

    def set_element_type(self, type_):
        self.element = type_

    def roll(self):
        self.element = random.randint(0, 7)
        # self.element = 0

    def roll_base(self):
        self.element = random.randint(1, 7)
import random
import time
from player import Player
from character import Character
from card import Card
from summon import Summon
from enums import ElementType, GameStage 
from utils import read_json, evaluate_expression, reverse_delete
from typing import Union
import socket
import threading
import asyncio
from copy import deepcopy


class Game:
    def __init__(self, mode, player_socket: list, client_deck: dict):
        config = read_json("config.json")
        game_config = config["Game"][mode]
        now_time = time.time()
        self.record = open("./record/%s.txt" % time.strftime("%Y%m%d%H%M%S"), "w", encoding="utf-8")
        random.seed(now_time)
        self.record.write("seed: %s\n" % now_time)
        self.record.flush()
        self.socket = self.create_socket()
        self.client_socket = player_socket
        self.round = 0
        self.players: list[Player] = self.init_player(client_deck, game_config["enable_deck"], game_config["enable_character"], game_config["Player"])
        self.first_player: int = -1
        self.init_card_num = game_config["init_card_num"]
        self.switch_hand_times = game_config["switch_hand_times"]
        self.switch_dice_times = game_config["switch_dice_times"]
        self.max_round = game_config["max_round"]
        # self.draw_card_num = game_config["draw_card_num"]
        self.stage = GameStage.NONE
        self.state_dict = read_json("state.json")
        self.now_player = None
        self.broadcast_condition = []
        self.lock = threading.Lock()
        self.special_event = {player: [] for player in self.players}

    @staticmethod
    def create_socket():
        svr_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        svr_sock.bind(("127.0.0.1", 0))
        return svr_sock

    def send(self, data: dict, client):
        self.socket.sendto(str(data).encode(), client)

    def recv(self):
        while True:
            data, remote_addr = self.socket.recvfrom(1024)
            if data:
                data = eval(data)
                message = data["message"]
                client_index = self.client_socket.index(remote_addr)
                if message == "selected_card":
                    card_index = data["index"]
                    player = self.players[client_index]
                    self.record.write("player%s's redraw index: %s\n" % (client_index, str(card_index)))
                    player.redraw(card_index)
                    self.broadcast_condition.append({message: client_index})
                elif message == "selected_character":
                    character_index = data["character_index"]
                    player = self.players[client_index]
                    state = player.choose_character(character_index)
                    if state:
                        self.broadcast_condition.append({message: client_index})
                elif message == "need_reroll":
                    dices = data["dice_index"]
                    player = self.players[client_index]
                    self.record.write("player%s's reroll index: %s\n" % (client_index, str(dices)))
                    player.reroll(dices)
                    dices = self.get_player_dice_info(player)
                    self.record.write("player%s's dices: %s\n" % (client_index, str(dices)))
                    clear_dice_message = {"message": "clear_dice"}
                    self.send(clear_dice_message, remote_addr)
                    dice_message = {"message": "add_dice", "dices": dices}
                    self.send(dice_message, remote_addr)
                    self.record.flush()
                    self.broadcast_condition.append({message: client_index})
                elif message == "commit_cost":
                    player = self.players[client_index]
                    player.use_dices(data["cost"])
                    consume_message = {"message": "remove_dice", "dices": data["cost"]}
                    self.send(consume_message, self.client_socket[client_index])
                    dices = self.get_player_dice_info(player)
                    dice_num_message = {"message": "show_dice_num", "num": len(dices)}
                    self.send(dice_num_message, self.client_socket[client_index])
                    dice_num_message = {"message": "show_oppose_dice_num", "num": len(dices)}
                    for client in self.get_oppose_client(client_index):
                        self.send(dice_num_message, client)
                    self.broadcast_condition.append({message: client_index})
                elif message == "check_cost":
                    self.broadcast_condition.append({message: client_index, "cost": data["cost"]})
                elif message == "cancel":
                    if self.now_player == client_index:
                        self.broadcast_condition.append({"action": message})
                elif message.startswith("chose_target"):
                    self.broadcast_condition.append({message: client_index, "index": data["index"]})
                elif message == "change_character":
                    change_to = data["character"]
                    if self.now_player == client_index:
                        self.broadcast_condition.append({"action": message, "change_to": change_to})
                elif message == "play_card":
                    if self.now_player == client_index:
                        self.broadcast_condition.append(
                            {"action": message, "card_index": data["card_index"]})
                elif message == "element_tuning":
                    if self.now_player == client_index:
                        self.broadcast_condition.append(
                            {"action": message, "card_index": data["card_index"]})
                elif message == "round_end":
                    if self.now_player == client_index:
                        self.broadcast_condition.append(
                            {"action": message})
                elif message == "use_skill":
                    if self.now_player == client_index:
                        self.broadcast_condition.append(
                            {"action": message, "skill_index": data["skill_index"]})
                print("recv", data)

    @staticmethod
    def skip_list_index(target_list: list, index:int):
        return target_list[:index] + target_list[index+1:]

    def init_player(self, player_deck, card_pack, char_pack, player_config):
        players = []
        for index, ip in enumerate(self.client_socket):
            players.append(Player(player_config, card_pack, char_pack, player_deck[ip]))
        return players

    def ask_client_init_character(self):
        for index, player in enumerate(self.players):
            characters = player.characters
            self.record.write("player%d's characters: %s\n" % (index, str([character.name for character in characters])))
            for char_index, character in enumerate(characters):
                init_message = {"message": "init_character", "position": char_index, "character_name": character.name,
                                "hp": character.get_hp(), "energy": (character.get_energy(), character.max_energy)}
                self.send(init_message, self.client_socket[index])
                init_message = {"message": "init_oppo_character", "position": char_index,
                                "character_name": character.name,
                                "hp": character.get_hp(), "energy": (character.get_energy(), character.max_energy)}
                for client_socket in self.skip_list_index(self.client_socket, index):
                    self.send(init_message, client_socket)
        self.record.flush()

    def start_game(self):

        async def game_loop():
            for client in self.client_socket:
                self.send({"message":"game start"}, client)
            enable_receive = threading.Thread(target=self.recv)
            enable_receive.start()
            self.broadcast_condition.clear()
            self.ask_client_init_character()
            self.stage = GameStage.GAME_START
            await self.init_draw()
            await self.init_invoke_passive_skill()
            await self.init_choose_active()
            self.first_player = random.randint(0, len(self.players) - 1)
            self.record.write("player%d first\n" % self.first_player)
            self.record.flush()
            await self.start()

        asyncio.run(game_loop())

    async def init_draw(self):
        for index, player in enumerate(self.players):
            player.draw(self.init_card_num)
            card_info = self.get_player_hand_card_info(player)
            self.record.write("player%d's hand cards: %s\n" % (index, str(card_info)))
        self.record.flush()
        tasks = []
        for index, player in enumerate(self.players):
            tasks.append(asyncio.create_task(self.ask_client_redraw(index, player)))
        await asyncio.gather(*tasks)
        for index, player in enumerate(self.players):
            cards = self.get_player_hand_card_info(player)
            self.record.write("player%d's hand cards: %s\n" % (index, str(cards)))
            for client in self.get_oppose_client(index):
                oppo_card_num_message = {"message": "oppose_card_num", "num": len(cards)}
                self.send(oppo_card_num_message, client)
        self.record.flush()

    async def ask_client_redraw(self, index, player):
        await asyncio.sleep(0)
        for _ in range(self.switch_hand_times):
            await self.ask_player_redraw_card(index, player)
            await asyncio.sleep(0)
        cards_name, cards_cost = self.get_player_hand_card_name_and_cost(player)
        add_card_message = {"message": "add_card", "card_name": cards_name, "card_cost": cards_cost}
        self.send(add_card_message, self.client_socket[index])

    async def init_choose_active(self):
        tasks = []
        for player in self.players:
            tasks.append(asyncio.create_task(self.ask_player_choose_character(player)))
        await asyncio.gather(*tasks)
        for index, player in enumerate(self.players):
            character_index = player.current_character
            self.send_effect_message("change_active", player, None, change_from=None, change_to=character_index)
            active = player.get_active_character_obj()
            self.record.write("player%d choose active character %s\n" % (index, active.get_name()))
            await self.invoke_modify("change_to", player, active)
        self.record.flush()

    async def init_invoke_passive_skill(self):
        for player in self.players:
            self.now_player = self.players.index(player)
            characters = player.get_character()
            for character in characters:
                await self.invoke_passive_skill(player, character)

    async def invoke_passive_skill(self, player, character):
        passive_skills = character.get_passive_skill()
        for passive in passive_skills:
            await self.handle_skill(player, character, passive, skip_cost=True)

    async def start(self):
        while True:
            self.round += 1
            self.record.write("round%d start\n" % self.round)
            self.record.flush()
            self.stage = GameStage.ROUND_START
            await self.start_stage()
            self.stage = GameStage.ROLL
            await self.roll_stage()
            self.stage = GameStage.ACTION
            await self.action_stage()
            self.stage = GameStage.ROUND_END
            await self.end_stage()

    async def start_stage(self):
        self.now_player = self.first_player
        for player in self.players:
            active = player.get_active_character_obj()
            await self.invoke_modify("start", player, active)

    async def roll_stage(self):
        tasks = []
        for index, player in enumerate(self.players):
            tasks.append(asyncio.create_task(self.roll_and_reroll(index, player)))
        await asyncio.gather(*tasks)
        for index, player in enumerate(self.players):
            dices = self.get_player_dice_info(player)
            card_num_message = {"message": "show_dice_num", "num": len(dices)}
            self.send(card_num_message, self.client_socket[index])
            card_num_message = {"message": "show_oppose_dice_num", "num": len(dices)}
            for client in self.get_oppose_client(index):
                self.send(card_num_message, client)

    async def roll_and_reroll(self, index, player):
        roll_effect = await self.invoke_modify("roll", player, player.get_active_character_obj())
        if "FIXED_DICE" in roll_effect:
            player.roll(fixed_dice=roll_effect["FIXED_DICE"])
            roll_effect.pop("FIXED_DICE")
        else:
            player.roll()
        dices = self.get_player_dice_info(player)
        self.record.write("player%s's dices: %s\n" % (index, str(dices)))
        extra_switch_times = 0
        if "REROLL" in roll_effect:
            if isinstance(roll_effect["REROLL"], str):
                extra_switch_times += eval(roll_effect["REROLL"])
                roll_effect.pop("REROLL")
        await asyncio.sleep(0)
        for _ in range(self.switch_dice_times + extra_switch_times):
            await self.ask_player_reroll_dice(player)
            await asyncio.sleep(0)

    async def action_stage(self):
        for player in self.players:
            player.round_has_end = False
        self.now_player = self.first_player
        while True:
            round_has_end = True
            for player in self.players:
                if player.round_has_end:
                    continue
                else:
                    round_has_end = False
                    break
            if round_has_end:
                break
            now_player = self.players[self.now_player]
            if not now_player.round_has_end:
                active = now_player.get_active_character_obj()

                await self.invoke_modify("action", now_player, active)
                display_state, display_cost = self.update_player_display_cost(now_player)
                self.send_effect_message("change_skill_state", now_player, None, skill_state=display_state,
                                         skill_cost=display_cost)
                action_type = "combat"
                if "PREPARE" in active.state:
                    prepare_info = active.state["PREPARE"]
                    prepare_time = prepare_info["time_limit"]["PREPARE"]
                    prepare_time[0] += 1
                    if prepare_time[0] == prepare_time[1]:
                        await self.handle_skill(now_player, active, prepare_info["name"])
                        active.state.pop("PREPARE")

                else:
                    action_message = {"message": "action_phase_start"}
                    self.send(action_message, self.client_socket[self.now_player])
                    action_info = {}
                    while True:
                        for condition_index, each in enumerate(self.broadcast_condition):
                            if isinstance(each, dict):
                                if "action" in each:
                                    get = False
                                    action_info = each
                                    try:
                                        get = self.lock.acquire()
                                        self.broadcast_condition.pop(condition_index)
                                        break
                                    finally:
                                        if get:
                                            self.lock.release()
                        if action_info:
                            break
                        await asyncio.sleep(0.1)
                    if action_info["action"] == "change_character":
                        change_to = action_info["change_to"]
                        now_player = self.players[self.now_player]
                        change_from = now_player.current_character
                        change_state = await self.player_change_avatar(now_player, change_to)
                        action_type = "combat"
                        if not change_state:
                            self.send_effect_message("block_action", now_player, None)
                            continue
                        elif change_state == "fast":
                            action_type = "fast"
                        self.send_effect_message("change_active", now_player, None, change_from=change_from,
                                                 change_to=change_to)
                    elif "play_card" == action_info["action"]:
                        play_card_state = await self.play_card(self.players[self.now_player], action_info["card_index"])
                        action_type = "fast"
                        if not play_card_state:
                            self.send_effect_message("block_action", now_player, None)
                            continue
                        elif play_card_state == "combat":
                            action_type = "combat"
                    elif "element_tuning" == action_info["action"]:
                        element_tuning_state = await self.element_tuning(self.players[self.now_player],
                                                                   action_info["card_index"])
                        if not element_tuning_state:
                            self.send_effect_message("block_action", now_player, None)
                            continue
                        action_type = "fast"
                    elif "use_skill" == action_info["action"]:
                        use_state = await self.use_skill(self.players[self.now_player], action_info["skill_index"])
                        if not use_state:
                            continue
                    elif "round_end" == action_info["action"]:
                        others_had_end = False
                        now_player = self.players[self.now_player]
                        for player in self.players:
                            if player.round_has_end:
                                others_had_end = True
                                break
                        now_player.round_has_end = True
                        if not others_had_end:
                            self.first_player = self.now_player
                        self.record.write("player%d action round end\n" % self.now_player)
                        self.record.flush()
                    elif "cancel" == action_info["action"]:
                        continue
                    display_state, display_cost = self.update_player_display_cost(now_player)
                    self.send_effect_message("change_skill_state", now_player, None, skill_state=display_state, skill_cost=display_cost)
                    print(415, display_cost)
                if action_type == "fast":
                    continue
                else:
                    action_end_message = {"message": "act_end"}
                    self.send(action_end_message, self.client_socket[self.now_player])
                    self.now_player = (self.now_player + 1) % len(self.players)
            else:
                self.now_player = (self.now_player + 1) % len(self.players)

    async def end_stage(self):
        self.now_player = self.first_player
        for _ in range(len(self.players)):
            player = self.players[self.now_player]
            active = player.get_active_character_obj()
            await self.invoke_modify("end", player, active)
            player.dices.clear()
            self.send_effect_message("clear_dice", player, None)
            draw_num = player.draw(2)
            if draw_num > 0:
                cards, cards_cost = self.get_player_hand_card_name_and_cost(player)
                self.send_effect_message("add_card", player, None, card_name=cards[-draw_num:],
                                         card_cost=cards_cost[-draw_num:], card_num=len(cards))
            player.clear_character_saturation()
            self.now_player = (self.now_player + 1) % len(self.players)
        self.round_end_consume_modify()

    def get_now_player(self):
        return self.players[self.now_player]

    def get_oppose(self, index):
        return self.skip_list_index(self.players, index)

    def get_one_oppose(self, player):
        index = self.players.index(player)
        all_oppose = self.get_oppose(index)
        return all_oppose[0]

    def get_oppose_client(self, index):
        return self.skip_list_index(self.client_socket, index)

    @staticmethod
    def get_player_hand_card_info(player: Player) -> list[str]:
        hand = player.get_hand()
        card_info = []
        for card in hand:
            card_info.append(card.get_name())
        return card_info

    @staticmethod
    def get_player_hand_card_name_and_cost(player: Player) -> tuple[list[str], list[str]]:
        hand = player.get_hand()
        card_info = []
        card_cost = []
        for card in hand:
            card_info.append(card.get_name())
            card_cost.append(card.get_cost())
        return card_info, card_cost

    @staticmethod
    def get_player_character_info(player:Player) -> tuple[list[str], str]:
        character = player.get_character()
        names = []
        for c in character:
            names.append(c.name)
        active = player.get_active_character_name()
        return names, active

    @staticmethod
    def get_player_dice_info(player: Player) -> list[str]:
        dices = player.get_dice()
        dice_type = []
        for dice in dices:
            dice_type.append(ElementType(dice.element).name)
        return dice_type

    @staticmethod
    def get_player_character_detail(player: Player) -> str:
        character = player.get_character()
        detail = ""
        for c in character:
            detail += c.get_card_info()
        return detail

    async def ask_player_redraw_card(self, index, player: Player):
        cards, cards_cost = self.get_player_hand_card_name_and_cost(player)
        redraw_message = {"message": "redraw", "card_name": cards, "card_cost": cards_cost}
        self.send(redraw_message, self.client_socket[index])
        while True:
            for condition_index, each in enumerate(self.broadcast_condition):
                if isinstance(each, dict):
                    if "selected_card" in each:
                        if each["selected_card"] == index:
                            get = False
                            try:
                                get = self.lock.acquire()
                                self.broadcast_condition.pop(condition_index)
                                return
                            finally:
                                if get:
                                    self.lock.release()
            await asyncio.sleep(0.1)

    async def ask_player_choose_character(self, player: Player):
        select_message = {"message": "select_character"}
        index = self.players.index(player)
        self.send(select_message, self.client_socket[index])
        while True:
            for condition_index, each in enumerate(self.broadcast_condition):
                if isinstance(each, dict):
                    if "selected_character" in each:
                        if each["selected_character"] == index:
                            get = False
                            try:
                                get = self.lock.acquire()
                                self.broadcast_condition.pop(condition_index)
                                return
                            finally:
                                if get:
                                    self.lock.release()
            await asyncio.sleep(0.1)

    async def ask_player_reroll_dice(self, player):
        dice_type = self.get_player_dice_info(player)
        reroll_message = {"message": "reroll", "now_dice": dice_type}
        index = self.players.index(player)
        self.send(reroll_message, self.client_socket[index])
        while True:
            for condition_index, each in enumerate(self.broadcast_condition):
                if isinstance(each, dict):
                    if "need_reroll" in each:
                        if each["need_reroll"] == index:
                            get = False
                            try:
                                get = self.lock.acquire()
                                self.broadcast_condition.pop(condition_index)
                                return
                            finally:
                                if get:
                                    self.lock.release()
            await asyncio.sleep(0.1)

    async def ask_player_choose_target(self, player, target_type):
        target = "choose_target"
        choose_message = {"message": target, "target_type": target_type}
        return_target = "chose_target"
        index = self.players.index(player)
        self.send(choose_message, self.client_socket[index])
        while True:
            for condition_index, each in enumerate(self.broadcast_condition):
                if isinstance(each, dict):
                    if return_target in each:
                        if each[return_target] == index:
                            get = False
                            try:
                                get = self.lock.acquire()
                                self.broadcast_condition.pop(condition_index)
                                return each["index"]
                            finally:
                                if get:
                                    self.lock.release()
            await asyncio.sleep(0.1)

    async def element_tuning(self, player: Player, card_index):
        state = await self.action_cost(player, {"ANY": 1})
        if state:
            element = player.get_active_character_obj().element
            player.append_special_dice(element)
            self.send_effect_message("dice", player, None)
            player_index = self.players.index(player)
            card_name = player.hand_cards[card_index].get_name()
            self.record.write("player%d action element_tuning, use card %s\n" % (player_index, card_name))
            dices = self.get_player_dice_info(player)
            self.record.write("player%s's dices: %s\n" % (player_index, str(dices)))
            player.remove_hand_card(card_index)
            hand_cards_name = self.get_player_hand_card_info(player)
            self.record.write("player%s's hand cards: %s\n" % (player_index, str(hand_cards_name)))
            self.record.flush()
            self.send_effect_message("play_card", player, None)
            return True
        return False

    def preview_cost(self, operation, player, invoker: Union[Character, None], normal_cost, **kwargs):

        def get_modify(modify):
            contain_modify = []
            for each in modify:
                if "name" in each:
                    contain_modify.append(each)
                else:
                    state_name, state = next(iter(each.items()))
                    contain_modify += state["modify"]
            return contain_modify

        def preview_change(operation, player, invoker, modify, cost):
            effect = modify["effect"]
            effect_type = effect['effect_type']
            effect_value = effect["effect_value"]
            if self.is_trigger_time(operation, modify["trigger_time"]):
                if "CHANGE_COST" == effect_type:
                    if self.modify_satisfy_condition(player, invoker, modify):
                        cost_change = eval(effect_value)
                        if "ANY" in cost:
                            if cost["ANY"] > 0 or cost_change > 0:
                                cost["ANY"] += cost_change
            return cost

        def preview_skill(operation, player, invoker, modify, cost, **kwargs):
            effect = modify["effect"]
            effect_type = effect['effect_type']
            effect_value = effect["effect_value"]
            if self.is_trigger_time(operation, modify["trigger_time"]):
                if effect_type in {"COST_ANY", "COST_PYRO", "COST_HYDRO", "COST_ELECTRO", "COST_CRYO",
                                         "COST_DENDRO", "COST_ANEMO", "COST_GEO", "COST_ALL", "COST_ELEMENT"}:
                    if self.modify_satisfy_condition(player, invoker, modify, **kwargs):
                        element_type = effect_type.replace("COST_", "")
                        cost_change = eval(effect_value)
                        if element_type in ElementType.__members__:
                            if element_type in cost:
                                if cost[element_type] > 0 or cost_change > 0:
                                    cost[element_type] += cost_change
                            elif "ANY" in cost:
                                if cost["ANY"] > 0 or cost_change > 0:
                                    cost["ANY"] += cost_change
                            elif cost_change > 0:  
                                cost[element_type] = cost_change
                        elif element_type == "ANY":
                            if element_type in cost:
                                if cost[element_type] > 0 or cost_change > 0:
                                    cost[element_type] += cost_change
                            elif cost_change > 0: 
                                cost[element_type] = cost_change
                        elif element_type == "ELEMENT":
                            for element in ['CRYO', 'HYDRO', 'PYRO', 'ELECTRO', 'GEO', 'DENDRO', 'ANEMO']:
                                if element in cost:
                                    if cost[element] > 0 or cost_change > 0:
                                        cost[element] += cost_change
                                        break
                        elif element_type == "ALL":
                            if "SAME" in cost:
                                if cost["SMAE"] > 0:
                                    cost["SAME"] += cost_change
                            else:
                                for element in ['CRYO', 'HYDRO', 'PYRO', 'ELECTRO', 'GEO', 'DENDRO', 'ANEMO']:
                                    if element in cost:
                                        if cost[element] > 0 or cost_change > 0:
                                            cost[element] += cost_change
                                            break
                                    else:
                                        if "ANY" in cost:
                                            if cost["ANY"] > 0 or cost_change > 0:
                                                cost[element] += cost_change
                        else:
                            print("missing %s" % element_type)
            return cost

        def preview_invoke(operation, invoker, cost, **kwargs):
            contain_modify = get_modify(invoker.modifies)
            for modify in contain_modify:
                if operation in ["change_from", "change_to"]:
                    cost = preview_change(operation, player, invoker, modify, cost)
                else:
                    cost = preview_skill(operation, player, invoker, modify, cost, **kwargs)
            contain_modify = get_modify(player.team_modifier)
            for modify in contain_modify:
                if operation in ["change_from", "change_to"]:
                    cost = preview_change(operation, player, None, modify, cost)
                else:
                    cost = preview_skill(operation, player, None, modify, cost, **kwargs)
            for summon in player.summons:
                contain_modify = get_modify(summon.modifies)
                for modify in contain_modify:
                    if operation in ["change_from", "change_to"]:
                        cost = preview_change(operation, player, summon, modify, cost)
                    else:
                        cost = preview_skill(operation, player, summon, modify, cost, **kwargs)
            for support in player.summons:
                contain_modify = get_modify(support.modifies)
                for modify in contain_modify:
                    if operation in ["change_from", "change_to"]:
                        cost = preview_change(operation, player, support, modify, cost)
                    else:
                        cost = preview_skill(operation, player, support, modify, cost, **kwargs)
            return cost

        cost = normal_cost.copy()
        if operation == "change":
            change_from = kwargs["change_from"]
            change_to = kwargs["change_to"]
            cost = preview_invoke("change_from", change_from, cost)
            cost = preview_invoke("change_to", change_to, cost)
        elif operation == "use_skill":
            cost = preview_invoke("skill_cost", invoker, cost, **kwargs)
        elif operation == "play_card":
            cost = preview_invoke("card_cost", invoker, cost, **kwargs)
        return cost

    def modify_satisfy_condition(self, player, invoker, modify, **kwargs):
        if "time_limit" in modify:
            time_limit = modify["time_limit"]
            if "ROUND" in time_limit:
                if time_limit['ROUND'][1] <= 0:
                    return False
            elif "USAGE" in time_limit:
                if time_limit["USAGE"] <= 0:
                    return False
        print("unlimited_time")
        if self.check_condition(player, invoker, modify["condition"], **kwargs):
            return True
        return False

    async def action_cost(self, player, cost):
        dice_type = self.get_player_dice_info(player)
        cost_state = player.check_cost(cost)
        print("action_cost", cost_state)
        if cost_state:
            cost_indexes = []
            use_energy = -1
            for key, value in cost_state.items():
                if key == "ENERGY":
                    use_energy = value
                else:
                    start_index = 0
                    for _ in range(value):
                        new_index = dice_type.index(key, start_index)
                        cost_indexes.append(new_index)
                        start_index = new_index + 1
            cost_message = {"message": "highlight_dice", "dice_indexes": cost_indexes}
            player_index = self.players.index(player)
            self.send(cost_message, self.client_socket[player_index])
            while True:
                for condition_index, each in enumerate(self.broadcast_condition):
                    if isinstance(each, dict):
                        if "commit_cost" in each:
                            if each["commit_cost"] == player_index:
                                get = False
                                try:
                                    get = self.lock.acquire()
                                    self.broadcast_condition.pop(condition_index)
                                    if use_energy != -1:
                                        active = player.get_active_character_obj()
                                        active.change_energy(-use_energy)
                                        self.send_effect_message("energy", player, active)
                                    return True
                                finally:
                                    if get:
                                        self.lock.release()
                        elif "check_cost" in each:
                            if each["check_cost"] == player_index:
                                check_result = player.recheck_cost(cost, each["cost"])
                                if check_result:
                                    enable_message = {"message": "enable_commit"}
                                    self.send(enable_message, self.client_socket[player_index])
                                get = False
                                try:
                                    get = self.lock.acquire()
                                    self.broadcast_condition.pop(condition_index)
                                finally:
                                    if get:
                                        self.lock.release()
                        elif "action" in each:
                            if each["action"] == "cancel":
                                get = False
                                try:
                                    get = self.lock.acquire()
                                    self.broadcast_condition.pop(condition_index)
                                finally:
                                    if get:
                                        self.lock.release()
                                if get:
                                    return False
                await asyncio.sleep(0.1)
        elif cost_state == {}:
            player_index = self.players.index(player)
            self.send({"message": "zero_cost"}, self.client_socket[player_index])
            return True
        return False

    async def player_change_avatar(self, player: Player, character_index):
        normal_cost = {"ANY": 1}
        change_action = "combat"
        active = player.get_active_character_obj()
        new_active = character_index
        if player.check_character_alive(new_active):
            new_active_obj = player.characters[new_active]
            preview_cost = self.preview_cost("change", player, None, normal_cost, change_from=active, change_to=new_active_obj)
            cost_state = await self.action_cost(player, preview_cost)
            if cost_state:
                change_effect = await self.invoke_modify("change_from", player, active, change_cost=normal_cost, change_action=change_action)
                player.choose_character(new_active)
                change_effect = await self.invoke_modify("change_to", player, new_active_obj, change_cost=change_effect["change_cost"],
                                                   change_action=change_effect["change_action"])
                change_action = change_effect["change_action"]
                self.record.write("player%d change character from %s to %s, it's %s action\n" %
                                  (self.players.index(player), active.get_name(), new_active_obj.get_name(), change_action))
                await self.invoke_modify("after_change", player, None)
                self.record.flush()
            else:
                return False
        else:
            return False
        return change_action

    async def use_skill(self, player: Player, skill_index):
        active = player.get_active_character_obj()
        if "FROZEN" in active.state:
            return False
        skill_names = active.get_skills_name()
        skill_name = skill_names[skill_index]
        use_state = await self.handle_skill(player, active, skill_name)
        if use_state:
            return True
        else:
            return False

    async def play_card(self, player: Player, card_index):
        card = player.get_card_obj(card_index)
        card_cost = card.get_cost().copy()
        tag = card.tag
        cost = self.preview_cost("play_card", player, player.get_active_character_obj(), card_cost, card_tag=tag)
        state = player.check_cost(cost)
        if state or state == {}:
            need_fetch = card.need_fetch()
            select_const = {}
            if need_fetch:
                await self.fetch_from_client(player, need_fetch[0], select_const)
                obj = evaluate_expression(card.get_store(), select_const)
            else:
                obj = None
            if card.combat_limit:
                satisfy = self.check_condition(player, None, card.combat_limit, special_const=select_const)
                if not satisfy:
                    print("Limit exceed")
                    return False
            if "Food" in tag:
                if isinstance(obj, Character):
                    if obj.get_saturation() < player.max_character_saturation:
                        obj.change_saturation("+1")
                    else:
                        print("Full")
                        return False
                else:
                    return False
            elif "Weapon" in tag:
                if isinstance(obj, Character):
                    if obj.weapon not in tag:
                        print("Wrong weapon type", obj.weapon, "not in ", tag)
                        return False
                else:
                    print("Wrong target")
                    return False
            elif "Location" in tag or "Companion" in tag or "Item" in tag:
                if player.is_support_reach_limit():
                    index = await self.ask_player_choose_target(player, "support")
                    player.remove_support(index)
            cost_state = await self.action_cost(player, cost)
            print("cost_state", cost_state)
            if not cost_state:
                print("Point exceed")
                return False
            await self.invoke_modify("card_cost", player, player.get_active_character_obj(), card_tag=tag, cost=card_cost)
            player.remove_hand_card(card_index)
            player_index = self.players.index(player)
            self.record.write("player%d play card %s\n" % (player_index, card.get_name()))
            dices = self.get_player_dice_info(player)
            self.record.write("player%s's dices: %s\n" % (player_index, str(dices)))
            hand_cards_name = self.get_player_hand_card_info(player)
            self.record.write("player%s's hand cards: %s\n" % (player_index, str(hand_cards_name)))
            self.record.flush()
            self.send_effect_message("play_card", player, None)
            if "Weapon" in tag or "Artifact" in tag or "Talent" in tag:
                if isinstance(obj, Character):
                    equip = list(set(tag) & {"Weapon", "Artifact", "Talent"})[0].lower()
                    print(equip)
                    if obj.equipment[equip] is not None:
                        self.remove_equip(obj, obj.equipment[equip])
                    obj.equipment[equip] = card.get_name()
                    print(obj.equipment, obj.name)
                    self.add_modify(player, obj, card.modifies, store=card.get_store())
                    equipment = [type_.lower() for type_, value in obj.equipment.items() if value is not None]
                    self.send_effect_message("equip", player, obj, equip=equipment)
            elif "Location" in tag or "Companion" in tag or "Item" in tag:
                player.add_support(card)
                if card.have_counter():
                    num = card.get_count()
                    self.send_effect_message("add_support", player, card, num=num)
                elif card.have_usage():
                    num = card.usage
                    self.send_effect_message("add_support", player, card, num=num)
                else:
                    self.send_effect_message("add_support", player, card, num="")
            else:
                self.add_modify(player, obj, card.modifies, store=card.get_store())
            await self.invoke_modify("play_card", player, obj, card_tag=tag)
            if card.use_skill:
                await self.handle_skill(player, player.get_active_character_obj(), card.use_skill, skip_cost=True)
            if "Combat Action" in tag:
                return "combat"
            else:
                return True
        else:
            print("Point exceed")
            return False

    async def handle_skill(self, player, invoker, skill_name, skip_cost=False):
        skill_detail = invoker.get_skill_detail(skill_name)
        if "modify" in skill_detail:
            self.add_modify(player, invoker, skill_detail["modify"])
        skill_type = skill_detail["type"]
        skill_cost = skill_detail["cost"].copy()
        if not skip_cost:
            preview_cost = self.preview_cost("use_skill", player, invoker, skill_cost, skill_name=skill_name, skill_type=skill_type)
            state = await self.action_cost(player, preview_cost)
            if not state:
                return False
            await self.invoke_modify("before_skill_cost", player, invoker, skill_name=skill_name,
                                     skill_type=skill_type, cost=skill_cost)
            await self.invoke_modify("skill_cost", player, invoker, skill_name=skill_name,
                               skill_type=skill_type, cost=skill_cost)
        if "Normal Attack" in skill_type or "Elemental Skill" in skill_type:
            add_energy = 1
        else:
            add_energy = 0
        self.record.write("player%d's %s use skill %s\n" % (self.players.index(player), invoker.get_name(), skill_name))
        self.record.flush()
        use_skill_effect = await self.invoke_modify("use_skill", player, invoker, skill_name=skill_name, skill_type=skill_type, add_energy=add_energy)
        if "add_energy" in use_skill_effect:
            invoker.change_energy(use_skill_effect["add_energy"])
        else:
            invoker.change_energy(add_energy)
        self.send_effect_message("energy", player, invoker)
        if "damage" in skill_detail:
            await self.handle_damage(player, invoker, "team", skill_detail["damage"], skill_type=skill_type, skill_name=skill_name)
        await self.invoke_modify("after_attack", player, invoker, skill_type=skill_type, skill_name=skill_name)
        if "create" in skill_detail:
            await self.handle_state(player, invoker, skill_detail["create"])
        if "summon" in skill_detail:
            await self.handle_summon(player, skill_detail["summon"])
        await self.invoke_modify("extra_attack", player, invoker)
        return True

    async def handle_damage(self, player: Player, attacker, attackee: Union[str, Character], damage: dict[str, int], **kwargs):
        oppose: Player = self.get_one_oppose(player)
        extra_attack = []
        if attackee == "team":
            oppose_active = oppose.get_active_character_obj()
        else:
            oppose_active = attackee
        for element_type, init_damage in damage.items():
            if element_type in ElementType.__members__:
                reaction_effect = self.handle_element_reaction(player, oppose, oppose_active, element_type)
                reaction = reaction_effect["reaction"]
                for key, value in reaction_effect.items():
                    if key == element_type:
                        init_damage += eval(reaction_effect[key])
                    elif key in ["HYDRO_DMG", "GEO_DMG", "ELECTRO_DMG","DENDRO_DMG", "PYRO_DMG", "PHYSICAL_DMG",
                                "CRYO_DMG", "ANEMO_DMG", "PIERCE_DMG"]:
                        extra_attack.append({key.replace("_DMG", ""): value})
                attack_effect = await self.invoke_modify("attack", player, attacker, **kwargs, reaction=reaction, damage=init_damage, element=element_type)
                damage = attack_effect["damage"]
                attackee_effect = await self.invoke_modify("defense", oppose, oppose_active, **kwargs, reaction=reaction, hurt=damage,
                                              element=element_type)
                hurt = attackee_effect["hurt"]
                if hurt > 0:
                    oppose_state = oppose_active.change_hp(-hurt)
                    self.send_effect_message("hp", oppose, oppose_active)
                    if oppose_state == "die":
                        await self.handle_oppose_dead(oppose)
                await self.handle_element_reaction_extra_effect(player, oppose, oppose_active, reaction)
            elif element_type == "PHYSICAL":
                infusion = None
                if isinstance(attacker, Character):
                    if "INFUSION" in attacker.state:
                        state_infusion = attacker.state["INFUSION"]
                        if state_infusion:
                            infusion = state_infusion[0]["type"]
                    if infusion is None:
                        if "INFUSION" in player.team_state:
                            state_infusion = player.team_state["INFUSION"]
                            if state_infusion:
                                infusion = state_infusion[0]["type"]
                if infusion is not None:
                    await self.handle_damage(player, attacker, attackee, {infusion: init_damage}, **kwargs)
                else:
                    attack_effect = await self.invoke_modify("attack", player, attacker, **kwargs, reaction=None,
                                                  damage=init_damage, element=element_type)
                    damage = attack_effect["damage"]
                    attackee_effect = await self.invoke_modify("defense", oppose, oppose_active, **kwargs, reaction=None,
                                                    hurt=damage, element=element_type)
                    hurt = attackee_effect["hurt"]
                    if hurt > 0:
                        oppose_state = oppose_active.change_hp(-hurt)
                        self.send_effect_message("hp", oppose, oppose_active)
                        if oppose_state == "die":
                            await self.handle_oppose_dead(oppose)
            elif element_type == "PIERCE":
                if attackee == "team":
                    oppose_standby = oppose.get_standby_obj()
                else:
                    oppose_standby = [attackee]
                for obj in oppose_standby:
                    oppose_state = obj.change_hp(-init_damage)
                    self.send_effect_message("hp", oppose, obj)
                    if oppose_state == "die":
                        await self.handle_oppose_dead(oppose)
                await self.invoke_modify("pierce", player, attacker, element="PIERCE")
                await self.invoke_modify("pierce_hurt", player, None, element="PIERCE")
        if extra_attack:
            oppose_other = oppose.get_character().copy()
            oppose_other.remove(oppose_active)
            for damage in extra_attack:
                for standby in oppose_other:
                    await self.handle_damage(player, attacker, standby, damage)

    async def handle_oppose_dead(self, oppose: Player):
        end = True
        for index in range(len(oppose.get_character())):
            if oppose.check_character_alive(index):
                end = False
                break
        if end:
            self.stage = GameStage.GAME_END
            exit(0)
        else:
            change_from = oppose.get_active_character_obj()
            if not change_from.alive:
                await self.ask_player_choose_character(oppose)
            change_to = oppose.get_active_character_obj()
            if change_from != change_to:
                await self.invoke_modify("change_to", oppose, change_to)
                self.send_effect_message("change_active", oppose, None, change_from=oppose.characters.index(change_from),
                                         change_to=oppose.characters.index(change_to))
            self.special_event[oppose].append({"name": "DIE", "remove": "round_start"})

    async def handle_state(self, player, invoker: Character, combat_state):
        old_team_modifies_name = {}
        for index, old_team_modify in enumerate(player.team_modifier):
            if "name" not in old_team_modify:
                old_team_modifies_name.update({list(old_team_modify.keys())[0]: index})
        old_invoker_modifies_name = {}
        if invoker is not None:
            for index, old_invoker_modify in enumerate(invoker.modifies):
                if "modify" not in old_invoker_modify:
                    old_invoker_modifies_name.update({list(old_invoker_modify.keys())[0]: index})
        for state_name, _ in combat_state.items():
            state_info = deepcopy(self.state_dict[state_name])
            add_state_effect = await self.invoke_modify("add_state", player, invoker, state_name=state_name)
            if state_info["count"] == "time":
                num = state_info["usage"]
            else:
                num = ""
            if state_info["store"] == "SELF":
                if state_name in old_invoker_modifies_name:
                    old_state = invoker.modifies[old_invoker_modifies_name[state_name]][state_name]
                    if old_state["usage"] <= state_info["usage"]:
                        old_state["usage"] = state_info["usage"]
                        self.send_effect_message("change_state_usage", player, invoker, state_name=state_name,
                                                 type="self", num=old_state["usage"])
                    old_state["modify"] = state_info["modify"]
                else:
                    invoker.modifies.append({state_name: state_info})
                    self.send_effect_message("add_state", player, invoker, state_name=state_name, num=num,
                                             type="self", state_icon=state_info["icon"], store=player.characters.index(invoker))
            elif state_info["store"] == "TEAM":
                if state_name in old_team_modifies_name:
                    old_state = player.team_modifier[old_team_modifies_name[state_name]][state_name]
                    if old_state["usage"] <= state_info["usage"]:
                        old_state["usage"] = state_info["usage"]
                        self.send_effect_message("change_state_usage", player, invoker, state_name=state_name,
                                                 type="team", num=old_state["usage"])
                    old_state["modify"] = state_info["modify"]
                else:
                    player.team_modifier.append({state_name: state_info})
                    self.send_effect_message("add_state", player, invoker, state_name=state_name, num=num,
                                             type="team", state_icon=state_info["icon"], store=player.current_character)

    async def handle_summon(self, player: Player, summon_dict: dict):
        for summon_name, num in summon_dict.items():
            for _ in range(num):
                add_state = player.add_summon(summon_name)
                if add_state == "add":
                    summon_obj = player.summons[-1]
                    self.send_effect_message("add_summon", player, summon_obj)
                elif add_state == "cancel":
                    pass
                else:
                    if isinstance(add_state, int):
                        summon_obj = player.summons[add_state]
                        self.send_effect_message("change_summon_usage", player, summon_obj, index=add_state)

    def handle_element_reaction(self, player, trigger_on_player, trigger_obj: Character, element):
        trigger_obj.application.append(ElementType[element])
        applied_element = set(trigger_obj.application)
        return_effect = {}
        if {ElementType.CRYO, ElementType.PYRO}.issubset(applied_element):
            applied_element.remove(ElementType.CRYO)
            applied_element.remove(ElementType.PYRO)
            return_effect = {"CRYO": "+2", "PYRO": "+2", "reaction": "MELT"}
        elif {ElementType.HYDRO, ElementType.PYRO}.issubset(applied_element):
            applied_element.remove(ElementType.PYRO)
            applied_element.remove(ElementType.HYDRO)
            return_effect = {"HYDRO": "+2", "PYRO": "+2", "reaction": "VAPORIZE"}
        elif {ElementType.ELECTRO, ElementType.PYRO}.issubset(applied_element):
            applied_element.remove(ElementType.ELECTRO)
            applied_element.remove(ElementType.PYRO)
            return_effect = {"ELECTRO": "+2", "PYRO": "+2", "reaction": "OVERLOADED"}
        elif {ElementType.HYDRO, ElementType.CRYO}.issubset(applied_element):
            applied_element.remove(ElementType.HYDRO)
            applied_element.remove(ElementType.CRYO)
            return_effect = {"HYDRO": "+1", "CRYO": "+1", "reaction": "FROZEN"}
        elif {ElementType.ELECTRO, ElementType.CRYO}.issubset(applied_element):
            applied_element.remove(ElementType.CRYO)
            applied_element.remove(ElementType.ELECTRO)
            return_effect = {"ELECTRO": "+1", "CRYO": "+1", "PIERCE_DMG": 1, "reaction": "SUPER_CONDUCT"}
        elif {ElementType.ELECTRO, ElementType.HYDRO}.issubset(applied_element):
            applied_element.remove(ElementType.ELECTRO)
            applied_element.remove(ElementType.HYDRO)
            return_effect = {"ELECTRO": "+1", "HYDRO": "+1", "PIERCE_DMG": 1, "reaction": "ELECTRO_CHARGE"}
        elif {ElementType.DENDRO, ElementType.PYRO}.issubset(applied_element):
            applied_element.remove(ElementType.DENDRO)
            applied_element.remove(ElementType.PYRO)
            return_effect = {"DENDRO": "+1", "PYRO": "+1", "reaction": "BURNING"}
        elif {ElementType.DENDRO, ElementType.HYDRO}.issubset(applied_element):
            applied_element.remove(ElementType.DENDRO)
            applied_element.remove(ElementType.HYDRO)
            return_effect = {"DENDRO": "+1", "HYDRO": "+1", "reaction": "BLOOM"}
        elif {ElementType.DENDRO, ElementType.ELECTRO}.issubset(applied_element):
            applied_element.remove(ElementType.DENDRO)
            applied_element.remove(ElementType.ELECTRO)
            return_effect = {"DENDRO": "+1", "ELECTRO": "+1", "reaction": "CATALYZE"}
        elif ElementType.ANEMO in applied_element :
            applied_element.remove(ElementType.ANEMO)
            if(len(applied_element) < 2):
                return_effect = {"reaction": None}
            else:
                elements = list(applied_element)
                for element in elements:
                    if element != ElementType.DENDRO and element != ElementType.GEO and element != ElementType.NONE:
                        applied_element.remove(element)
                        return_effect = {element.name + "_DMG": 1, "reaction": "SWIRL", "swirl_element": element.name}
                        break
        elif ElementType.GEO in applied_element:
            if(len(applied_element) < 2):
                return_effect = {"reaction": None}
            else:
                applied_element.remove(ElementType.GEO)
                elements = list(applied_element)
                for element in elements:
                    if element != ElementType.DENDRO and element != ElementType.ANEMO and element != ElementType.NONE:
                        applied_element.remove(element)
                        return_effect = {"GEO": "+1", "reaction": "CRYSTALLIZE", "crystallize_element": element.name}
                        break
        else:
            return_effect = {"reaction": None}
        trigger_obj.application = list(applied_element)
        self.send_effect_message("application", trigger_on_player, trigger_obj)
        return return_effect
        
    async def handle_element_reaction_extra_effect(self, player, trigger_on_player, trigger_obj: Character, reaction):
        if reaction == "FROZEN":
            await self.handle_state(trigger_on_player, trigger_obj, {"Frozen": 1})
        elif reaction == "OVERLOADED":
            await self.handle_state(trigger_on_player, trigger_obj, {"Overloaded": 1})
        elif reaction == "BURNING":
            await self.handle_summon(player, {"Burning Flame": 1})
        elif reaction == "BLOOM":
            await self.handle_state(player, player.get_active_character_obj(), {"Dendro Core": 1})
        elif reaction == "CATALYZE":
            await self.handle_state(player, player.get_active_character_obj(), {"Catalyzing Field": 1})
        elif reaction == "CRYSTALLIZE":
            await self.handle_state(player, player.get_active_character_obj(), {"Crystallize": 1})

    def update_player_display_cost(self, player: Player):
        active = player.get_active_character_obj()
        skills_name, skills_cost = active.get_skill_name_and_cost()
        skills_type = active.get_skills_type()
        display_skill_cost = []
        skill_state = []
        if "FROZEN" in active.state:
            skill_state = [False] * len(skills_name)
            for skill_name, skill_cost, skill_type in zip(skills_name, skills_cost, skills_type):
                new_cost = self.preview_cost("use_skill", player, active, skill_cost, skill_name=skill_name, skill_type=skill_type)
                if new_cost == {}:
                    display_skill_cost.append({"ANY": 0})
                else:
                    display_skill_cost.append(new_cost)
        else:
            for skill_name, skill_cost, skill_type in zip(skills_name, skills_cost, skills_type):
                new_cost = self.preview_cost("use_skill", player, active, skill_cost, skill_name=skill_name, skill_type=skill_type)
                if new_cost == {}:
                    skill_state.append(True)
                    display_skill_cost.append({"ANY": 0})
                else:
                    display_skill_cost.append(new_cost)
                    cost_state = player.check_cost(new_cost)
                    if cost_state:
                        skill_state.append(True)
                    else:
                        skill_state.append(False)
        return skill_state, display_skill_cost

    @staticmethod
    def add_modify(player, invoker: Union[Character, Summon, Card, None], modifies:list, store=None):
        old_team_modifies_name = {}
        team_need_del_index = []
        for index, old_team_modify in enumerate(player.team_modifier):
            if "name" in old_team_modify:  
                old_team_modifies_name.update({old_team_modify["name"]: index})
        old_invoker_modifies_name = {}
        invoker_need_del_index = []
        if invoker is not None:
            for index, old_invoker_modify in enumerate(invoker.modifies):
                if "name" in old_invoker_modify:
                    old_invoker_modifies_name.update({old_invoker_modify["name"]: index})
        for modify in modifies:
            modify_name = modify["name"]
            if store is None:
                if "store" in modify:
                    store = modify["store"]
                else:
                    print("%sModify" % modify_name)
                    continue
            if store == "SELF" or store == "{__select}":
                if invoker is not None:
                    if modify_name in old_invoker_modifies_name:
                        invoker_need_del_index.append(old_invoker_modifies_name[modify_name])
                    invoker.modifies.append(modify)
                else:
                    print("%s存在潜在错误" % modify_name)
            elif store == "TEAM" or store == "player":
                if modify_name in old_team_modifies_name:
                    team_need_del_index.append(old_team_modifies_name[modify_name])
                player.team_modifier.append(modify)
        sort_team_del_index = sorted(team_need_del_index, reverse=True)
        sort_invoker_del_index = sorted(invoker_need_del_index, reverse=True)
        for index in sort_team_del_index:
            player.team_modifier.pop(index)
        for index in sort_invoker_del_index:
            invoker.modifies.pop(index)

    async def invoke_modify(self, operation:str, player, invoker: Union[Character, None], oppose_invoker: Union[Character, None]=None, **kwargs):
        only_invoker = False
        if operation in ["init_draw", "start", "roll", "action", "end", "duration", "add_state", "invoke_state", "remove_state"]:
            invoke_invoker = True
            invoke_beside_invoker = True
            invoker_oppose = False
        elif operation in ["before_skill_cost", "skill_cost", "use_skill", "attack", "defense", "pierce", "pierce_hurt",
                           "change_from", "change_to", "card_cost"]:
            invoke_invoker = True
            invoke_beside_invoker = False
            invoker_oppose = False
        elif operation in ["after_attack", "change_hp"]:
            invoke_invoker = True
            invoke_beside_invoker = True
            invoker_oppose = True
        elif operation in ["play_card", "draw", "after_change"]:
            invoke_invoker = False
            invoke_beside_invoker = False
            invoker_oppose = False
        elif operation in ["extra_attack"]:
            invoke_invoker = True
            invoke_beside_invoker = False
            invoker_oppose = True
        elif operation in ["trigger"]:
            invoke_invoker = True
            invoke_beside_invoker = False
            invoker_oppose = False
            only_invoker = True
        else:
            print("trigger time %s" % operation)
            return {}
        print(operation, kwargs)
        if "from_oppose" in kwargs:
            print("invoke_oppose")
            invoker_oppose = False
        return_effect = {}
        if invoker is not None and invoke_invoker:
            print("invoker_pre_modify", invoker.modifies)
            kwargs, _ = await self.process_modify(operation, player, invoker, invoker, invoker.modifies, return_effect, **kwargs)
            print("invoker_after_modify", invoker.modifies)
        if not only_invoker:
            if invoker is not None and invoke_beside_invoker:
                for character in player.get_no_self_obj(invoker):
                    print("%s_pre_modify" % character.get_name(), character.modifies)
                    kwargs, _ = await self.process_modify(operation, player, invoker, character, character.modifies,
                                                       return_effect, **kwargs)
                    print("%s_after_modify" % character.get_name(), character.modifies)
            print("team_pre_modify", player.team_modifier)
            kwargs, _ = await self.process_modify(operation, player, invoker, None, player.team_modifier,
                                               return_effect, **kwargs)
            print("team_after_modify", player.team_modifier)
            need_remove_summon = set()
            for index, summon in enumerate(player.summons):
                print("%s_pre_modify" % summon.get_name(), summon.modifies)
                kwargs, need_remove = await self.process_modify(operation, player, invoker, summon, summon.modifies,
                                                   return_effect, **kwargs)
                if need_remove:
                    need_remove_summon.add(index)
                print("%s_after_modify" % summon.get_name(), summon.modifies)
            if need_remove_summon:
                for index in sorted(need_remove_summon, reverse=True):
                    player.summons.pop(index)
                    self.send_effect_message("remove_summon", player, None, index=index)
            need_remove_support = set()
            for index, support in enumerate(player.supports):
                print("%s_pre_modify" % support.get_name(), support.modifies)
                kwargs, need_remove = await self.process_modify(operation, player, invoker, support, support.modifies,
                                                   return_effect, **kwargs)
                if need_remove:
                    need_remove_support.add(index)
                print("%s_after_modify" % support.get_name(), support.modifies)
            if need_remove_support:
                for index in sorted(need_remove_support, reverse=True):
                    player.supports.pop(index)
                    self.send_effect_message("remove_support", player, None, index=index)
            if "from_oppose" in kwargs:
                kwargs.pop("from_oppose")
            if invoker_oppose:
                oppose = self.get_one_oppose(player)
                await self.invoke_modify(operation, oppose, oppose_invoker, from_oppose=True, **kwargs)
        self.record.flush()
        if "cost" in kwargs:
            return_effect["cost"] = kwargs["cost"]
        if "damage" in kwargs:
            if "damage_multiple" in return_effect:
                kwargs["damage"] = eval(str(kwargs["damage"]) + return_effect["damage_multiple"])
            return_effect["damage"] = -(-kwargs["damage"] // 1)  # ceil
        if "hurt" in kwargs:
            kwargs["hurt"] = max(kwargs["hurt"], 0)
            if "hurt_multiple" in return_effect:
                kwargs["hurt"] = eval(str(kwargs["hurt"]) + return_effect["hurt_multiple"])
            return_effect["hurt"] = -(-kwargs["hurt"] // 1)  # ceil
        if "change_cost" in kwargs:
            return_effect["change_cost"] = kwargs["change_cost"]
        if "change_action" in kwargs:
            return_effect["change_action"] = kwargs["change_action"]
        print(1338, "invoke_modify", return_effect)
        return return_effect

    async def process_modify(self, operation:str, player: Player, from_object: Character,
                             invoker: Union[Summon, Card, Character, None], modifies: list, return_effect, **kwargs):
        need_remove = set()
        remove_invoker = False
        for index, modify in enumerate(modifies):
            is_state = False
            state_name, state = "", {}
            # modify{state_name:{modify:[], ...}}
            if "name" in modify:
                contain_modify = [modify]
            else:
                state_name, state = next(iter(modify.items()))
                contain_modify = state["modify"]
                is_state = True
            consume_usage = 0
            need_del_modify = set()
            for modify_index, each_modify in enumerate(contain_modify):
                print("processing modify", each_modify)
                if "from" in each_modify:
                    from_limit = each_modify["from"]
                    if from_limit == "SELF":
                        if from_object != invoker:
                            continue
                    elif from_limit == "NO_SELF":
                        if from_object == invoker or "from_oppose" in kwargs:
                            continue
                    elif from_limit == "TEAM":
                        if "from_oppose" in kwargs:
                            continue
                    elif from_limit == "OPPOSE":
                        if "from_oppose" not in kwargs:
                            continue
                    elif from_limit == "BOTH":
                        pass
                    else:
                        print("from_limit")
                        continue
                print("valid source")
                trigger_time = each_modify["trigger_time"]
                special_const = {}
                if "special_const" in state:
                    special_const = state["special_const"]
                if self.is_trigger_time(operation, trigger_time):
                    print("is_trigger_time")
                    if "fetch" in each_modify:
                        for need_fetch in each_modify["fetch"]:
                            await self.fetch_from_client(player, need_fetch, special_const)
                    if "get" in each_modify:
                        get_success = True
                        for need_get in each_modify["get"]:
                            get_result = self.get_from_player(player, invoker, need_get, special_const, **kwargs)
                            if not get_result:
                                get_success = False
                                break
                        if not get_success:
                            print("get_failure")
                            continue
                    kwargs["special_const"] = special_const
                    if self.modify_satisfy_condition(player, invoker, each_modify, **kwargs):
                        print("satisfy")
                        effect_obj = each_modify["effect_obj"]
                        effect = each_modify["effect"]
                        if isinstance(effect_obj, str):
                            effect_obj = evaluate_expression(effect_obj, special_const)
                        kwargs, consume = await self.handle_effect(player, invoker, effect, effect_obj, return_effect,
                                                                   **kwargs)
                        if consume:
                            self.record.write("trigger %s, effect is %s\n" % (each_modify["name"], str(each_modify["effect"])))
                        if "consume" in each_modify:
                            need_consume_times = each_modify["consume"]
                            if consume or "immediate" in each_modify:
                                if is_state or isinstance(invoker, (Card, Summon)):
                                    if isinstance(need_consume_times, str):
                                        consume_usage = need_consume_times
                                    else:
                                        consume_usage += need_consume_times
                                    print("change_consume_state", consume_usage)
                                else:
                                    if "usage" in each_modify:
                                        each_modify["usage"] -= need_consume_times
                                        if each_modify["usage"] <= 0:
                                            need_remove.add(index)
                                    elif isinstance(invoker, (Card, Summon)):
                                        invoke_state = invoker.consume_usage(need_consume_times)
                                        if invoke_state == "remove":
                                            if isinstance(invoker, Card):
                                                player.supports.remove(invoker)
                                            else:
                                                player.summons.remove(invoker)
                        if "time_limit" in each_modify:
                            consume_status = self.consume_modify_usage(each_modify)
                            if consume_status == "remove":
                                need_remove.add(index)
                    if "immediate" in each_modify:
                        if is_state:
                            need_del_modify.add(modify_index)
                        else:
                            need_remove.add(index)
                if "special_const" in kwargs:
                    kwargs.pop("special_const")
            for need_del_modify_index in sorted(need_del_modify, reverse=True):
                modify["modify"].pop(need_del_modify_index)
            if consume_usage:
                if "usage" in state:
                    state["usage"] -= consume_usage
                    if state["usage"] <= 0:
                        need_remove.add(index)
                        if isinstance(invoker, Character):
                            self.send_effect_message("remove_state", player, invoker, state_name=state_name,
                                                     type="self")
                        elif invoker is None:
                            self.send_effect_message("remove_state", player, invoker, state_name=state_name,
                                                     type="team")
                    else:
                        if isinstance(invoker, Character):
                            self.send_effect_message("change_state_usage", player, invoker, state_name=state_name,
                                                     type="self", num=state["usage"])
                        elif invoker is None:
                            self.send_effect_message("change_state_usage", player, invoker, state_name=state_name,
                                                     type="team", num=state["usage"])
                elif isinstance(invoker, Summon):
                    consume_state = invoker.consume_usage(consume_usage)
                    if consume_state == "remove":
                        remove_invoker = True
                    else:
                        summon_index = player.summons.index(invoker)
                        self.send_effect_message("change_summon_usage", player, invoker, index=summon_index)
                elif isinstance(invoker, Card):
                    consume_state = invoker.consume_usage(consume_usage)
                    if consume_state == "remove":
                        remove_invoker = True
                    else:
                        support_index = player.supports.index(invoker)
                        self.send_effect_message("change_support_usage", player, invoker, index=support_index)
                else:
                    print("consume usage", modify)
        reverse_delete(modifies, need_remove)
        return kwargs, remove_invoker


    async def fetch_from_client(self, player, fetch_logic, special_const):
        if fetch_logic["logic"] == "fetch":
            if fetch_logic["what"] == "select":
                fetch_type = fetch_logic["type"]
                index = await self.ask_player_choose_target(player, fetch_type)
                if fetch_type == "character":
                    obj = player.characters[index]
                elif fetch_type == "summon":
                    obj = player.summons[index]
                elif fetch_type == "oppose_summon":
                    oppose = self.get_one_oppose(player)
                    obj = oppose.summons[index]
                else:
                    print("fetch type %s" % fetch_type)
                    return None
                special_const[fetch_logic["export"]] = obj
                return True

    @staticmethod
    def get_from_player(player, invoker, get_logic, special_const, **kwargs):
        logic = get_logic["logic"]
        if logic == "get":

            if "what" in get_logic:
                what = get_logic["what"]
            if "where" in get_logic:
                where = get_logic["where"]
            else:
                where = "summon"
            if "whose" in get_logic:
                whose = get_logic["whose"]

            if what == "element":
                if where == "summon":
                    summon = player.get_summon_by_name(whose)
                    if summon is None:
                        return False
                    special_const[get_logic["export"]] = summon.element
                elif where == "team":
                    if whose == "active":
                        special_const[get_logic["export"]] = player.get_active_character_obj().element
                elif where == "swirl":
                    if "swirl_element" in kwargs:
                        special_const[get_logic["export"]] = kwargs["swirl_element"]
                    else:
                        return False
            elif what == "summon":
                if where == "team":
                    summon = player.get_summon_by_name(whose)
                    if summon is None:
                        return False
                    special_const[get_logic["export"]] = summon
            elif what == "object":
                if where == "standby":
                    if whose == "most_hurt":
                        obj = player.get_most_hurt_standby()
                        if obj:
                            special_const[get_logic["export"]] = obj
                        else:
                            return False
            elif what == "skill":
                if whose == "name":
                    if "skill_name" in kwargs:
                        special_const[get_logic["export"]] = kwargs["skill_name"]
                    else:
                        return False
            elif what == "weapon":
                where = evaluate_expression(where, special_const)
                if isinstance(where, Character):
                    if whose == "type":
                        special_const[get_logic["export"]] = where.weapon
                    elif whose == "name":
                        special_const[get_logic["export"]] = where.equipment["weapon"]
                    else:
                        return False
                else:
                    return False
            elif what == "artifact":
                where = evaluate_expression(where, special_const)
                if isinstance(where, Character):
                    if whose == "name":
                        special_const[get_logic["export"]] = where.equipment["artifact"]
                    else:
                        return False
                else:
                    return False
        elif logic == "sum":
            what = get_logic["what"]
            type_ = get_logic["type"]
            export = get_logic["export"]
            if what == "summon":
                summons = player.summons
                if type_ == "num":
                    special_const[export] = len(summons)
            elif what == "counter":
                if type_ in invoker.counter:
                    special_const[export] = invoker.counter[type_]
                else:
                    return False
            elif what == "nation":
                nation = player.get_character_nation()
                special_const[export] = nation.count(type_)
            elif what == "card":
                if type_ == "cost":
                    if "cost" in kwargs:
                        cost = 0
                        for value in kwargs["cost"].values():
                            cost += value
                        special_const[export] = cost
            elif what == "dice":
                if type_ == "type":
                    dices = player.dices
                    num = dices.count(0)
                    count_dices = list(set(dices))
                    if(num != 0):
                        count_dices.remove(0)
                    num += len(count_dices)
                    special_const[export] = num

    async def handle_effect(self, player, invoker, effect, effect_obj, return_effect, **kwargs):
        consume = False
        if not effect:
            return kwargs, True
        print(1460, "handle_effect", effect, kwargs)
        special_const = kwargs["special_const"] if "special_const" in kwargs else {}
        effect_type = effect["effect_type"]
        effect_value = effect["effect_value"]
        player_index = self.players.index(player)
        if isinstance(effect_type, str):
            effect_type = evaluate_expression(effect_type, special_const)
        if isinstance(effect_value, str):
            effect_value = evaluate_expression(effect_value, special_const)
        if effect_obj == "COUNTER":
            if isinstance(invoker, (Character, Card, Summon)):
                if effect_type in invoker.counter:
                    from_counter_value = invoker.counter[effect_type]
                    invoker_name = invoker.get_name()
                    if isinstance(effect_value, str):
                        invoker.counter[effect_type] += eval(effect_value)
                    else:
                        invoker.counter[effect_type] = effect_value
                    to_counter_value = invoker.counter[effect_type]
                    self.record.write("player%d's %s counter %s change from %s to %s" % (player_index, invoker_name,
                                                                                         effect_type, from_counter_value
                                                                                         , to_counter_value))
                    if isinstance(invoker, Card):
                        self.send_effect_message("change_support_usage", player, invoker)
                    consume |= True
                else:
                    print("Error：unknown counter name %s" % effect_type)
        else:
            if effect_type == "REROLL":
                if isinstance(effect_value, str):
                    return_effect.setdefault("REROLL", 0)
                    return_effect["REROLL"] += eval(effect_value)
                    consume |= True
                elif isinstance(effect_value, int):
                    for _ in range(effect_value):
                        await self.ask_player_reroll_dice(player)
                    consume |= True
                else:
                    print("ReRoll %s" % effect_value)
            elif effect_type == "FIXED_DICE":
                return_effect.setdefault("FIXED_DICE", [])
                for element in effect_value:
                    return_effect["FIXED_DICE"].append(evaluate_expression(element, special_const))
                consume |= True
            elif effect_type == "USE_SKILL":
                if effect_obj == "SELF" and isinstance(invoker, Character):
                    await self.handle_skill(player, invoker, effect_value, skip_cost=True)
                    consume |= True
            elif effect_type == "CHANGE_COST":
                if "change_cost" in kwargs:
                    print(kwargs)
                    cost = kwargs['change_cost']
                    cost_change = eval(effect_value)
                    if "ANY" in cost:
                        if cost["ANY"] > 0 or cost_change > 0:
                            cost["ANY"] += cost_change
                            consume |= True
            elif effect_type == "CHANGE_ACTION":
                if "change_action" in kwargs:
                    if kwargs["change_action"] != effect_value:
                        kwargs["change_action"] = effect_value
                        consume |= True
            elif effect_type == "SKILL_ADD_ENERGY":
                if "add_energy" in kwargs:
                    kwargs["add_energy"] = kwargs["add_energy"]
                    consume |= True
            elif effect_type in {"COST_ANY", "COST_PYRO", "COST_HYDRO", "COST_ELECTRO", "COST_CRYO",
                                              "COST_DENDRO", "COST_ANEMO", "COST_GEO", "COST_ALL", "COST_ELEMENT"}:
                if "cost" in kwargs:
                    cost: dict = kwargs["cost"]
                    element_type = effect_type.replace("COST_", "")
                    cost_change = eval(effect_value)
                    if element_type in ElementType.__members__:
                        if element_type in cost:
                            if cost[element_type] > 0 or cost_change > 0:
                                cost[element_type] += cost_change
                                consume |= True
                        elif "ANY" in cost:
                            if cost["ANY"] > 0 or cost_change > 0:
                                cost["ANY"] += cost_change
                                consume |= True
                        elif cost_change > 0:  
                            cost[element_type] = cost_change
                            consume |= True
                    elif element_type == "ANY":
                        if element_type in cost:
                            if cost[element_type] > 0 or cost_change > 0:
                                cost[element_type] += cost_change
                                consume |= True
                        elif cost_change > 0:  
                            cost[element_type] = cost_change
                            consume |= True
                    elif element_type == "ELEMENT":
                        for element in ['CRYO', 'HYDRO', 'PYRO', 'ELECTRO', 'GEO', 'DENDRO', 'ANEMO']:
                            if element in cost:
                                if cost[element] > 0 or cost_change > 0:
                                    cost[element] += cost_change
                                    consume |= True
                                    break
                    elif element_type == "ALL":
                        if "SAME" in cost:
                            if cost["SMAE"] > 0:
                                cost["SAME"] += cost_change
                                consume |= True
                        else:
                            cost_change_by_all = False
                            for element in ['CRYO', 'HYDRO', 'PYRO', 'ELECTRO', 'GEO', 'DENDRO', 'ANEMO']:
                                if element in cost:
                                    if cost[element] > 0 or cost_change > 0:
                                        cost[element] += cost_change
                                        cost_change_by_all = True
                                        break
                            if cost_change_by_all:
                                consume |= True
                            else:
                                if "ANY" in cost:
                                    if cost["ANY"] > 0 or cost_change > 0:
                                        cost[element] += cost_change
                                        consume |= True
                    else:
                        print("Wrong Element %s" % element_type)
            elif effect_type == "DMG":
                if "damage" in kwargs:
                    if effect_value.startswith("*") or effect_value.startswith("/"):
                        return_effect["damage_multiple"] = effect_value
                    else:
                        kwargs["damage"] += eval(effect_value)
                    consume |= True
            elif effect_type == "HURT":
                if "hurt" in kwargs:
                    if effect_value.startswith("*") or effect_value.startswith("/"):
                        return_effect["hurt_multiple"] = effect_value
                        consume |= True
                    else:
                        hurt_change = eval(effect_value)
                        if kwargs["hurt"] > 0 or hurt_change > 0:
                            kwargs["hurt"] += eval(effect_value)
                            kwargs["hurt"] = max(kwargs["hurt"], 0)
                            consume |= True
            elif effect_type == "SHIELD":
                if "hurt" in kwargs:
                    if kwargs["hurt"] > 0:
                        kwargs["hurt"] -= effect_value
                        consume |= True
            elif effect_type == "INFUSION":
                if effect_obj == "SELF":
                    if isinstance(invoker, Character):
                        invoker.state.setdefault("INFUSION", []).append(effect_value)
                elif effect_obj == "TEAM" or effect_obj == "ACTIVE":
                    player.team_state.setdefault("INFUSION", []).append(effect_value)
                else:
                    print("Error：infusion %s" % effect_obj)
                consume |= True
            elif effect_type == "ADD_MODIFY":
                if effect_obj in ["SELF", "TEAM"]:
                    self.add_modify(player, invoker, effect["ADD_MODIFY"], store=effect_obj)
                elif effect_obj in ["STATE"]:
                    return_effect.setdefault("add_modify", []).append(effect_value)
                else:
                    print("Error：add_modify %s" % effect_obj)
                consume |= True
            elif effect_type in {"HYDRO_DMG", "GEO_DMG", "ELECTRO_DMG","DENDRO_DMG", "PYRO_DMG", "PHYSICAL_DMG",
                                    "CRYO_DMG", "ANEMO_DMG", "PIERCE_DMG"}:
                element_type = effect_type.replace("_DMG", "")
                if effect_obj == "OPPOSE_ALL":
                    oppose: Player = self.get_one_oppose(player)
                    for character in oppose.characters:
                        await self.handle_damage(player, None, character, {element_type: effect_value})
                elif effect_obj == "OPPOSE":
                    await self.handle_damage(player, None, "team", {element_type: effect_value})
                elif effect_obj == "SELF":
                    # TODO 
                    await self.handle_damage(player, None, invoker, {element_type: effect_value})
                else:
                    print("Error： %s" % effect_obj)
                consume |= True
            elif effect_type == "DRAW_CARD":
                if isinstance(effect_value, int):
                    draw_num = player.draw(effect_value)
                    if draw_num > 0:
                        cards_name, cards_cost = self.get_player_hand_card_name_and_cost(player)
                        self.send_effect_message("add_card", player, invoker, card_name=cards_name[-draw_num:],
                                                 card_cost=cards_cost[-draw_num:], card_num=len(cards_name))
                elif isinstance(effect_value, str):
                    if effect_value.startswith("TYPE_"):
                        card_type = effect_value.replace("TYPE_", "")
                        draw_num = player.draw_type(card_type)
                        if draw_num > 0:
                            cards_name, cards_cost = self.get_player_hand_card_name_and_cost(player)
                            self.send_effect_message("add_card", player, invoker, card_name=cards_name[-draw_num:],
                                                     card_cost=cards_cost[-draw_num:], card_num=len(cards_name))
                    else:
                        print("Error：card type %s" % effect_value)
                else:
                    print("Error：draw card %s" % str(effect_value))
                consume |= True
            elif effect_type == "ADD_CARD":
                add_state = player.append_hand_card(effect_value)
                if add_state:
                    cards_name, cards_cost = self.get_player_hand_card_name_and_cost(player)
                    self.send_effect_message("add_card", player, invoker, card_name=cards_name[-1:],
                                             card_cost=cards_cost[-1:], card_num=len(cards_name))
                consume |= True
            elif effect_type == "APPEND_DICE":
                if isinstance(effect_value, list):
                    for dice in effect_value:
                        dice = evaluate_expression(dice, special_const)
                        if dice == "RANDOM":
                            player.append_random_dice()
                        elif dice == "BASE":
                            player.append_base_dice()
                        else:
                            player.append_special_dice(dice)
                    self.send_effect_message("dice", player, None)
                else:
                    if effect_value == "RANDOM":
                        player.append_random_dice()
                    elif effect_value == "BASE":
                        player.append_base_dice()
                    else:
                        player.append_special_dice(effect_value)
                    self.send_effect_message("dice", player, None)
                consume |= True
            elif effect_type == "CHANGE_CHARACTER":
                if effect_obj == "OPPOSE":
                    oppose  = self.get_one_oppose(player)
                    change_from_index = oppose.current_character
                    change_from = oppose.get_active_character_obj()
                    change_to_index = oppose.auto_change_active(effect_value)
                    if change_from_index != change_to_index:
                        await self.invoke_modify("change_from", oppose, change_from)
                        oppose.choose_character(change_to_index)
                        change_to = oppose.get_active_character_obj()
                        await self.invoke_modify("change_to", oppose, change_to)
                        self.send_effect_message("change_active", oppose, None,
                                                 change_from=oppose.characters.index(change_from),
                                                 change_to=oppose.characters.index(change_to))
                        await self.invoke_modify("after_change", oppose, None)
                elif effect_obj == "ALL":
                    change_from_index = player.current_character
                    change_from = player.get_active_character_obj()
                    change_to_index = player.auto_change_active(effect_value)
                    if change_from_index != change_to_index:
                        await self.invoke_modify("change_from", player, change_from)
                        player.choose_character(change_to_index)
                        change_to = player.get_active_character_obj()
                        await self.invoke_modify("change_to", player, change_to)
                        self.send_effect_message("change_active", player, None,
                                                 change_from=player.characters.index(change_from),
                                                 change_to=player.characters.index(change_to))
                        await self.invoke_modify("after_change", player, None)
                else:
                    print("Error：change character %s" % effect_obj)
                consume |= True
            elif effect_type == "HEAL":
                if effect_obj == "ACTIVE":
                    active = player.get_active_character_obj()
                    active.change_hp(effect_value)
                    self.send_effect_message("hp", player, active)
                elif effect_obj == "STANDBY":
                    standby = player.get_standby_obj()
                    for obj in standby:
                        obj.change_hp(effect_value)
                        self.send_effect_message("hp", player, obj)
                elif effect_obj == "SELF":
                    if isinstance(invoker, Character):
                        invoker.change_hp(effect_value)
                        self.send_effect_message("hp", player, invoker)
                elif isinstance(effect_obj, Character):
                    effect_obj.change_hp(effect_value)
                    self.send_effect_message("hp", player, effect_obj)
                elif effect_obj == "ALL":
                    characters = player.characters
                    for index, character in enumerate(characters):
                        character.change_hp(effect_value)
                        self.send_effect_message("hp", player, character)
                consume |= True
            elif effect_type == "APPLICATION":
                oppose: Player = self.get_one_oppose(player)
                if effect_obj == "ACTIVE":
                    reaction_effect = self.handle_element_reaction(oppose, player, player.get_active_character_obj(), effect_value)
                    reaction = reaction_effect["reaction"]
                    await self.handle_element_reaction_extra_effect(oppose, player, player.get_active_character_obj(), reaction)
                    # if reaction is not None:
                    #     await self.invoke_modify("element_reaction", player, player.get_active_character_obj())
                    # self.send_effect_message("application", player, player.get_active_character_obj())
                elif effect_obj == "SELF":
                    reaction_effect = self.handle_element_reaction(oppose, player, invoker, effect_value)
                    reaction = reaction_effect["reaction"]
                    await self.handle_element_reaction_extra_effect(oppose, player, invoker, reaction)
                    # if reaction is not None:
                    #     await self.invoke_modify("element_reaction", player, invoker,
                    #                              only_invoker=True)
                    # self.send_effect_message("application", player, invoker)
                consume |= True
            elif effect_type == "CHANGE_ENERGY":
                if effect_obj == "ACTIVE":
                    active = player.get_active_character_obj()
                    active.change_energy(effect_value)
                    self.send_effect_message("energy", player, active)
                consume |= True
            elif effect_type == "PREPARE":
                invoker.state.update(deepcopy(effect))
                consume |= True
        print(1761, "handle_effect", consume)
        return kwargs, consume

    @staticmethod
    def consume_modify_usage(modify, operation="use"):
        time_limit = modify["time_limit"]
        if operation == "use":
            if "USAGE" in time_limit:
                time_limit["USAGE"] -= 1
                if time_limit["USAGE"] <= 0:
                    return "remove"
            if "ROUND" in time_limit:
                time_limit["ROUND"][1] -= 1
            if "IMMEDIATE" in time_limit:
                return "remove"
        elif operation == "end":
            if "ROUND" in time_limit:
                time_limit["ROUND"][1] = time_limit["ROUND"][0]
            if "DURATION" in time_limit:
                time_limit["DURATION"] -= 1
                if time_limit["DURATION"] == 0:
                    return "remove"

    def consume_state_usage(self, state, operation="use"):
        time_limit = state["time_limit"]
        if operation == "use":
            if "USAGE" in time_limit:
                time_limit["USAGE"] -= 1
                if time_limit["USAGE"] <= 0:
                    return "remove"
                return time_limit["USAGE"]
            if "ROUND" in time_limit:
                time_limit["ROUND"][1] -= 1
                if time_limit["ROUND"][1] == 0:
                    return "use_up"
            if "IMMEDIATE" in time_limit:
                return "remove"
        elif operation == "end":
            if "ROUND" in time_limit:
                time_limit["ROUND"][1] = time_limit["ROUND"][0]
                return "activate"
            if "DURATION" in time_limit:
                time_limit["DURATION"] -= 1
                if time_limit["DURATION"] == 0:
                    return "remove"
                else:
                    return time_limit["DURATION"]
            for modify in state["modify"]:
                if "time_limit" in modify:
                    self.consume_modify_usage(modify, "end")

    @staticmethod
    def remove_modify(modifies: list, need_remove_indexes: set):
        if need_remove_indexes:
            sort_index = sorted(need_remove_indexes, reverse=True)
            for index in sort_index:
                modifies.pop(index)

    def remove_equip(self, invoker: Character, card_name):
        need_remove = set()
        for index, modify in enumerate(invoker.modifies):
            if "name" in modify:
                if modify["name"].startswith(card_name):
                    need_remove.add(index)
        self.remove_modify(invoker.modifies, need_remove)

    def send_effect_message(self, change_type:str, player, invoker, **kwargs):
        player_index = self.players.index(player)
        if change_type == "hp":
            position = player.characters.index(invoker)
            hp = invoker.get_hp()
            change_hp_message = {"message": "change_hp",
                                 "position": position,
                                 "hp": hp}
            self.send(change_hp_message, self.client_socket[player_index])
            change_hp_message = {"message": "change_oppose_hp",
                                 "position": position,
                                 "hp": hp}
            for client in self.get_oppose_client(player_index):
                self.send(change_hp_message, client)
        elif change_type == "application":
            position = player.characters.index(invoker)
            application = [elementType.name.lower() for elementType in invoker.application]
            application_message = {"message": "change_application", "position": position,
                                   "application": application}
            self.send(application_message, self.client_socket[player_index])
            application_message = {"message": "oppose_change_application", "position": position,
                                   "application": application}
            for client in self.get_oppose_client(player_index):
                self.send(application_message, client)
        elif change_type == "equip": # kwargs: equip
            position = player.characters.index(invoker)
            equip = kwargs["equip"]
            update_equip_message = {"message": "change_equip", "position": position,
                                    "equip": equip}
            self.send(update_equip_message, self.client_socket[player_index])
            update_equip_message = {"message": "change_oppose_equip", "position": position, "equip": equip}
            for client in self.get_oppose_client(player_index):
                self.send(update_equip_message, client)
        elif change_type == "energy":
            char_index = player.characters.index(invoker)
            energy = (invoker.get_energy(), invoker.max_energy)
            change_energy_message = {"message": "change_energy", "position": char_index,
                                     "energy": energy}
            self.send(change_energy_message, self.client_socket[player_index])
            change_energy_message = {"message": "change_oppose_energy", "position": char_index,
                                     "energy": energy}
            for client in self.get_oppose_client(player_index):
                self.send(change_energy_message, client)
            # playercur = self.players[self.now_player]
            # standby = playercur.get_standby_obj()
            # for char in standby:
            #     index =  playercur.characters.index(char)
            #     energy = (char.get_energy(), char.max_energy)
            #     change_energy_message = {"message": "change_energy", "position": char_index,
            #                          "energy": energy}
            #     self.send(change_energy_message, self.client_socket[player_index])
            #     change_energy_message = {"message": "change_oppose_energy", "position": char_index,
            #                          "energy": energy}
            #     for client in self.get_oppose_client(player_index):
            #         self.send(change_energy_message, client)

        elif change_type == "add_state":
            add_state_message = {"message": "add_state", "state_name": kwargs["state_name"],"store":kwargs["store"],
                                     "num": kwargs["num"], "type": kwargs["type"], "state_icon": kwargs["state_icon"]}
            self.send(add_state_message, self.client_socket[player_index])
            add_state_message = {"message": "oppose_add_state", "state_name": kwargs["state_name"],"store":kwargs["store"],
                                 "num": kwargs["num"], "type": kwargs["type"], "state_icon": kwargs["state_icon"]}
            for client in self.get_oppose_client(player_index):
                self.send(add_state_message, client)
        elif change_type == "change_state_usage": # kwargs: state_name, num, type
            if kwargs["type"] == "team":
                store = None
            else:
                store = player.characters.index(invoker)
            change_state_usage = {"message":"change_state_usage", "state_name": kwargs["state_name"], "store":store,
                                  "num": kwargs["num"], "type": kwargs["type"]}
            self.send(change_state_usage, self.client_socket[player_index])
            change_state_usage = {"message": "change_oppose_state_usage", "state_name": kwargs["state_name"],
                                  "store":store, "num": kwargs["num"], "type": kwargs["type"]}
            for client in self.get_oppose_client(player_index):
                self.send(change_state_usage, client)
        elif change_type == "remove_state": # kwargs: state_name, type
            if kwargs["type"] == "team":
                store = None
            else:
                store = player.characters.index(invoker)
            remove_state_message = {"message": "remove_state", "state_name": kwargs["state_name"], "store":store,
                                  "type": kwargs["type"]}
            self.send(remove_state_message, self.client_socket[player_index])
            remove_state_message = {"message": "remove_oppose_state", "state_name": kwargs["state_name"],
                                   "store":store, "type": kwargs["type"]}
            for client in self.get_oppose_client(player_index):
                self.send(remove_state_message, client)
        elif change_type == "infusion":
            pass
        elif change_type == "change_active": # kwargs: change_from, change_to
            from_index = kwargs["change_from"]
            to_index = kwargs["change_to"]
            choose_message = {"message": "oppose_change_active", "from_index": from_index, "to_index": to_index}
            for client in self.get_oppose_client(player_index):
                self.send(choose_message, client)
            choose_message = {"message": "player_change_active", "from_index": from_index, "to_index": to_index}
            self.send(choose_message, self.client_socket[player_index])
            clear_skill_message = {"message": "clear_skill"}
            self.send(clear_skill_message, self.client_socket[player_index])
            active = player.get_active_character_obj()
            skill_name, skill_cost = active.get_skill_name_and_cost()
            init_skill_message = {"message": "init_skill", "skill_name": skill_name, "skill_cost": skill_cost}
            self.send(init_skill_message, self.client_socket[player_index])
        elif change_type == "dice":
            dices = self.get_player_dice_info(player)
            dice_message = {"message": "clear_dice"}
            self.send(dice_message, self.client_socket[player_index])
            dice_message = {"message": "add_dice", "dices": dices}
            self.send(dice_message, self.client_socket[player_index])
            dice_num_message = {"message": "show_dice_num", "num": len(dices)}
            self.send(dice_num_message, self.client_socket[player_index])
            dice_num_message = {"message": "show_oppose_dice_num", "num": len(dices)}
            for client in self.get_oppose_client(player_index):
                self.send(dice_num_message, client)
        elif change_type == "clear_dice":
            dice_message = {"message": "clear_dice"}
            self.send(dice_message, self.client_socket[player_index])
            dice_num_message = {"message": "show_dice_num", "num": ""}
            self.send(dice_num_message, self.client_socket[player_index])
            dice_num_message = {"message": "show_oppose_dice_num", "num": ""}
            for client in self.get_oppose_client(player_index):
                self.send(dice_num_message, client)
        elif change_type == "add_card": # kwargs: card_name, card_num, card_cost
            add_card_message = {"message": "add_card", "card_name": kwargs["card_name"], "card_cost": kwargs["card_cost"]}
            self.send(add_card_message, self.client_socket[player_index])
            oppo_card_num_message = {"message": "oppose_card_num", "num": kwargs["card_num"]}
            for client in self.get_oppose_client(player_index):
                self.send(oppo_card_num_message, client)
        elif change_type == "play_card":
            # remove_card_message = {"message": "remove_card", "card_index": kwargs["card_index"]} # 客户端自行处理
            # self.send(remove_card_message, self.client_socket[player_index])
            oppo_card_num_message = {"message": "oppose_card_num", "num": len(self.get_player_hand_card_info(player))}
            for client in self.get_oppose_client(player_index):
                self.send(oppo_card_num_message, client)
        elif change_type == "add_support": # invoker[Card], kwargs: num
            name = invoker.get_name()
            init_support_message = {"message": "add_support", "support_name": name, "num": str(kwargs["num"])}
            self.send(init_support_message, self.client_socket[player_index])
            init_support_message = {"message": "oppose_add_support", "support_name": name,
                                    "num": str(kwargs["num"])}
            for client in self.get_oppose_client(player_index):
                self.send(init_support_message, client)
        elif change_type == "add_summon": # invoker[Summon]
            name = invoker.get_name()
            effect = invoker.get_show()
            usage = invoker.usage
            add_summon_message = {"message": "add_summon", "summon_name": name, "usage": str(usage), "effect":effect}
            self.send(add_summon_message, self.client_socket[player_index])
            add_summon_message = {"message": "oppose_add_summon", "summon_name": name,
                                  "usage": str(usage), "effect": effect}
            for client in self.get_oppose_client(player_index):
                self.send(add_summon_message, client)
        elif change_type == "change_skill_state": # --- kwargs: skill_cost, skill_state --- #
            change_skill_state_message = {"message": "change_skill_state", "skill_cost": kwargs["skill_cost"], "skill_state": kwargs["skill_state"]}
            self.send(change_skill_state_message, self.client_socket[player_index])
        elif change_type == "change_summon_usage": # --- kwargs: index --- #      
            change_summon_usage_message = {"message": "change_summon_usage", "index": kwargs["index"], "usage": invoker.usage}
            self.send(change_summon_usage_message, self.client_socket[player_index])
            change_summon_usage_message = {"message": "change_oppose_summon_usage", "index": kwargs["index"], "usage": invoker.usage}
            for client in self.get_oppose_client(player_index):
                self.send(change_summon_usage_message, client)
        elif change_type == "remove_summon": # --- kwargs: index --- #      
            remove_summon_message = {"message": "remove_summon", "index": kwargs["index"]}
            self.send(remove_summon_message, self.client_socket[player_index])
            remove_summon_message = {"message": "remove_oppose_summon", "index": kwargs["index"]}
            for client in self.get_oppose_client(player_index):
                self.send(remove_summon_message, client)
        elif change_type == "change_support_usage":
            index = player.supports.index(invoker)
            if invoker.have_counter():
                num = invoker.get_count()
            elif invoker.have_usage():
                num = invoker.usage
            else:
                num = ""
            change_support_usage_message = {"message": "change_support_usage", "index": index, "usage": num}
            self.send(change_support_usage_message, self.client_socket[player_index])
            change_support_usage_message = {"message": "change_oppose_support_usage", "index": index, "usage": num}
            for client in self.get_oppose_client(player_index):
                self.send(change_support_usage_message, client)
        elif change_type == "remove_support": # --- kwargs: index --- #        
            remove_support_message = {"message": "remove_support", "index": kwargs["index"]}
            self.send(remove_support_message, self.client_socket[player_index])
            remove_support_message = {"message": "remove_oppose_support", "index": kwargs["index"]}
            for client in self.get_oppose_client(player_index):
                self.send(remove_support_message, client)
        elif change_type == 'block_action':
            block_action_message = {"message": "block_action"}
            self.send(block_action_message, self.client_socket[player_index])


    @staticmethod
    def is_trigger_time(operation, modify_tag):
        if modify_tag == "any":
            return True
        elif modify_tag == 'defense':
            return True
        else:
            if operation == modify_tag:
                return True
            elif modify_tag == "cost" and operation in ["skill_cost", "card_cost"]:
                return True
        return False

    def check_condition(self, player, invoker, condition, **kwargs):
        if condition:
            for each in condition:
                if isinstance(each, str):
                    if each.startswith("STAGE_"):
                        condition_stage = each.replace("STAGE_", "")
                        if condition_stage == self.stage.name:
                            continue
                        else:
                            return False
                    elif each == "BEING_HIT":
                        if "hurt" in kwargs:
                            continue
                        else:
                            return False
                    elif each == "SKILL":
                        if "skill_type" in kwargs:
                            continue
                        else:
                            return False
                    elif each == "NORMAL_ATTACK":
                        if "skill_type" in kwargs:
                            if "Normal Attack" in kwargs["skill_type"]:
                                continue
                            else:
                                return False
                        else:
                            return False
                    elif each == "ELEMENTAL_SKILL":
                        if "skill_type" in kwargs:
                            if "Elemental Skill" in kwargs["skill_type"]:
                                continue
                            else:
                                return False
                        else:
                            return False
                    elif each == "ELEMENTAL_BURST":
                        if "skill_type" in kwargs:
                            if "Elemental Burst" in kwargs["skill_type"]:
                                continue
                            else:
                                return False
                        else:
                            return False
                    elif each == "CHARGED_ATTACK":
                        if "skill_type" in kwargs:
                            if "CHARGED_ATTACK" in kwargs["skill_type"]:
                                continue
                            else:
                                return False
                        else:
                            return False
                    elif each == "ELEMENT_REACTION":
                        if "reaction" in kwargs:
                            if kwargs["reaction"] is not None:
                                continue
                            else:
                                return False
                        else:
                            return False
                    elif each == "SWIRL":
                        if "reaction" in kwargs:
                            if kwargs["reaction"] == "SWIRL":
                                continue
                            else:
                                return False
                    elif each == "PYRO_RELATED":
                        if "reaction" in kwargs:
                            if kwargs["reaction"] in ["MELT", "VAPORIZE", "OVERLOADED", "BURNING"]:
                                continue
                            elif kwargs["reaction"] == "SWIRL":
                                if kwargs["swirl_element"] == "PYRO":
                                    continue
                                else:
                                    return False
                            elif kwargs["reaction"] == "CRYSTALLIZE":
                                if kwargs["crystallize_element"] == "PYRO":
                                    continue
                                else:
                                    return False
                            else:
                                return False
                    elif each == "HYDRO_RELATED":
                        if "reaction" in kwargs:
                            if kwargs["reaction"] in ["VAPORIZE", "FROZEN", "ELECTRO_CHARGE", "BLOOM"]:
                                continue
                            elif kwargs["reaction"] == "SWIRL":
                                if kwargs["swirl_element"] == "HYDRO":
                                    continue
                                else:
                                    return False
                            elif kwargs["reaction"] == "CRYSTALLIZE":
                                if kwargs["crystallize_element"] == "HYDRO":
                                    continue
                                else:
                                    return False
                            else:
                                return False
                    elif each == "ELECTRO_RELATED":
                        if "reaction" in kwargs:
                            if kwargs["reaction"] in ["OVERLOADED", "SUPER_CONDUCT", "ELECTRO_CHARGE", "CATALYZE"]:
                                continue
                            elif kwargs["reaction"] == "SWIRL":
                                if kwargs["swirl_element"] == "ELECTRO":
                                    continue
                                else:
                                    return False
                            elif kwargs["reaction"] == "CRYSTALLIZE":
                                if kwargs["crystallize_element"] == "ELECTRO":
                                    continue
                                else:
                                    return False
                            else:
                                return False
                    elif each == "CRYO_RELATED":
                        if "reaction" in kwargs:
                            if kwargs["reaction"] in ["MELT", "SUPER_CONDUCT", "FROZEN", "SUPER_CONDUCT"]:
                                continue
                            elif kwargs["reaction"] == "SWIRL":
                                if kwargs["swirl_element"] == "CRYO":
                                    continue
                                else:
                                    return False
                            elif kwargs["reaction"] == "CRYSTALLIZE":
                                if kwargs["crystallize_element"] == "CRYO":
                                    continue
                                else:
                                    return False
                            else:
                                return False
                    elif each == "DENDRO_RELATED":
                        if "reaction" in kwargs:
                            if kwargs["reaction"] in ["BURNING", "BLOOM", "CATALYZE"]:
                                continue
                            else:
                                return False
                    elif each == "ANEMO_RELATED":
                        if "reaction" in kwargs:
                            if kwargs["reaction"] == "SWIRL":
                                continue
                            else:
                                return False
                    elif each == "GEO_RELATED":
                        if "reaction" in kwargs:
                            if kwargs["reaction"] == "CRYSTALLIZE":
                                continue
                            else:
                                return False
                    else:
                        return False
                elif isinstance(each, dict):
                    logic = each["logic"]
                    special_const = kwargs["special_const"] if "special_const" in kwargs else {}
                    if logic == "check":
                        check_type = each["what"]
                        if check_type == "counter":
                            if invoker is not None:
                                attribute = each["whose"]
                                if attribute in invoker.counter:
                                    num = invoker.counter[attribute]
                                    require = each["condition"]
                                    if isinstance(require, str):
                                        require = evaluate_expression(require, special_const)
                                    if self.compare(each["operator"], num, require):
                                        continue
                        elif check_type == "element":
                            attribute = each["whose"]
                            if isinstance(attribute, str):
                                attribute = evaluate_expression(attribute, special_const)
                            require = each["condition"]
                            if isinstance(require, str):
                                require = evaluate_expression(require, special_const)
                            if attribute == "hurt":
                                if "hurt" in kwargs and "element" in kwargs:
                                    if self.compare(each["operator"], kwargs["element"], require):
                                        continue
                            elif attribute == "attack":
                                if "damage" in kwargs and "element" in kwargs:
                                    if self.compare(each["operator"], kwargs["element"], require):
                                        continue
                            elif attribute == "self":
                                if isinstance(invoker, Character):
                                    element = invoker.element
                                    if self.compare(each["operator"], element, require):
                                        continue
                            else:
                                if self.compare(each["operator"], attribute, require):
                                    continue
                        elif check_type == "weapon":
                            attribute = each["whose"]
                            if isinstance(attribute, str):
                                attribute = evaluate_expression(attribute, special_const)
                            if attribute == "active":
                                weapon = player.get_active_character_obj().weapon
                            else:
                                return False
                            require = each["condition"]
                            if self.compare(each["operator"], weapon, require):
                                continue
                        elif check_type == "hurt":
                            if "hurt" in kwargs:
                                hurt = kwargs["hurt"]
                                require = each["condition"]
                                if self.compare(each["operator"], hurt, require):
                                    continue
                        elif check_type == "hp":
                            attribute = each["whose"]
                            require = each["condition"]
                            if attribute == "active":
                                hp = player.get_active_character_obj().get_hp()
                                if self.compare(each["operator"], hp, require):
                                    continue
                            elif attribute == "oppose":
                                hp = self.get_one_oppose(player).get_active_character_obj().get_hp()
                                if self.compare(each["operator"], hp, require):
                                    continue
                        elif check_type == "dice":
                            attribute = each["whose"]
                            require = each["condition"]
                            if attribute == "num":
                                dice_num = len(player.dices)
                                if self.compare(each["operator"], dice_num, require):
                                    continue
                        elif check_type == "energy":
                            attribute = each["whose"]
                            require = each["condition"]
                            if attribute == "active":
                                energy = player.get_active_character_obj().get_energy()
                                if self.compare(each["operator"], energy, require):
                                    continue
                            elif attribute == "_each":
                                max_energy = 2
                                energy = 0
                                for char in player.get_standby_obj():
                                    char_energy = char.get_energy() 
                                    energy += min(char_energy,max_energy)
                                    char.set_energy(max(char_energy - max_energy, 0))
                                    if(energy == max_energy):
                                        break
                                cur = player.get_active_character_obj()
                                cur.set_energy(cur._energy + energy)
                                if self.compare(each["operator"], energy, require):
                                    continue
                        return False
                    elif logic == "have":
                        what = each["what"]
                        where = each["where"]
                        operator_ = each["operator"]
                        require = each["condition"]
                        if isinstance(require, str):
                            require = evaluate_expression(require, special_const)
                        if what == "card":
                            if where == "team":
                                cards = player.hand_cards
                                if self.compare(operator_, cards, require):
                                    continue
                        elif what == "state":
                            if where == "self":
                                all_state = invoker.modifies
                                # TODO
                                state_names = [state.keys()[0] for state in all_state if "name" not in state]
                                if self.compare(operator_, state_names, require):
                                    continue
                            elif where == "team":
                                all_state = player.team_modifier
                                # TODO
                                state_names = [state.keys()[0] for state in all_state if "name" not in state]
                                if self.compare(operator_, state_names, require):
                                    continue
                        elif what == "infusion":
                            if where == "self":
                                all_state = invoker.state
                                if "INFUSION" in all_state:
                                    infusion = all_state["INFUSION"]
                                    if infusion:
                                        infusion_name = infusion[0]["name"]
                                        if self.compare(operator_, infusion_name, require):
                                            continue
                        elif what == "summon":
                            if where == "team":
                                summons = player.get_summon_name()
                                if self.compare(operator_, summons, require):
                                    continue
                        elif what == "event":
                            # TODO end event
                            pass
                        elif what == "counter":
                            counter = invoker.counter
                            if self.compare(operator_, counter, require):
                                continue
                        elif what == "modify":
                            if where == "self":
                                all_state = invoker.modifies
                                # TODO
                                state_names = [state["name"] for state in all_state if "name" in state]
                                if self.compare(operator_, state_names, require):
                                    continue
                        return False
                    elif logic == "play_card":
                        if "tag" in each and "card_tag" in kwargs:
                            if each["tag"] in kwargs["card_tag"]:
                                continue
                        return False
                    elif logic == "compare":
                        value1 = each["value1"]
                        value2 = each["value2"]
                        operator_ = each["operator"]
                        if isinstance(value1, str):
                            value1 = evaluate_expression(value1, special_const)
                        if isinstance(value2, str):
                            value2 = evaluate_expression(value2, special_const)
                        if self.compare(operator_, value1, value2):
                            continue
                        return False
                    elif logic == "is_active":
                        who = logic["who"]
                        if who == "_self":
                            if invoker.is_active:
                                continue
                        else:
                            if player.get_active_character_obj().get_name() == who:
                                continue
                        return False
                    elif logic == "is_alive":
                        who = logic["who"]
                        if who == "_self":
                            if invoker.alive:
                                continue
                        else:
                            characters = player.characters
                            alive = False
                            for character in characters:
                                if character.get_name() == who and character.alive:
                                    alive = True
                                    break
                            if alive:
                                continue
                        return False
                elif isinstance(each, list):
                    satisfy = False
                    for condition in each:
                        condition_state = self.check_condition(player, invoker, [condition], **kwargs)
                        if condition_state:
                            satisfy |= True
                            break
                    if not satisfy:
                        return False
        return True

    @staticmethod
    def compare(operator, left_value, right_value):
        if operator == "equal":
            if left_value == right_value:
                return True
        elif operator == "less":
            if left_value < right_value:
                return True
        elif operator == "large":
            if left_value > right_value:
                return True
        elif operator == "large_equal":
            if left_value >= right_value:
                return True
        elif operator == "not_equal":
            if left_value != right_value:
                return True
        elif operator == "less_equal":
            if left_value <= right_value:
                return True
        elif operator == "is": 
            if right_value == "melee":
                if left_value in ["polearm", "sword", "claymore"]:
                    return True
            elif right_value == "even":
                if not left_value % 2:
                    return True
            elif right_value == "ELEMENT":
                if left_value in ["HYDRO", "GEO", "ELECTRO","DENDRO", "PYRO", "CRYO", "ANEMO"]:
                    return True
        elif operator == "is_not":
            # TODO
            pass
        elif operator == "contain":
            if right_value in left_value:
                return True
        elif operator == "not_contain":
            if right_value not in left_value:
                return True
        return False

    def round_end_consume_modify(self):
        for player in self.players:
            for character in player.characters:
                need_remove_modifies = set()
                for index, modify in enumerate(character.modifies):
                    if "time_limit" in modify:
                        consume_state = self.consume_modify_usage(modify, "end")
                        if consume_state == "remove":
                            need_remove_modifies.add(index)
                self.remove_modify(character.modifies, need_remove_modifies)
            need_remove_modifies = set()
            for index, modify in enumerate(player.team_modifier):
                if "time_limit" in modify:
                    consume_state = self.consume_modify_usage(modify, "end")
                    if consume_state == "remove":
                        need_remove_modifies.add(index)
            self.remove_modify(player.team_modifier, need_remove_modifies)
            for summon in player.summons:
                need_remove_modifies = set()
                for index, modify in enumerate(summon.modifies):
                    if "time_limit" in modify:
                        consume_state = self.consume_modify_usage(modify, "end")
                        if consume_state == "remove":
                            need_remove_modifies.add(index)
                self.remove_modify(summon.modifies, need_remove_modifies)
                
            for support in player.supports:
                need_remove_modifies = set()
                for index, modify in enumerate(support.modifies):
                    if "time_limit" in modify:
                        consume_state = self.consume_modify_usage(modify, "end")
                        if consume_state == "remove":
                            need_remove_modifies.add(index)
                self.remove_modify(support.modifies, need_remove_modifies)




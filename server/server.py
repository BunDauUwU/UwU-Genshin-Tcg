import socket
from utils import read_json, pre_check
import threading
from game import Game


def start_game(clients, mode, client_deck):
    gcg = Game(mode, clients, client_deck)
    gcg.start_game()

class Server:
    def __init__(self):
        self.waiting_clients = []
        self.client_info = {} 
        self.mode_clients = {} 
        self.config = read_json("config.json")["server"] 
        self.svr_sock = self.create_socket() 
        self.valid_deck_client = {} 

    @staticmethod
    def create_socket():
        svr_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        svr_sock.bind(("127.0.0.1", 14095))
        return svr_sock

    def send(self, data, client):
        self.svr_sock.sendto(data, client)

    def handle_message(self, data, remote_addr):
        try:
            msg = eval(data.decode("utf-8"))
            if msg["message"] == "connect request":
                nickname = msg["nickname"]
                self.client_info[remote_addr] = [nickname, None]
                self.waiting_clients.append(remote_addr)
                self.send(str({"message": "choose mode"}).encode("utf-8"), remote_addr)
            elif msg["message"] == "selected mode":
                mode = msg["mode"]
                self.client_info[remote_addr][1] = mode
                self.send(str({"message": "send deck"}).encode("utf-8"), remote_addr)
                self.mode_clients.setdefault(mode, []).append(remote_addr)
            elif msg["message"] == "check deck":
                character = msg["character"]
                card = msg["card"]
                mode = self.client_info[remote_addr][1]
                mode = "Game1"
                check_state = pre_check(mode, character, card)
                if isinstance(check_state, list):
                    data_send : dict = {"message": "recheck deck", "invalid_card": check_state}
                    self.send(str(data_send).encode("utf-8"), remote_addr)
                else:
                    self.valid_deck_client.update({remote_addr: (character, card)})
                    self.whether_start_game(mode)
        except Exception as e:
            print("Error in handle_message:", e)

    def whether_start_game(self, mode):
        if mode in self.mode_clients:
            valid_client = []
            client_deck = {}
            for client in self.mode_clients[mode]:
                if client in self.valid_deck_client:
                    valid_client.append(client)
                    client_deck.update({client: self.valid_deck_client[client]})
            if len(valid_client) >= self.config[mode]["client_num"]:
                new_game_thread = threading.Thread(target=start_game, args=(valid_client, mode, client_deck))
                new_game_thread.start()  
                for c in valid_client:
                    self.waiting_clients.remove(c)
                    self.mode_clients[mode].remove(c)
                    self.valid_deck_client.pop(c)

    def receive(self):
        while True:
            data, remote_addr = self.svr_sock.recvfrom(4096)
            if data:
                self.handle_message(data, remote_addr)

    def start(self):
        threading.Thread(target=self.receive).start()

if __name__ == "__main__":
    svr = Server()
    svr.start()

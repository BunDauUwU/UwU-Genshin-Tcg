import os 
# os.system('cmd /k "pip install firebase_admin"')
# os.system('cmd /k "pip install tk"')
# os.system('cmd /k "pip install tkinterwidgets"`')
# os.system('start cmd /k "cd server & py server.py"') #'/c' == system(0)
import json, sys

import socketio

from tkinter import *
from PIL import Image, ImageTk
from tkinter import messagebox

from pickcard import Pickcard
from login import Login

import utils as checkEngine

WIDTH = 1575
HEIGHT = 750

class Master(Tk):
    sio: socketio.Client

    def __init__(self):
        Tk.__init__(self)
        self.configure(bg = 'black')
        self.title("UwU")
        x = self.winfo_screenwidth()  
        y = self.winfo_screenheight()  
        self.geometry("%dx%d" % (x, y))
        self.resizable(False, False)
        self.attributes('-fullscreen',True)
        self.resizable(False, False)

        self.sio = socketio.Client()

        # ------ Tkinter ------ #
        self.image = Image.open("./frame/Namecard_Background_Achievement_Invoker.webp")
        self.resize_image = self.image.resize((x, y))
        self.img = ImageTk.PhotoImage(self.resize_image)
        self.titleImage = Label(self, image=self.img, text = '') 

        noneImg = Image.open('./frame/background.png')
        rz_noneImg = noneImg.resize((42,72))
        self.noneImg = ImageTk.PhotoImage(rz_noneImg)
        self.buttonFind = Button(self, text = "FindOpponent", command = lambda: self.FindOpponent())
    
        # ------ Room ------ #
        self.room = None
        # ----- Preprocess --- #
        self.protocol("WM_DELETE_WINDOW", lambda : self.callback())

        self.login = Login(self, self.sio)
        self.pickcard = Pickcard(self)
        self.pickcard.CardLayout()

    # --- Run --- #
    def run(self):
        self.titleImage.place(x = 0, y = 0, relheight=1, relwidth=1)
        self.buttonFind.place(x = 50, y = 20)
        self.pickcard.run_CardLayout()
        
    # --- Transfer data --- #
    def TransferData(self):
        self.dataChar = []
        self.dataCard = []
        for i in self.pickcard.slotChar:
            self.dataChar.append(self.pickcard.charName[i])
        for i in self.pickcard.slotCard:
            self.dataCard.append(self.pickcard.cardName[i])
        kq = checkEngine.pre_check('Game1', self.dataChar, self.dataCard)
        if(kq != True):
            messagebox.showinfo("showinfo",kq)
            return 0
        print(self.login.recordname)
        self.data_send : dict = {
            self.login.recordname:{
                "character":self.dataChar,
                "card":self.dataCard,
                "camp":"Player"
            }
        }
        json_object = json.dumps(self.data_send, indent=4)
        with open("data_send.json", "w") as outfile:
            outfile.write(json_object)
        return True

    # --- Find Opponent --- #
    def FindOpponent(self):
        if(None in self.pickcard.slotChar):
            messagebox.showinfo( message = "3 character cards are required")
            return 
        if(None in self.pickcard.slotCard):
            messagebox.showinfo( message = "40 support cards are required")
            return
        if self.TransferData() != True:
            return
        os.system('start cmd /k "py client_main.py"')
        self.destroy()

    # --- Callback --- #
    def callback(self):
        close = messagebox.askokcancel("Close", "Sure? All progress will be LOST")
        if close: 
            self.destroy()


if __name__ == "__main__":
    app = Master()
    app.mainloop()


# {
#     "": {
#         "character": [
#             "Ganyu",
#             "Xiangling",
#             "Bennett"
#         ],
#         "card": [
#             "Raven Bow",
#             "Sacrificial Sword",
#             "Broken Rime's Echo",
#             "Blizzard Strayer",
#             "Dawn Winery",
#             "Dawn Winery",
#             "Dawn Winery",
#             "Favonius Cathedral",
#             "Favonius Cathedral",
#             "Favonius Cathedral",
#             "Paimon",
#             "Paimon",
#             "Paimon",
#             "Katheryne",
#             "Katheryne",
#             "Wagner",
#             "Timmie",
#             "Timmie",
#             "Liben",
#             "Liben",
#             "Chang the Ninth",
#             "Chang the Ninth",
#             "Elemental Resonance Fervent Flames",
#             "The Bestest Travel Companion!",
#             "The Bestest Travel Companion!",
#             "The Bestest Travel Companion!",
#             "Changing Shifts",
#             "Changing Shifts",
#             "Changing Shifts",
#             "Toss-Up",
#             "Toss-Up",
#             "Leave It to Me!",
#             "Leave It to Me!",
#             "Leave It to Me!",
#             "Calx's Arts",
#             "Calx's Arts",
#             "Calx's Arts",
#             "Quick Knit",
#             "Quick Knit",
#             "Quick Knit"
#         ],
#         "camp": "Player"
#     }
# }

# {
#     "": {
#         "character": [
#             "Klee",
#             "Mona",
#             "Xingqiu"
#         ],
#         "card": [
#             "Skyward Atlas",
#             "Witch's Scorching Hat",
#             "Crimson Witch of Flames",
#             "Dawn Winery",
#             "Dawn Winery",
#             "Dawn Winery",
#             "Katheryne",
#             "Katheryne",
#             "Katheryne",
#             "Timmie",
#             "Timmie",
#             "Timmie",
#             "Liben",
#             "Liben",
#             "Liben",
#             "The Bestest Travel Companion!",
#             "The Bestest Travel Companion!",
#             "The Bestest Travel Companion!",
#             "Changing Shifts",
#             "Changing Shifts",
#             "Changing Shifts",
#             "Toss-Up",
#             "Toss-Up",
#             "Toss-Up",
#             "Strategize",
#             "Strategize",
#             "Strategize",
#             "Leave It to Me!",
#             "Leave It to Me!",
#             "Leave It to Me!",
#             "Send Off",
#             "Adeptus' Temptation",
#             "Adeptus' Temptation",
#             "Adeptus' Temptation",
#             "Sweet Madame",
#             "Sweet Madame",
#             "Sweet Madame",
#             "Mondstadt Hash Brown",
#             "Mondstadt Hash Brown",
#             "Mondstadt Hash Brown"
#         ],
#         "camp": "Player"
#     }
# }
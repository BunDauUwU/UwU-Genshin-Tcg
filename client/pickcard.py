from tkinter import *
import customtkinter
from PIL import Image, ImageTk
from tkinter import messagebox
import pywinstyles
import os
import json
import sys
import copy

with open("./character.json", "r") as f: deskChar = json.load(f)
with open("./card.json", "r") as f: deskCard = json.load(f)

# ---- Cmp ---- #
def cmp(element):
    return element == None, element


class Pickcard:
    app: Tk

    def __init__(self, app):
        self.app = app
    
    def CardLayout(self): 
        self.FrameCard = Frame(self.app, width = 1000, height = 80*8 + 20, bg = "#000001")
        pywinstyles.set_opacity(self.FrameCard, color="#000001")

        # ------ Card ------ #
        self.imgChar = []
        self.imgCard =[]
        self.charName = []
        self.cardName = []

        for CharName in deskChar['standard'].keys():
            path = os.path.join('./resources/characters/', f'{CharName.replace(" ","").replace(",","").replace("-","")}.png')
            if(not os.path.exists(path)):
               continue
            self.charName.append(CharName)
            img = Image.open(path)
            resize_img = img.resize((42,72))
            self.imgChar.append(ImageTk.PhotoImage(resize_img))
        
        for CardName in deskCard['standard'].keys():
            path = os.path.join('./resources/cards/', f'{CardName.replace(" ", "").replace(",","").replace("-","")}.png')
            if(not os.path.exists(path)):
               continue
            self.cardName.append(CardName)
            img = Image.open(path)
            resize_img = img.resize((42,72))
            self.imgCard.append(ImageTk.PhotoImage(resize_img))

        self.slotChar = [None,None,None]
        self.slotCharButton = []
        for i in range(3):
            btn = Button(self.app,background = "#fcd088", image = self.app.noneImg,command = lambda copyi = i:self.RemoveCharacter(btn, copyi))
            self.slotCharButton.append(btn)

        self.slotCard = [None]*40
        self.slotCardButton = []
        for i in range(40):
            btn = Button(self.app,background = "#fcd088", image = self.app.noneImg, command = lambda i=i, btn = btn:self.RemoveCard(btn, i))
            self.slotCardButton.append(btn)
        
        self.Details = Label(self.app, image = self.app.noneImg)
        self.BigImg = Label(self.app, image = self.app.noneImg)
        self.DetailsImg = None
        self.CharacerAvatar = None
        
    def run_CardLayout(self):
        self.slotCharButton[0].place(x = 50, y = 70)
        self.slotCharButton[1].place(x = 100, y = 70)
        self.slotCharButton[2].place(x = 150, y = 70)

        for i in range(20):
            self.slotCardButton[i].place(x=i*50 + 50, y=0 + 340)
        for i in range(20):
            self.slotCardButton[i+20].place(x=i*50 + 50, y=79 + 340)

        self.FrameCard.place(x = 50, y = 420)
        self.creat_Card()
    
    def detailsChar(self, stt):
            path = os.path.join('./InfoCharacter/', f'{self.charName[stt].replace(" ","").replace(",","").replace("-","")}.png')
            if not os.path.exists(path):
                return
            self.DetailsImg = Image.open(path)
            self.DetailsImg = ImageTk.PhotoImage(self.DetailsImg)
            self.Details.configure(image = self.DetailsImg)
            self.Details.place(x = 1100, y = 170)
            cpath = os.path.join('./resources/characters/', f'{self.charName[stt].replace(" ","").replace(",","").replace("-","")}.png')
            if not os.path.exists(cpath):
                return
            self.CharacerAvatar = Image.open(cpath).resize((42*4,72*4))
            self.CharacerAvatar = ImageTk.PhotoImage(self.CharacerAvatar)
            self.BigImg.configure(image = self.CharacerAvatar)
            self.BigImg.place(x = 1700, y = 170)

    def creat_Card(self):
        for i in range(len(self.imgChar)):
            btn = Button(image = self.imgChar[i], background='#fcd088', command = lambda i=i: self.addCharacter(i))
            btn.bind("<Enter>", func=lambda e, i = i: self.detailsChar(i))
            btn.place(x=((i)%20)*50 + 50, y=170 + (i//20)*80)
        
        for i in range(len(self.imgCard)):
            btn = Button(self.FrameCard, image = self.imgCard[i], background='#fcd088', command = lambda i=i: self.addCard(i))
            btn.place(x=(i%20)*50, y=80*(i//20) + 90)


    def RemoveCharacter(self, here, stt): 
        self.slotChar[stt] = None
        self.slotCharButton[stt].configure(image = self.app.noneImg)

    def addCharacter(self,event):
        if(self.slotChar.count(event) >= 1):
            messagebox.showinfo(title = None, message = "This card cannot be obtained further")
            return
        for i in range(3):
            if(self.slotChar[i] == None):
                self.slotChar[i] = event
                self.slotCharButton[i].configure(image = self.imgChar[self.slotChar[i]])
                return
        messagebox.showinfo(title = None, message = "Remove some card before adding")
    
    def RemoveCard(self, here, stt):
        self.slotCard[stt] = None
        self.slotCard.sort(key = cmp)
        print(self.slotCard)
        for i in range(40):
            if self.slotCard[i] != None:
                self.slotCardButton[i].configure(image = self.imgCard[self.slotCard[i]])
            else:
                self.slotCardButton[i].configure(image = self.app.noneImg)

    def addCard(self,event):
        if(self.slotCard.count(event) >= 3):
            messagebox.showinfo(title = None, message = "This card cannot be obtained further")
            return
        for i in range(40):
            if self.slotCard[i] != None: continue
            self.slotCard[i] = event
            self.slotCard.sort(key=cmp)
            for i in range(40):
                if self.slotCard[i] != None:
                    self.slotCardButton[i].configure(image = self.imgCard[self.slotCard[i]])
                else :
                    break
            return
        messagebox.showinfo(title = None, message = "Remove some card before adding")         





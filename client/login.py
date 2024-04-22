from tkinter import *
from PIL import Image, ImageTk
from tkinter import messagebox

import socketio

class Login:
    app: Tk
    sio: socketio.Client

    def __init__(self, app, sio):
        self.app = app
        self.sio = sio

        self.uid = StringVar()
        self.name = StringVar()
        self.password = StringVar()
        self.recordname = ""

        self.titleFirst = Label(app, text = "", fg = "red", font = ('cambria', 16), bg = "#ead7a9")
        self.buttonReg = Button(app, text = "Submit", width = 30, command= lambda : self.login())
        self.nameEntry = Entry(app, width = 50, fg = 'gray', font=('cambria', 20), textvariable=self.uid, bg = '#1b1e24')
        self.passwordEntry = Entry(app, width = 35, textvariable=self.password)

        # self.titleFirst.place(x = 50, y = 10)
        self.nameEntry.place(relx=0.5, rely=0.5, anchor=CENTER)
        # self.passwordEntry.place(x = 50, y = 80)
        self.buttonReg.place(relx=0.5, rely=0.6, anchor=CENTER)
        self.nameEntry.config(highlightbackground = "white", highlightcolor= "white")
        self.nameEntry.insert(0, "Enter your name...")
        self.nameEntry.bind("<FocusIn>", lambda e: self.nameEntry.delete(0,"end"))
    

    def login(self):
        # self.sio.emit('login', dict(username=self.name.get(), password=self.password.get()))
        # Password check (do later)
        if(self.uid.get() == 'Enter your name...' or self.uid.get() == ''):
            messagebox.showinfo(title = None, message = "Login failed! ")
            return    
        messagebox.showinfo(title = None, message = "Login complete!")
        self.titleFirst.destroy()
        self.nameEntry.destroy()
        self.passwordEntry.destroy()
        self.buttonReg.destroy()

        self.app.run()
        
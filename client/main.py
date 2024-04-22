from app import Master
import os
os.system('start cmd /k "cd server & py server.py"') #'/c' == system(0)

if __name__ == "__main__":
    app = Master()
    app.mainloop()

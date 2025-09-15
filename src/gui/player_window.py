from tkinter import Tk, Frame, Button, Label, StringVar, Entry
from PIL import Image, ImageTk
import cv2
from threading import Thread

class PlayerWindow(Frame):
    def __init__(self, master):
        super().__init__(master)  # 注意这里要初始化Frame
        self.master = master
        self.master.title("RTSP Player")
        
        self.stream1_var = StringVar()
        self.stream2_var = StringVar()
        
        self.create_widgets()
        
        self.stream1_thread = None
        self.stream2_thread = None
        self.panel1 = None
        self.panel2 = None
        self.stop_flag = False

    def create_widgets(self):
        frame = Frame(self)
        frame.pack()

        Label(frame, text="RTSP Stream 1:").grid(row=0, column=0)
        Entry(frame, textvariable=self.stream1_var).grid(row=0, column=1)
        Button(frame, text="Play Stream 1", command=self.play_stream1).grid(row=0, column=2)

        Label(frame, text="RTSP Stream 2:").grid(row=1, column=0)
        Entry(frame, textvariable=self.stream2_var).grid(row=1, column=1)
        Button(frame, text="Play Stream 2", command=self.play_stream2).grid(row=1, column=2)

        self.panel1 = Label(self)
        self.panel1.pack(side="left", padx=10, pady=10)
        self.panel2 = Label(self)
        self.panel2.pack(side="right", padx=10, pady=10)

    def play_stream1(self):
        Thread(target=self.start_stream, args=(self.stream1_var.get(), self.panel1)).start()

    def play_stream2(self):
        Thread(target=self.start_stream, args=(self.stream2_var.get(), self.panel2)).start()

    def start_stream(self, stream_url, panel):
        if panel is None:
            print("Error: panel is None")
            return
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            print(f"无法打开流: {stream_url}")
            return
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            # 缩放到窗口适合的大小
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            img = img.resize((640, 360))  # 你可以根据窗口实际大小调整
            imgtk = ImageTk.PhotoImage(image=img)
            panel.imgtk = imgtk
            panel.config(image=imgtk)
            panel.update()
            if self.stop_flag:
                break
        cap.release()
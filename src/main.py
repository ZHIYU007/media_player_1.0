import tkinter as tk
from tkinter import ttk, Label
from threading import Thread
from PIL import Image, ImageTk
import time
import subprocess
import numpy as np
from onvif import ONVIFCamera
from tkinter import simpledialog, messagebox

class ONVIFController:
    def __init__(self, ip, port, username, password):
        self.cam = ONVIFCamera(ip, port, username, password)
        # 创建PTZ服务
        self.ptz = self.cam.create_ptz_service()
        self.media = self.cam.create_media_service()
        self.imaging = self.cam.create_imaging_service()
        
    def get_profiles(self):
        """获取摄像机配置集"""
        return self.media.GetProfiles()
    
    def absolute_move(self, pan, tilt, zoom, speed=0.5):
        """绝对移动"""
        req = self.ptz.create_type('AbsoluteMove')
        req.ProfileToken = self.get_profiles()[0].token
        req.Position = {
            'PanTilt': {'x': pan, 'y': tilt},
            'Zoom': {'x': zoom}
        }
        req.Speed = {
            'PanTilt': {'x': speed, 'y': speed},
            'Zoom': {'x': speed}
        }
        self.ptz.AbsoluteMove(req)
    
    def relative_move(self, pan, tilt, zoom, speed=0.5):
        """相对移动"""
        req = self.ptz.create_type('RelativeMove')
        req.ProfileToken = self.get_profiles()[0].token
        req.Translation = {
            'PanTilt': {'x': pan, 'y': tilt},
            'Zoom': {'x': zoom}
        }
        req.Speed = {
            'PanTilt': {'x': speed, 'y': speed},
            'Zoom': {'x': speed}
        }
        self.ptz.RelativeMove(req)
    
    def continuous_move(self, pan, tilt, zoom, timeout=1):
        """持续移动"""
        req = self.ptz.create_type('ContinuousMove')
        req.ProfileToken = self.get_profiles()[0].token
        req.Velocity = {
            'PanTilt': {'x': pan, 'y': tilt},
            'Zoom': {'x': zoom}
        }
        self.ptz.ContinuousMove(req)
        time.sleep(timeout)
        self.ptz.Stop({'ProfileToken': req.ProfileToken})

class PlayerWindow(ttk.Frame):
    def __init__(self, parent):
        ttk.Frame.__init__(self, parent)
        self.parent = parent
        
        # 创建ONVIF配置和PTZ控制面板
        self.create_ptz_controls()
        
        # 设置较低分辨率
        self.panel_width = 320
        self.panel_height = 180

        self.stream1_var = tk.StringVar(value="rtsp://172.20.4.131/live/VideoChannel1")
        self.stream2_var = tk.StringVar(value="rtsp://172.20.4.131/live/VideoChannel2")

        self.create_widgets()
        self.stop_flag = False
        self.panel1.bind("<Configure>", self.on_panel_resize)
        self.need_restart_stream = False
        self.onvif_controller = None

    def create_widgets(self):
        stream1_label = ttk.Label(self, text="Stream 1:")
        stream1_label.pack(anchor=tk.W, padx=10, pady=5)
        stream1_url_entry = ttk.Entry(self, textvariable=self.stream1_var, width=50)
        stream1_url_entry.pack(anchor=tk.W, padx=10, pady=5)
        stream2_label = ttk.Label(self, text="Stream 2:")
        stream2_label.pack(anchor=tk.W, padx=10, pady=5)
        stream2_url_entry = ttk.Entry(self, textvariable=self.stream2_var, width=50)
        stream2_url_entry.pack(anchor=tk.W, padx=10, pady=5)
        play_button = ttk.Button(self, text="Play Picture-in-Picture", command=self.play_pip)
        play_button.pack(anchor=tk.W, padx=10, pady=5)
        self.panel1 = Label(self)
        self.panel1.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.BOTH, expand=True)

    def on_panel_resize(self, event):
        try:
            # 计算新的高度以保持16:9的宽高比
            self.panel_width = event.width
            self.panel_height = int(self.panel_width * 9 / 16)
            self.panel1.config(width=self.panel_width, height=self.panel_height)
            self.need_restart_stream = True  # 标记需要重启流
        except Exception as e:
            print("处理窗口大小调整异常:", e)

    def play_pip(self):
        self.stop_flag = False
        Thread(target=self._start_pip_stream, daemon=True).start()

    def _start_pip_stream(self):
        def ffmpeg_stream(url, width, height):
            cmd = [
                'ffmpeg',       
                '-protocol_whitelist', 'rtsp,udp,rtp,file,http,https,tcp',
                '-i', url, # 设置输入URL为播放源
                '-f', 'rawvideo',  # 输出格式为原始视频流
                '-pix_fmt', 'rgb24',  # 输出格式为RGB24
                '-s', f'{width}x{height}',  # 输出分辨率
                '-r', '15', # 帧率
                '-'
            ]
            return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)

        w, h = self.panel_width, self.panel_height
        pip_w, pip_h = w // 3, h // 3
        proc1 = ffmpeg_stream(self.stream1_var.get(), w, h)
        proc2 = ffmpeg_stream(self.stream2_var.get(), pip_w, pip_h)
        frame_size1 = w * h * 3
        frame_size2 = pip_w * pip_h * 3

        error_count = 0  # 新增异常计数
        max_error_count = 10  # 连续异常阈值

        while not self.stop_flag:
            if self.need_restart_stream:
                proc1.terminate()
                proc2.terminate()
                w, h = self.panel_width, self.panel_height
                pip_w, pip_h = int(w // 2.3), int(h // 2.3)
                proc1 = ffmpeg_stream(self.stream1_var.get(), w, h)
                proc2 = ffmpeg_stream(self.stream2_var.get(), pip_w, pip_h)
                frame_size1 = w * h * 3
                frame_size2 = pip_w * pip_h * 3
                self.need_restart_stream = False
                error_count = 0

            start_time = time.time()
            try:
                raw_frame1 = proc1.stdout.read(frame_size1)
                raw_frame2 = proc2.stdout.read(frame_size2)
                # 如果读取超时或数据不完整，直接丢弃
                if len(raw_frame1) != frame_size1 or len(raw_frame2) != frame_size2:
                    error_count += 1
                    if error_count > max_error_count:
                        self.need_restart_stream = True
                    continue
                frame1 = np.frombuffer(raw_frame1, np.uint8).reshape((h, w, 3)).copy()
                frame2 = np.frombuffer(raw_frame2, np.uint8).reshape((pip_h, pip_w, 3))
                x_offset = w - pip_w - 10
                y_offset = h - pip_h - 10
                frame1[y_offset:y_offset+pip_h, x_offset:x_offset+pip_w] = frame2
                img = Image.fromarray(frame1)
                imgtk = ImageTk.PhotoImage(image=img)
                self.panel1.after(0, self._update_panel, imgtk)
                error_count = 0
            except Exception as e:
                print("解码异常:", e)
                error_count += 1
                if error_count > max_error_count:
                    self.need_restart_stream = True
                continue
            elapsed = time.time() - start_time
            # 不要sleep，直接下一帧
        proc1.terminate()
        proc2.terminate()

    def _update_panel(self, imgtk):
        self.panel1.imgtk = imgtk
        self.panel1.config(image=imgtk)

    def create_ptz_controls(self):
        """创建PTZ控制面板"""
        # ONVIF配置面板
        config_frame = ttk.LabelFrame(self.parent, text="ONVIF Configuration")
        config_frame.pack(side=tk.RIGHT, padx=10, pady=10, fill=tk.Y)

        # 输入控件
        ttk.Label(config_frame, text="IP:").grid(row=0, column=0, sticky=tk.W)
        self.ip_entry = ttk.Entry(config_frame, width=15)
        self.ip_entry.grid(row=0, column=1, padx=2)
        
        ttk.Label(config_frame, text="Port:").grid(row=1, column=0, sticky=tk.W)
        self.port_entry = ttk.Entry(config_frame, width=8)
        self.port_entry.insert(0, "1234")
        self.port_entry.grid(row=1, column=1, padx=2)
        
        ttk.Label(config_frame, text="User:").grid(row=2, column=0, sticky=tk.W)
        self.user_entry = ttk.Entry(config_frame, width=10)
        self.user_entry.insert(0, "admin")
        self.user_entry.grid(row=2, column=1, padx=2)
        
        ttk.Label(config_frame, text="Password:").grid(row=3, column=0, sticky=tk.W)
        self.pwd_entry = ttk.Entry(config_frame, width=10, show="*")
        self.pwd_entry.insert(0, "admin")
        self.pwd_entry.grid(row=3, column=1, padx=2)

        # 连接按钮
        connect_btn = ttk.Button(config_frame, text="Connect", command=self.connect_onvif)
        connect_btn.grid(row=4, columnspan=2, pady=5)

        # PTZ控制面板
        control_frame = ttk.LabelFrame(self.parent, text="PTZ Control")
        control_frame.pack(side=tk.RIGHT, padx=10, pady=10, fill=tk.Y)

        # 方向控制
        ttk.Button(control_frame, text="↑", command=lambda: self.move_camera(0, 0.1)).grid(row=0, column=1, pady=5)
        ttk.Button(control_frame, text="←", command=lambda: self.move_camera(-0.1, 0)).grid(row=1, column=0, pady=5)
        ttk.Button(control_frame, text="→", command=lambda: self.move_camera(0.1, 0)).grid(row=1, column=2, pady=5)
        ttk.Button(control_frame, text="↓", command=lambda: self.move_camera(0, -0.1)).grid(row=2, column=1, pady=5)
        
        # 变焦控制
        ttk.Label(control_frame, text="Zoom:").grid(row=3, column=0, pady=5)
        ttk.Button(control_frame, text="+", command=lambda: self.zoom_camera(0.1)).grid(row=3, column=1, pady=5)
        ttk.Button(control_frame, text="-", command=lambda: self.zoom_camera(-0.1)).grid(row=3, column=2, pady=5)

    def connect_onvif(self):
        """连接ONVIF摄像机"""
        try:
            ip = self.ip_entry.get()
            port = int(self.port_entry.get())
            username = self.user_entry.get()
            password = self.pwd_entry.get()
            
            # 空值校验
            if not all([ip, port, username, password]):
                raise ValueError("Missing required parameters")
                
            self.onvif_controller = ONVIFController(ip, port, username, password)
            messagebox.showinfo("Success", "Camera connected!")
        except Exception as e:
            messagebox.showerror("Error", f"Connection failed: {str(e)}")    

    def move_camera(self, pan, tilt):
        """移动摄像机"""
        if self.onvif_controller:
            self.onvif_controller.relative_move(pan, tilt, 0)
    
    def zoom_camera(self, zoom):
        """变焦控制"""
        if self.onvif_controller:
            self.onvif_controller.relative_move(0, 0, zoom)

if __name__ == "__main__":
    def main():
        root = tk.Tk()
        root.title("RTSP Player App")
        root.geometry("800x480")  # 增大默认窗口大小
        root.update()  # 强制刷新窗口尺寸
        root.minsize(640, 360)  # 设置最小窗口大小
        root.maxsize(1920, 1080)  # 设置最大窗口大小（可选）
        player_window = PlayerWindow(root)
        player_window.pack(fill=tk.BOTH, expand=True)
        root.mainloop()
    main()

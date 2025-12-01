import tkinter as tk
from tkinter import ttk, Label
from threading import Thread
from PIL import Image, ImageTk
import time
import subprocess
import numpy as np
from onvif import ONVIFCamera
from tkinter import simpledialog, messagebox
from tkinter.scrolledtext import ScrolledText
from zeep import helpers
from lxml import etree
from zeep.plugins import HistoryPlugin

class ONVIFController:
    def __init__(self, ip, port, username, password):
        self.history = HistoryPlugin()
        self.cam = ONVIFCamera(ip, port, username, password)
        self.ptz = self.cam.create_ptz_service()
        self.media = self.cam.create_media_service()
        self.imaging = self.cam.create_imaging_service()
        # 兼容主流onvif-py，插件加到_client.plugins
        try:
            self.ptz._client.plugins.append(self.history)
        except AttributeError:
            pass
        try:
            self.media._client.plugins.append(self.history)
        except AttributeError:
            pass
        try:
            self.imaging._client.plugins.append(self.history)
        except AttributeError:
            pass
        
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

    def relative_move_with_log(self, pan, tilt, zoom, speed=0.5):
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
        send_content = "未捕获到发送内容"
        recv_content = "未捕获到返回内容"
        try:
            self.ptz.RelativeMove(req)
            # 捕获最近一次请求和响应
            if hasattr(self.history, 'last_sent') and self.history.last_sent is not None:
                try:
                    send_content = etree.tostring(self.history.last_sent["envelope"], pretty_print=True, encoding='unicode')
                except Exception:
                    send_content = "未捕获到发送内容"
            if hasattr(self.history, 'last_received') and self.history.last_received is not None:
                try:
                    recv_content = etree.tostring(self.history.last_received["envelope"], pretty_print=True, encoding='unicode')
                except Exception:
                    recv_content = "未捕获到返回内容"
        except Exception as e:
            recv_content = f"Error: {e}"
        print("发送内容：", send_content)
        print("返回内容：", recv_content)
        print("history.last_sent:", getattr(self.history, 'last_sent', None))
        print("history.last_received:", getattr(self.history, 'last_received', None))
        return send_content, recv_content

class PlayerWindow(ttk.Frame):
    def __init__(self, parent):
        ttk.Frame.__init__(self, parent)
        self.parent = parent
        
        # 应用深色科技主题
        self.setup_theme()
        
        # 设置较低分辨率
        self.panel_width = 320
        self.panel_height = 180

        self.stream1_var = tk.StringVar(value="rtsp://172.20.4.99/live/VideoChannel1")
        self.stream2_var = tk.StringVar(value="rtsp://172.20.4.99/live/VideoChannel2")
        self.connection_status = tk.StringVar(value="未连接")
        self.stream_status = tk.StringVar(value="未播放")

        # 先创建右侧控制面板，确保它先显示
        self.create_ptz_controls()
        # 再创建左侧视频区域
        self.create_widgets()
        
        self.stop_flag = False
        self.panel1.bind("<Configure>", self.on_panel_resize)
        self.need_restart_stream = False
        self.onvif_controller = None
        self.send_text = None
        self.recv_text = None
        self.right_panel = None  # 保存右侧面板引用

    def setup_theme(self):
        """设置 PotPlayer 风格主题"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # PotPlayer 风格配色方案 - 深黑色主题
        bg_color = "#1a1a1a"  # 深黑背景（PotPlayer 风格）
        panel_bg = "#2a2a2a"  # 面板背景（稍亮）
        border_color = "#3a3a3a"  # 边框颜色
        text_color = "#e0e0e0"  # 主文字颜色（浅灰白）
        text_secondary = "#a0a0a0"  # 次要文字颜色
        accent_color = "#4a4a4a"  # 按钮背景
        hover_color = "#5a5a5a"  # 悬停颜色
        active_color = "#6a6a6a"  # 激活颜色
        entry_bg = "#2a2a2a"  # 输入框背景
        entry_fg = "#ffffff"  # 输入框文字
        highlight_color = "#0078d4"  # 高亮色（蓝色，PotPlayer 风格）
        
        # 配置样式
        style.configure('TFrame', background=bg_color, borderwidth=0)
        style.configure('TLabelFrame', background=panel_bg, foreground=text_color, 
                       borderwidth=1, relief='flat', bordercolor=border_color)
        style.configure('TLabelFrame.Label', background=panel_bg, foreground=text_color,
                       font=('Segoe UI', 9))
        style.configure('TLabel', background=bg_color, foreground=text_color,
                       font=('Segoe UI', 9))
        style.configure('TEntry', fieldbackground=entry_bg, foreground=entry_fg,
                       borderwidth=1, relief='flat', insertcolor=highlight_color,
                       bordercolor=border_color)
        style.configure('TButton', background=accent_color, foreground=text_color,
                       borderwidth=0, relief='flat', font=('Segoe UI', 9))
        style.map('TButton', 
                 background=[('active', hover_color), ('pressed', active_color)],
                 bordercolor=[('active', border_color)])
        
        # 自定义按钮样式 - 扁平化设计
        style.configure('Control.TButton', background=accent_color, foreground=text_color,
                       font=('Segoe UI', 11), width=4, borderwidth=0, relief='flat')
        style.map('Control.TButton', 
                 background=[('active', hover_color), ('pressed', active_color)])
        
        style.configure('Connect.TButton', background=highlight_color, foreground='white',
                       font=('Segoe UI', 9), borderwidth=0, relief='flat')
        style.map('Connect.TButton', background=[('active', '#0088e5'), ('pressed', '#0066b3')])
        
        style.configure('Play.TButton', background=highlight_color, foreground='white',
                       font=('Segoe UI', 10), borderwidth=0, relief='flat')
        style.map('Play.TButton', background=[('active', '#0088e5'), ('pressed', '#0066b3')])
        
        style.configure('Small.TButton', background=accent_color, foreground=text_color,
                       font=('Segoe UI', 8), borderwidth=0, relief='flat')
        style.map('Small.TButton', 
                 background=[('active', hover_color), ('pressed', active_color)])
        
        # 设置主窗口背景
        self.parent.configure(bg=bg_color)
        self.configure(style='TFrame')

    def create_widgets(self):
        """创建主界面组件 - PotPlayer 风格"""
        # 左侧主区域 - 视频流控制
        left_frame = ttk.Frame(self)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # 顶部工具栏 - PotPlayer 风格（紧凑、扁平）
        toolbar = tk.Frame(left_frame, bg="#1a1a1a", height=40)
        toolbar.pack(fill=tk.X, side=tk.TOP, padx=0, pady=0)
        toolbar.pack_propagate(False)
        
        # 左侧：流配置（紧凑布局）
        stream_config_frame = tk.Frame(toolbar, bg="#1a1a1a")
        stream_config_frame.pack(side=tk.LEFT, padx=8, pady=5)
        
        tk.Label(stream_config_frame, text="主:", bg="#1a1a1a", fg="#a0a0a0", 
                font=('Segoe UI', 8)).pack(side=tk.LEFT, padx=(0, 3))
        stream1_entry = ttk.Entry(stream_config_frame, textvariable=self.stream1_var, width=35)
        stream1_entry.pack(side=tk.LEFT, padx=(0, 8))
        
        tk.Label(stream_config_frame, text="画中画:", bg="#1a1a1a", fg="#a0a0a0", 
                font=('Segoe UI', 8)).pack(side=tk.LEFT, padx=(0, 3))
        stream2_entry = ttk.Entry(stream_config_frame, textvariable=self.stream2_var, width=25)
        stream2_entry.pack(side=tk.LEFT)
        
        # 中间：播放控制按钮
        control_frame = tk.Frame(toolbar, bg="#1a1a1a")
        control_frame.pack(side=tk.LEFT, padx=15, pady=5)
        
        play_button = ttk.Button(control_frame, text="▶", 
                                command=self.play_pip, style='Play.TButton', width=3)
        play_button.pack(side=tk.LEFT, padx=2)
        stop_button = ttk.Button(control_frame, text="⏸", 
                                command=self.stop_stream, style='Small.TButton', width=3)
        stop_button.pack(side=tk.LEFT, padx=2)
        
        # 右侧：状态显示
        status_frame = tk.Frame(toolbar, bg="#1a1a1a")
        status_frame.pack(side=tk.RIGHT, padx=10, pady=5)
        
        tk.Label(status_frame, text="状态:", bg="#1a1a1a", fg="#a0a0a0", 
                font=('Segoe UI', 8)).pack(side=tk.LEFT, padx=(0, 5))
        self.status_label = tk.Label(status_frame, textvariable=self.stream_status, 
                                    bg="#1a1a1a", fg="#00d4aa", font=('Segoe UI', 8, 'bold'))
        self.status_label.pack(side=tk.LEFT)
        
        # 视频显示面板 - PotPlayer 风格（无边框，纯黑背景）
        video_container = tk.Frame(left_frame, bg="#000000")
        video_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        self.panel1 = Label(video_container, bg="#000000", relief='flat', borderwidth=0)
        self.panel1.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # 占位文本 - PotPlayer 风格
        placeholder = Label(video_container, text="等待视频流...", 
                           bg="#000000", fg="#666666", font=('Segoe UI', 12))
        placeholder.place(relx=0.5, rely=0.5, anchor='center')
        self.panel1.placeholder = placeholder

    def stop_stream(self):
        """停止视频流"""
        self.stop_flag = True
        self.stream_status.set("已停止")
        self.status_label.config(fg="#a0a0a0")

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
        self.stream_status.set("连接中...")
        self.status_label.config(fg="#ffaa00")
        # 隐藏占位文本
        if hasattr(self.panel1, 'placeholder'):
            self.panel1.placeholder.destroy()
        Thread(target=self._start_pip_stream, daemon=True).start()

    def _start_pip_stream(self):
        def ffmpeg_stream(url, width, height):
            cmd = [
                'ffmpeg', 
                '-hwaccel', 'cuda',  # 使用NVIDIA硬件加速
                '-hwaccel_device', '0',
                '-c:v', 'h264_cuvid',  # NVIDIA解码    
                '-protocol_whitelist', 'rtsp,udp,rtp,file,http,https,tcp',
                '-i', url, # 设置输入URL为播放源
                '-f', 'rawvideo',  # 输出格式为原始视频流
                '-pix_fmt', 'rgb24',  # 输出格式为RGB24
                '-s', f'{width}x{height}',  # 输出分辨率
                '-r', '15', # 帧率
                '-'
            ]
            return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)

        try:
            w, h = self.panel_width, self.panel_height
            pip_w, pip_h = w // 3, h // 3
            proc1 = None
            proc2 = None
            
            try:
                proc1 = ffmpeg_stream(self.stream1_var.get(), w, h)
                proc2 = ffmpeg_stream(self.stream2_var.get(), pip_w, pip_h)
            except Exception as e:
                self.panel1.after(0, lambda: [self.stream_status.set("连接失败"), 
                                             self.status_label.config(fg="#ff6666")])
                print(f"启动流失败: {e}")
                return
            
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
            
        except Exception as e:
            print(f"流处理异常: {e}")
            self.panel1.after(0, lambda: [self.stream_status.set("播放错误"),
                                         self.status_label.config(fg="#ff6666")])
        finally:
            # 清理资源
            if proc1:
                try:
                    proc1.terminate()
                    proc1.wait(timeout=2)
                except:
                    proc1.kill()
            if proc2:
                try:
                    proc2.terminate()
                    proc2.wait(timeout=2)
                except:
                    proc2.kill()
            if not self.stop_flag:
                self.panel1.after(0, lambda: [self.stream_status.set("已停止"),
                                            self.status_label.config(fg="#a0a0a0")])

    def _update_panel(self, imgtk):
        self.panel1.imgtk = imgtk
        self.panel1.config(image=imgtk)
        self.stream_status.set("播放中")
        self.status_label.config(fg="#00d4aa")

    def create_ptz_controls(self):
        """创建PTZ控制面板 - PotPlayer 风格"""
        # 右侧控制面板容器 - 固定宽度，防止被挤压
        self.right_panel = ttk.Frame(self)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=0, pady=0)
        # 设置固定宽度和最小宽度
        self.right_panel.config(width=260)
        self.right_panel.pack_propagate(False)  # 防止子组件改变父组件大小
        
        right_panel = self.right_panel  # 使用局部变量以便后续代码使用
        
        # ONVIF配置面板 - PotPlayer 风格（紧凑、扁平）
        config_frame = ttk.LabelFrame(right_panel, text="ONVIF 连接")
        config_frame.pack(fill=tk.X, pady=(5, 5), padx=5)

        # 输入控件 - PotPlayer 风格（紧凑布局）
        input_grid = ttk.Frame(config_frame)
        input_grid.pack(fill=tk.X, padx=8, pady=8)
        
        # IP地址
        ttk.Label(input_grid, text="IP:", font=('Segoe UI', 8)).grid(row=0, column=0, sticky=tk.W, pady=3)
        self.ip_entry = ttk.Entry(input_grid, width=20)
        self.ip_entry.insert(0, "172.20.4.131")
        self.ip_entry.grid(row=0, column=1, padx=(5, 0), pady=3, sticky=tk.EW)
        
        # 端口
        ttk.Label(input_grid, text="端口:", font=('Segoe UI', 8)).grid(row=1, column=0, sticky=tk.W, pady=3)
        self.port_entry = ttk.Entry(input_grid, width=20)
        self.port_entry.insert(0, "1234")
        self.port_entry.grid(row=1, column=1, padx=(5, 0), pady=3, sticky=tk.EW)
        
        # 用户名
        ttk.Label(input_grid, text="用户:", font=('Segoe UI', 8)).grid(row=2, column=0, sticky=tk.W, pady=3)
        self.user_entry = ttk.Entry(input_grid, width=20)
        self.user_entry.insert(0, "admin")
        self.user_entry.grid(row=2, column=1, padx=(5, 0), pady=3, sticky=tk.EW)
        
        # 密码
        ttk.Label(input_grid, text="密码:", font=('Segoe UI', 8)).grid(row=3, column=0, sticky=tk.W, pady=3)
        self.pwd_entry = ttk.Entry(input_grid, width=20, show="*")
        self.pwd_entry.insert(0, "admin")
        self.pwd_entry.grid(row=3, column=1, padx=(5, 0), pady=3, sticky=tk.EW)
        
        input_grid.columnconfigure(1, weight=1)

        # 连接按钮和状态 - PotPlayer 风格
        btn_frame = ttk.Frame(config_frame)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 5))
        connect_btn = ttk.Button(btn_frame, text="连接", 
                                command=self.connect_onvif, style='Connect.TButton')
        connect_btn.pack(fill=tk.X)
        
        # 连接状态
        status_frame = ttk.Frame(config_frame)
        status_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(status_frame, text="状态:", font=('Segoe UI', 8)).pack(side=tk.LEFT)
        self.status_indicator = tk.Label(status_frame, textvariable=self.connection_status,
                                        bg="#2a2a2a", fg="#ff6666", font=('Segoe UI', 8, 'bold'))
        self.status_indicator.pack(side=tk.LEFT, padx=(5, 0))

        # PTZ控制面板 - PotPlayer 风格
        control_frame = ttk.LabelFrame(right_panel, text="PTZ 控制")
        control_frame.pack(fill=tk.X, pady=(0, 5), padx=5)

        # 步长设置 - 紧凑布局
        step_frame = ttk.Frame(control_frame)
        step_frame.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(step_frame, text="步长:", font=('Segoe UI', 8)).pack(side=tk.LEFT)
        self.step_var = tk.IntVar(value=10)
        step_entry = ttk.Entry(step_frame, textvariable=self.step_var, width=8)
        step_entry.pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(step_frame, text="(1-10000)", font=('Segoe UI', 7), 
                 foreground="#888888").pack(side=tk.LEFT, padx=(3, 0))

        # 方向控制 - PotPlayer 风格（紧凑按钮）
        direction_frame = ttk.Frame(control_frame)
        direction_frame.pack(padx=8, pady=6)
        
        ttk.Label(direction_frame, text="方向", font=('Segoe UI', 8)).grid(
            row=0, column=0, columnspan=3, pady=(0, 5))
        
        # 创建方向按钮网格 - 更小的按钮
        btn_up = ttk.Button(direction_frame, text="▲", 
                           command=lambda: self.move_camera(0, -self.get_step()),
                           style='Control.TButton', width=3)
        btn_up.grid(row=1, column=1, padx=2, pady=2)
        
        btn_left = ttk.Button(direction_frame, text="◄", 
                             command=lambda: self.move_camera(-self.get_step(), 0),
                             style='Control.TButton', width=3)
        btn_left.grid(row=2, column=0, padx=2, pady=2)
        
        btn_center = ttk.Button(direction_frame, text="●", 
                               command=lambda: self.move_camera(0, 0),
                               style='Control.TButton', width=3)
        btn_center.grid(row=2, column=1, padx=2, pady=2)
        
        btn_right = ttk.Button(direction_frame, text="►", 
                              command=lambda: self.move_camera(self.get_step(), 0),
                              style='Control.TButton', width=3)
        btn_right.grid(row=2, column=2, padx=2, pady=2)
        
        btn_down = ttk.Button(direction_frame, text="▼", 
                             command=lambda: self.move_camera(0, self.get_step()),
                             style='Control.TButton', width=3)
        btn_down.grid(row=3, column=1, padx=2, pady=2)

        # 变焦控制 - PotPlayer 风格
        zoom_frame = ttk.Frame(control_frame)
        zoom_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(zoom_frame, text="变焦", font=('Segoe UI', 8)).pack(anchor=tk.W, pady=(0, 3))
        
        zoom_btn_frame = ttk.Frame(zoom_frame)
        zoom_btn_frame.pack(fill=tk.X)
        ttk.Button(zoom_btn_frame, text="+ 放大", 
                  command=lambda: self.zoom_camera(0.1),
                  style='Small.TButton').pack(side=tk.LEFT, padx=(0, 3), fill=tk.X, expand=True)
        ttk.Button(zoom_btn_frame, text="- 缩小", 
                  command=lambda: self.zoom_camera(-0.1),
                  style='Small.TButton').pack(side=tk.LEFT, fill=tk.X, expand=True)

    def log_onvif(self, send_content, recv_content):
        pass

    def get_step(self):
        """获取步长，范围限制在1~10000，并归一化到0~1"""
        try:
            step = self.step_var.get()
            step = max(1, min(10000, step))
            return step / 10000.0  # 步长归一化到0~1
        except Exception:
            return 0.01

    def connect_onvif(self):
        """连接ONVIF摄像机"""
        try:
            ip = self.ip_entry.get()
            port = int(self.port_entry.get())
            username = self.user_entry.get()
            password = self.pwd_entry.get()
            
            # 空值校验
            if not all([ip, port, username, password]):
                raise ValueError("请填写所有必填项")
            
            self.connection_status.set("连接中...")
            self.status_indicator.config(fg="#ffaa00")
            self.parent.update()
                
            self.onvif_controller = ONVIFController(ip, port, username, password)
            self.connection_status.set("已连接")
            self.status_indicator.config(fg="#00d4aa")
            messagebox.showinfo("成功", "摄像机连接成功！")
        except Exception as e:
            self.connection_status.set("连接失败")
            self.status_indicator.config(fg="#ff6666")
            messagebox.showerror("错误", f"连接失败: {str(e)}")    

    def move_camera(self, pan, tilt):
        """移动摄像机"""
        if self.onvif_controller:
            send, recv = self.onvif_controller.relative_move_with_log(pan, tilt, 0)
            self.log_onvif(send, recv)
    
    def zoom_camera(self, zoom):
        """变焦控制"""
        if self.onvif_controller:
            send, recv = self.onvif_controller.relative_move_with_log(0, 0, zoom)
            self.log_onvif(send, recv)

if __name__ == "__main__":
    def main():
        root = tk.Tk()
        root.title("RTSP 视频播放器 - 专业版")
        root.geometry("1200x700")  # 增大默认窗口大小
        root.update()  # 强制刷新窗口尺寸
        root.minsize(1000, 600)  # 设置最小窗口大小，确保右侧面板有足够空间
        root.maxsize(1920, 1080)  # 设置最大窗口大小（可选）
        
        # 设置窗口图标（如果有的话）
        try:
            root.iconbitmap('icon.ico')
        except:
            pass
        
        player_window = PlayerWindow(root)
        player_window.pack(fill=tk.BOTH, expand=True)
        
        # 确保右侧面板始终可见
        def ensure_right_panel_visible(event=None):
            if hasattr(player_window, 'right_panel') and player_window.right_panel:
                # 强制更新布局，确保右侧面板显示
                player_window.right_panel.update_idletasks()
        
        # 绑定窗口大小变化事件
        root.bind('<Configure>', ensure_right_panel_visible)
        
        root.mainloop()
    main()

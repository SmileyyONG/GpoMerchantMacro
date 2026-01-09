import cv2
import numpy as np
import pyautogui
import time
import requests
from PIL import ImageGrab, Image, ImageTk
import json
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from pynput import keyboard
import os
import glob
import sys

class RobloxMerchantFinder:
    def __init__(self, webhook_url, compass_region=None, auto_interact=True, search_mode=False, show_detection=False, root=None, update_vis_callback=None):
        self.webhook_url = webhook_url
        self.compass_region = compass_region
        self.auto_interact = auto_interact
        self.search_mode = search_mode
        self.show_detection = show_detection
        self.root = root
        self.update_vis_callback = update_vis_callback
        self.loop_count = 0
        self.merchants_found = 0
        self.is_running = False
        
        pyautogui.FAILSAFE = True
        
    def capture_screen(self):
        if self.compass_region:
            x, y, w, h = self.compass_region
            screenshot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        else:
            screenshot = ImageGrab.grab()
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    
    def find_merchant_icon(self, screenshot, template_path, threshold=0.7):
        try:
            template = cv2.imread(template_path)
            if template is None:
                return False, 0, 0, 0
            
            gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
            gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            
            result = cv2.matchTemplate(gray_screenshot, gray_template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= threshold:
                h, w = gray_template.shape
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                
                if self.compass_region:
                    center_x += self.compass_region[0]
                    center_y += self.compass_region[1]
                
                return True, center_x, center_y, max_val
            
            return False, 0, 0, max_val
            
        except Exception as e:
            print(f"Error in template matching: {e}")
            return False, 0, 0, 0
    
    def calculate_compass_angle(self, center_x, center_y):
        if self.compass_region:
            compass_center_x = self.compass_region[0] + self.compass_region[2] // 2
            compass_center_y = self.compass_region[1] + self.compass_region[3] // 2
        else:
            screen_width, screen_height = pyautogui.size()
            compass_center_x = screen_width // 2
            compass_center_y = screen_height // 2
        
        dx = center_x - compass_center_x
        dy = center_y - compass_center_y
        angle = np.degrees(np.arctan2(dy, dx))
        angle = (angle + 360) % 360
        
        return angle
    
    def move_camera_to_merchant(self, angle):
        sensitivity_multiplier = 2.0
        mouse_move_x = int(np.cos(np.radians(angle)) * 200 * sensitivity_multiplier)
        pyautogui.moveRel(mouse_move_x, 0, duration=0.3)
        time.sleep(0.2)
    
    def interact_with_merchant(self, template_path, detection_threshold=0.7, check_interval=0.3):
        try:
            pyautogui.moveRel(0, -100, duration=0.2)
            time.sleep(0.3)
            
            pyautogui.press('1')
            time.sleep(0.2)
            
            pyautogui.keyDown('t')
            
            max_hold_time = 60
            start_time = time.time()
            
            while time.time() - start_time < max_hold_time:
                screenshot = self.capture_screen()
                found, _, _, confidence = self.find_merchant_icon(screenshot, template_path, detection_threshold)
                
                if not found:
                    pyautogui.keyUp('t')
                    return True
                
                time.sleep(check_interval)
            
            pyautogui.keyUp('t')
            return False
            
        except Exception as e:
            pyautogui.keyUp('t')
            print(f"Error during interaction: {e}")
            return False
    
    def send_discord_webhook(self, message, color=0x5865F2):
        if not self.webhook_url or self.webhook_url == "":
            return
            
        try:
            embed = {
                "embeds": [{
                    "title": "Roblox Merchant Finder",
                    "description": message,
                    "color": color,
                    "timestamp": datetime.utcnow().isoformat(),
                    "footer": {
                        "text": f"Loop {self.loop_count} | Merchants Found: {self.merchants_found}"
                    }
                }]
            }
            
            response = requests.post(self.webhook_url, json=embed, timeout=5)
            
        except Exception as e:
            print(f"Error sending webhook: {e}")
    
    def run_loop(self, template_path, detection_threshold=0.7):
        self.loop_count += 1
        
        screenshot = self.capture_screen()
        found, x, y, confidence = self.find_merchant_icon(
            screenshot, template_path, detection_threshold
        )
        
        # Visualization
        if self.show_detection:
            vis_screenshot = screenshot.copy()
            if found:
                h, w = cv2.imread(template_path).shape[:2]
                cv2.rectangle(vis_screenshot, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(vis_screenshot, f"Confidence: {confidence:.2%}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
            # Convert to PIL
            pil_image = Image.fromarray(cv2.cvtColor(vis_screenshot, cv2.COLOR_BGR2RGB))
            # Schedule update in main thread
            if self.update_vis_callback:
                self.root.after(0, lambda: self.update_vis_callback(pil_image))
        
        if found:
            self.merchants_found += 1
            angle = self.calculate_compass_angle(x, y)
            
            self.move_camera_to_merchant(angle)
            
            interacted = False
            if self.auto_interact:
                interacted = self.interact_with_merchant(template_path, detection_threshold)
            
            message = (
                f"**Traveling Merchant Detected**\n\n"
                f"Position: ({x}, {y})\n"
                f"Confidence: {confidence:.2%}\n"
                f"Angle: {angle:.1f} degrees\n"
                f"Camera rotated to merchant location"
            )
            
            if self.auto_interact:
                if interacted:
                    message += f"\nInteraction complete (pressed 1, held T until merchant disappeared)"
                else:
                    message += f"\nInteraction timed out"
            
            self.send_discord_webhook(message, color=0x57F287)
            
            return True, confidence, interacted
        else:
            # Search mode: rotate camera if not found
            if self.search_mode:
                pyautogui.moveRel(20, 0, duration=0.1)  # Small rotation to search
            
            message = (
                f"**Loop {self.loop_count} Completed**\n\n"
                f"Status: No merchant detected\n"
                f"Best Match: {confidence:.2%}"
            )
            self.send_discord_webhook(message, color=0xFEE75C)
            
            return False, confidence, False


class RegionSelector:
    def __init__(self, callback):
        self.callback = callback
        self.root = tk.Toplevel()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)
        self.root.attributes('-topmost', True)
        
        self.canvas = tk.Canvas(self.root, cursor="cross", bg='black')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.start_x = None
        self.start_y = None
        self.rect = None
        
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        instruction = tk.Label(
            self.canvas,
            text="Click and drag to select the compass region\nPress ESC to cancel",
            font=("Segoe UI", 16, "bold"),
            bg="#1a1a1a",
            fg="#e0e0e0"
        )
        self.canvas.create_window(
            self.root.winfo_screenwidth() // 2,
            50,
            window=instruction
        )
        
        self.root.bind("<Escape>", lambda e: self.cancel())
        
    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        
        if self.rect:
            self.canvas.delete(self.rect)
        
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline='#5865F2', width=3
        )
    
    def on_drag(self, event):
        cur_x, cur_y = event.x, event.y
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)
    
    def on_release(self, event):
        end_x, end_y = event.x, event.y
        
        x1, y1 = min(self.start_x, end_x), min(self.start_y, end_y)
        x2, y2 = max(self.start_x, end_x), max(self.start_y, end_y)
        
        region = (x1, y1, x2 - x1, y2 - y1)
        
        self.root.destroy()
        self.callback(region)
    
    def cancel(self):
        self.root.destroy()


class MacroGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Roblox Merchant Finder")
        self.root.geometry("650x1200")
        self.root.resizable(True, True)
        self.root.configure(bg='#1a1a1a')
        
        if getattr(sys, 'frozen', False):
            self.script_dir = os.path.dirname(sys.executable)
        else:
            self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.config_path = os.path.join(self.script_dir, "config.json")
        
        self.webhook_var = tk.StringVar(value=self.load_config("webhook", ""))
        self.template_var = tk.StringVar(value="")
        self.threshold_var = tk.DoubleVar(value=float(self.load_config("threshold", "0.75")))
        self.delay_var = tk.DoubleVar(value=float(self.load_config("delay", "5.0")))
        self.auto_interact_var = tk.BooleanVar(value=self.load_config("auto_interact", True))
        self.compass_region = self.load_config("region", None)
        self.search_mode_var = tk.BooleanVar(value=self.load_config("search_mode", False))
        self.show_detection_var = tk.BooleanVar(value=self.load_config("show_detection", False))
        
        self.detect_merchant_icon()
        
        self.finder = None
        self.macro_thread = None
        self.is_running = False
        self.vis_image = None
        
        self.listener = keyboard.GlobalHotKeys({
            '<f1>': self.toggle_macro,
            '<f2>': self.select_region
        })
        self.listener.start()
        
        self.setup_ui()
        self.update_status()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def detect_merchant_icon(self):
        search_patterns = [
            "merchant_icon.png",
            "merchant.png",
            "icon.png",
            "template.png"
        ]
        
        for pattern in search_patterns:
            full_path = os.path.join(self.script_dir, pattern)
            if os.path.exists(full_path):
                self.template_var.set(full_path)
                return
        
        png_files = glob.glob(os.path.join(self.script_dir, "*.png"))
        if png_files:
            self.template_var.set(png_files[0])
    
    def load_config(self, key, default):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                    return config.get(key, default)
        except:
            pass
        return default
    
    def save_config(self):
        config = {
            "webhook": self.webhook_var.get(),
            "threshold": self.threshold_var.get(),
            "delay": self.delay_var.get(),
            "auto_interact": self.auto_interact_var.get(),
            "region": self.compass_region,
            "search_mode": self.search_mode_var.get(),
            "show_detection": self.show_detection_var.get()
        }
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)
    
    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        header = tk.Frame(self.root, bg='#0d0d0d', height=100)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        title = tk.Label(
            header,
            text="ROBLOX MERCHANT FINDER",
            font=("Segoe UI", 22, "bold"),
            bg='#0d0d0d',
            fg='#e0e0e0'
        )
        title.pack(pady=15)
        
        subtitle = tk.Label(
            header,
            text="F1: Start/Stop  |  F2: Select Region",
            font=("Segoe UI", 10),
            bg='#0d0d0d',
            fg='#808080'
        )
        subtitle.pack()
        
        main = tk.Frame(self.root, bg='#1a1a1a')
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        webhook_frame = tk.LabelFrame(
            main,
            text="  Discord Webhook (Optional)  ",
            font=("Segoe UI", 10, "bold"),
            bg='#1a1a1a',
            fg='#b0b0b0',
            bd=2,
            relief=tk.GROOVE
        )
        webhook_frame.pack(fill=tk.X, pady=(0, 15))
        
        webhook_entry = tk.Entry(
            webhook_frame,
            textvariable=self.webhook_var,
            font=("Segoe UI", 10),
            bg='#2b2b2b',
            fg='#e0e0e0',
            insertbackground='#5865F2',
            relief=tk.FLAT,
            bd=5
        )
        webhook_entry.pack(fill=tk.X, padx=10, pady=10)
        
        settings_frame = tk.LabelFrame(
            main,
            text="  Detection Settings  ",
            font=("Segoe UI", 10, "bold"),
            bg='#1a1a1a',
            fg='#b0b0b0',
            bd=2,
            relief=tk.GROOVE
        )
        settings_frame.pack(fill=tk.X, pady=(0, 15))
        
        settings_inner = tk.Frame(settings_frame, bg='#1a1a1a')
        settings_inner.pack(fill=tk.X, padx=10, pady=10)
        
        thresh_frame = tk.Frame(settings_inner, bg='#1a1a1a')
        thresh_frame.grid(row=0, column=0, columnspan=3, sticky='ew', pady=(0, 15))
        
        thresh_label = tk.Label(
            thresh_frame,
            text="Confidence Threshold:",
            bg='#1a1a1a',
            fg='#e0e0e0',
            font=("Segoe UI", 10, "bold")
        )
        thresh_label.pack(anchor='w')
        
        thresh_desc = tk.Label(
            thresh_frame,
            text="How similar the image must be to detect the merchant (0.5 = 50%, 0.95 = 95%)\nHigher = more accurate but may miss matches | Lower = more detections but more false positives",
            bg='#1a1a1a',
            fg='#808080',
            font=("Segoe UI", 8),
            justify=tk.LEFT
        )
        thresh_desc.pack(anchor='w', pady=(2, 5))
        
        thresh_control = tk.Frame(settings_inner, bg='#1a1a1a')
        thresh_control.grid(row=1, column=0, columnspan=3, sticky='ew', pady=(0, 15))
        
        thresh_scale = tk.Scale(
            thresh_control,
            from_=0.5,
            to=0.95,
            variable=self.threshold_var,
            orient=tk.HORIZONTAL,
            bg='#2b2b2b',
            fg='#e0e0e0',
            troughcolor='#0d0d0d',
            activebackground='#5865F2',
            highlightthickness=0,
            resolution=0.01,
            showvalue=0
        )
        thresh_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.thresh_value = tk.Label(
            thresh_control,
            text=f"{self.threshold_var.get():.2f}",
            bg='#1a1a1a',
            fg='#5865F2',
            font=("Segoe UI", 11, "bold"),
            width=5
        )
        self.thresh_value.pack(side=tk.RIGHT)
        
        thresh_scale.config(command=lambda v: self.thresh_value.config(text=f"{float(v):.2f}"))
        
        delay_frame = tk.Frame(settings_inner, bg='#1a1a1a')
        delay_frame.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(0, 5))
        
        delay_label = tk.Label(
            delay_frame,
            text="Loop Delay:",
            bg='#1a1a1a',
            fg='#e0e0e0',
            font=("Segoe UI", 10, "bold")
        )
        delay_label.pack(anchor='w')
        
        delay_desc = tk.Label(
            delay_frame,
            text="Time to wait between detection attempts (in seconds)\nLower = faster scanning | Higher = less CPU usage",
            bg='#1a1a1a',
            fg='#808080',
            font=("Segoe UI", 8),
            justify=tk.LEFT
        )
        delay_desc.pack(anchor='w', pady=(2, 5))
        
        delay_control = tk.Frame(settings_inner, bg='#1a1a1a')
        delay_control.grid(row=3, column=0, columnspan=3, sticky='ew')
        
        delay_scale = tk.Scale(
            delay_control,
            from_=1.0,
            to=30.0,
            variable=self.delay_var,
            orient=tk.HORIZONTAL,
            bg='#2b2b2b',
            fg='#e0e0e0',
            troughcolor='#0d0d0d',
            activebackground='#5865F2',
            highlightthickness=0,
            resolution=0.5,
            showvalue=0
        )
        delay_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.delay_value = tk.Label(
            delay_control,
            text=f"{self.delay_var.get():.1f}s",
            bg='#1a1a1a',
            fg='#5865F2',
            font=("Segoe UI", 11, "bold"),
            width=5
        )
        self.delay_value.pack(side=tk.RIGHT)
        
        delay_scale.config(command=lambda v: self.delay_value.config(text=f"{float(v):.1f}s"))
        
        settings_inner.columnconfigure(0, weight=1)
        
        interact_frame = tk.Frame(settings_inner, bg='#1a1a1a')
        interact_frame.grid(row=4, column=0, columnspan=3, sticky='ew', pady=(15, 0))
        
        interact_check = tk.Checkbutton(
            interact_frame,
            text="Auto-interact with merchant (tilt up, press 1, hold T)",
            variable=self.auto_interact_var,
            bg='#1a1a1a',
            fg='#e0e0e0',
            selectcolor='#2b2b2b',
            activebackground='#1a1a1a',
            activeforeground='#e0e0e0',
            font=("Segoe UI", 10, "bold"),
            cursor='hand2'
        )
        interact_check.pack(anchor='w')
        
        interact_desc = tk.Label(
            interact_frame,
            text="When merchant is detected: tilts camera up, presses 1, holds T until merchant icon disappears",
            bg='#1a1a1a',
            fg='#808080',
            font=("Segoe UI", 8),
            justify=tk.LEFT
        )
        interact_desc.pack(anchor='w', pady=(2, 0))
        
        search_frame = tk.Frame(settings_inner, bg='#1a1a1a')
        search_frame.grid(row=5, column=0, columnspan=3, sticky='ew', pady=(15, 0))
        
        search_check = tk.Checkbutton(
            search_frame,
            text="Search mode (rotate camera when not found)",
            variable=self.search_mode_var,
            bg='#1a1a1a',
            fg='#e0e0e0',
            selectcolor='#2b2b2b',
            activebackground='#1a1a1a',
            activeforeground='#e0e0e0',
            font=("Segoe UI", 10, "bold"),
            cursor='hand2'
        )
        search_check.pack(anchor='w')
        
        search_desc = tk.Label(
            search_frame,
            text="When merchant not detected, slowly rotate camera to search different directions",
            bg='#1a1a1a',
            fg='#808080',
            font=("Segoe UI", 8),
            justify=tk.LEFT
        )
        search_desc.pack(anchor='w', pady=(2, 0))
        
        detection_frame = tk.Frame(settings_inner, bg='#1a1a1a')
        detection_frame.grid(row=6, column=0, columnspan=3, sticky='ew', pady=(15, 0))
        
        detection_check = tk.Checkbutton(
            detection_frame,
            text="Show detection visualization",
            variable=self.show_detection_var,
            bg='#1a1a1a',
            fg='#e0e0e0',
            selectcolor='#2b2b2b',
            activebackground='#1a1a1a',
            activeforeground='#e0e0e0',
            font=("Segoe UI", 10, "bold"),
            cursor='hand2'
        )
        detection_check.pack(anchor='w')
        
        detection_desc = tk.Label(
            detection_frame,
            text="Display detection visualization in the GUI with green rectangle around matches",
            bg='#1a1a1a',
            fg='#808080',
            font=("Segoe UI", 8),
            justify=tk.LEFT
        )
        detection_desc.pack(anchor='w', pady=(2, 0))
        
        region_frame = tk.LabelFrame(
            main,
            text="  Compass Region  ",
            font=("Segoe UI", 10, "bold"),
            bg='#1a1a1a',
            fg='#b0b0b0',
            bd=2,
            relief=tk.GROOVE
        )
        region_frame.pack(fill=tk.X, pady=(0, 15))
        
        region_inner = tk.Frame(region_frame, bg='#1a1a1a')
        region_inner.pack(fill=tk.X, padx=10, pady=10)
        
        self.region_label = tk.Label(
            region_inner,
            text=self.get_region_text(),
            bg='#1a1a1a',
            fg='#e0e0e0',
            font=("Segoe UI", 10),
            anchor='w'
        )
        self.region_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        region_btn = tk.Button(
            region_inner,
            text="Select (F2)",
            command=self.select_region,
            font=("Segoe UI", 9, "bold"),
            bg='#2b2b2b',
            fg='#e0e0e0',
            activebackground='#3d3d3d',
            activeforeground='#e0e0e0',
            relief=tk.FLAT,
            bd=0,
            cursor='hand2',
            padx=15,
            pady=5
        )
        region_btn.pack(side=tk.RIGHT)
        
        vis_frame = tk.LabelFrame(
            main,
            text="  Detection Visualization  ",
            font=("Segoe UI", 10, "bold"),
            bg='#1a1a1a',
            fg='#b0b0b0',
            bd=2,
            relief=tk.GROOVE
        )
        vis_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.vis_canvas = tk.Canvas(
            vis_frame,
            bg='#0d0d0d',
            height=400,
            width=800
        )
        self.vis_canvas.pack(padx=10, pady=10)
        
        status_frame = tk.LabelFrame(
            main,
            text="  Status Log  ",
            font=("Segoe UI", 10, "bold"),
            bg='#1a1a1a',
            fg='#b0b0b0',
            bd=2,
            relief=tk.GROOVE
        )
        status_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        status_frame.config(height=250)
        
        status_inner = tk.Frame(status_frame, bg='#1a1a1a')
        status_inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(status_inner, bg='#2b2b2b', troughcolor='#0d0d0d')
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.status_text = tk.Text(
            status_inner,
            height=25,
            font=("Consolas", 9),
            bg='#0d0d0d',
            fg='#e0e0e0',
            insertbackground='#5865F2',
            selectbackground='#2b2b2b',
            selectforeground='#e0e0e0',
            relief=tk.FLAT,
            bd=0,
            state='disabled',
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set
        )
        self.status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=self.status_text.yview)
        
        btn_frame = tk.Frame(main, bg='#1a1a1a')
        btn_frame.pack(fill=tk.X)
        
        self.start_btn = tk.Button(
            btn_frame,
            text="START MACRO (F1)",
            command=self.toggle_macro,
            font=("Segoe UI", 14, "bold"),
            bg='#5865F2',
            fg='#ffffff',
            activebackground='#4752C4',
            activeforeground='#ffffff',
            relief=tk.FLAT,
            bd=0,
            cursor='hand2',
            height=2
        )
        self.start_btn.pack(fill=tk.X)
        
    def update_vis(self, pil_image):
        self.vis_canvas.delete("all")
        self.vis_image = ImageTk.PhotoImage(pil_image)
        self.vis_canvas.create_image(0, 0, anchor=tk.NW, image=self.vis_image)
    
    def get_region_text(self):
        if self.compass_region:
            x, y, w, h = self.compass_region
            return f"Region: ({x}, {y}) - Size: {w}x{h}px"
        return "No region selected (using full screen)"
    
    def select_region(self):
        if self.is_running:
            messagebox.showwarning("Warning", "Stop the macro before selecting a new region!")
            return
        
        self.root.withdraw()
        time.sleep(0.3)
        
        RegionSelector(self.on_region_selected)
    
    def on_region_selected(self, region):
        self.compass_region = region
        self.region_label.config(text=self.get_region_text())
        self.save_config()
        self.root.deiconify()
        self.log_status(f"Region selected: {region}")
    
    def toggle_macro(self):
        if self.is_running:
            self.stop_macro()
        else:
            self.start_macro()
    
    def start_macro(self):
        if not self.template_var.get() or not os.path.exists(self.template_var.get()):
            messagebox.showerror(
                "Error",
                f"Merchant icon template not found!\n\nAdd 'merchant_icon.png' to:\n{self.script_dir}"
            )
            return
        
        self.is_running = True
        self.start_btn.config(
            text="STOP MACRO (F1)",
            bg='#ED4245',
            fg='#ffffff',
            activebackground='#C03537'
        )
        
        self.finder = RobloxMerchantFinder(
            webhook_url=self.webhook_var.get(),
            compass_region=self.compass_region,
            auto_interact=self.auto_interact_var.get(),
            search_mode=self.search_mode_var.get(),
            show_detection=self.show_detection_var.get(),
            root=self.root,
            update_vis_callback=self.update_vis
        )
        
        self.save_config()
        self.log_status("Macro started")
        self.finder.send_discord_webhook("**Macro Started**\n\nSearching for traveling merchant...", color=0x5865F2)
        
        self.macro_thread = threading.Thread(target=self.run_macro, daemon=True)
        self.macro_thread.start()
    
    def stop_macro(self):
        self.is_running = False
        self.start_btn.config(
            text="START MACRO (F1)",
            bg='#5865F2',
            fg='#ffffff',
            activebackground='#4752C4'
        )
        
        self.vis_canvas.delete("all")
        
        if self.finder:
            self.finder.send_discord_webhook(
                f"**Macro Stopped**\n\nTotal Loops: {self.finder.loop_count}\nMerchants Found: {self.finder.merchants_found}",
                color=0xED4245
            )
        
        self.log_status("Macro stopped")
    
    def run_macro(self):
        try:
            while self.is_running:
                found, confidence, interacted = self.finder.run_loop(
                    self.template_var.get(),
                    self.threshold_var.get()
                )
                
                status = "MERCHANT FOUND" if found else "Not found"
                if found and interacted:
                    status += " + Interacted successfully"
                self.log_status(f"Loop {self.finder.loop_count}: {status} (Confidence: {confidence:.2%})")
                
                time.sleep(self.delay_var.get())
                
        except Exception as e:
            self.log_status(f"Error: {e}")
            self.is_running = False
            self.root.after(0, lambda: self.start_btn.config(
                text="START MACRO (F1)",
                bg='#5865F2',
                fg='#ffffff',
                activebackground='#4752C4'
            ))
    
    def log_status(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status_text.config(state='normal')
        self.status_text.insert('end', f"[{timestamp}] {message}\n")
        self.status_text.see('end')  # Auto-scroll to bottom
        
        lines = self.status_text.get('1.0', tk.END).split('\n')
        if len(lines) > 100:
            self.status_text.delete('1.0', '2.0')  # Remove from top
        
        self.status_text.config(state='disabled')
        
        print(f"[{timestamp}] {message}")  # Also print to console
    
    def update_status(self):
        if self.finder:
            stats = f"Loops: {self.finder.loop_count} | Found: {self.finder.merchants_found}"
            self.root.title(f"Roblox Merchant Finder - {stats}")
        
        self.root.after(1000, self.update_status)
    
    def on_close(self):
        if self.is_running:
            if messagebox.askokcancel("Quit", "Macro is running. Stop and quit?"):
                self.stop_macro()
                time.sleep(0.5)
                self.listener.stop()
                self.root.destroy()
        else:
            self.listener.stop()
            self.root.destroy()
    
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = MacroGUI()
    app.run()
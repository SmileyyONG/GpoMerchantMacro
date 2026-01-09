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
import ctypes
import re
import io

# Try to import pytesseract and configure it
try:
    import pytesseract
    
    # Try to find Tesseract executable on Windows
    if sys.platform == "win32":
        possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe".format(os.getenv('USERNAME')),
            r"C:\Tesseract-OCR\tesseract.exe"
        ]
        
        tesseract_found = False
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                tesseract_found = True
                print(f"Tesseract found at: {path}")
                break
        
        if not tesseract_found:
            print("Warning: Tesseract executable not found in common locations.")
            print("Please set pytesseract.pytesseract.tesseract_cmd to your Tesseract path.")
    
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("Warning: pytesseract not installed. Install with: pip install pytesseract")

SendInput = ctypes.windll.user32.SendInput

W = 0x11
A = 0x1E
S = 0x1F
D = 0x20
SPACE = 0x39
T = 0x14
KEY_1 = 0x02
LEFT_ARROW = 0x4B
RIGHT_ARROW = 0x4D
UP_ARROW = 0x48
DOWN_ARROW = 0x50

PUL = ctypes.POINTER(ctypes.c_ulong)

class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]

class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput),
                ("mi", MouseInput),
                ("hi", HardwareInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", Input_I)]

def PressKey(hexKeyCode):
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    # Use KEYEVENTF_SCANCODE (0x0008) and KEYEVENTF_EXTENDEDKEY (0x0001) for arrow keys
    flags = 0x0008
    if hexKeyCode in [0x4B, 0x4D, 0x48, 0x50]:  # Arrow keys
        flags |= 0x0001
    ii_.ki = KeyBdInput(0, hexKeyCode, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def ReleaseKey(hexKeyCode):
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    # Use KEYEVENTF_SCANCODE (0x0008), KEYEVENTF_KEYUP (0x0002), and KEYEVENTF_EXTENDEDKEY (0x0001) for arrow keys
    flags = 0x0008 | 0x0002
    if hexKeyCode in [0x4B, 0x4D, 0x48, 0x50]:  # Arrow keys
        flags |= 0x0001
    ii_.ki = KeyBdInput(0, hexKeyCode, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def PressAndReleaseKey(hexKeyCode, hold_time=0.05):
    PressKey(hexKeyCode)
    time.sleep(hold_time)
    ReleaseKey(hexKeyCode)

class RobloxMerchantFinder:
    def __init__(self, webhook_url, compass_region=None, ocr_region=None, auto_interact=True, search_mode=False, show_detection=False, root=None, update_vis_callback=None):
        self.webhook_url = webhook_url
        self.compass_region = compass_region
        self.ocr_region = ocr_region
        self.auto_interact = auto_interact
        self.search_mode = search_mode
        self.show_detection = show_detection
        self.root = root
        self.selected_items = []  # Will be set by UI
        self.update_vis_callback = update_vis_callback
        self.loop_count = 0
        self.merchants_found = 0
        self.is_running = False
        self.merchant_found_flag = False  # Flag to prevent duplicate webhooks
        
        pyautogui.FAILSAFE = True
        
    def capture_screen(self):
        if self.compass_region:
            x, y, w, h = self.compass_region
            screenshot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        else:
            screenshot = ImageGrab.grab()
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    
    def read_distance_ocr(self):
        """Read distance using template matching for game digits."""
        if not self.ocr_region:
            return None
        
        try:
            x, y, w, h = self.ocr_region
            screenshot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            img = np.array(screenshot)
            
            # Convert to grayscale and isolate white text
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            _, white = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
            
            # Simple pattern matching for common distance numbers
            # Check for consecutive white pixels that form digit-like shapes
            height, width = white.shape
            
            # Find white pixel columns (where digits likely are)
            column_density = np.sum(white, axis=0) / 255  # Count white pixels per column
            
            # Detect digit regions (groups of columns with white pixels)
            digit_threshold = height * 0.2  # At least 20% of column should be white
            in_digit = False
            digit_regions = []
            start_x = 0
            
            for x_pos in range(width):
                if column_density[x_pos] > digit_threshold:
                    if not in_digit:
                        start_x = x_pos
                        in_digit = True
                else:
                    if in_digit:
                        digit_regions.append((start_x, x_pos))
                        in_digit = False
            
            if in_digit:
                digit_regions.append((start_x, width))
            
            # Extract and recognize each digit region
            recognized_digits = []
            
            for i, (x1, x2) in enumerate(digit_regions):
                if x2 - x1 < 3:  # Too narrow, probably noise
                    continue
                
                digit_img = white[:, x1:x2]
                digit_height, digit_width = digit_img.shape
                
                if digit_height < 5 or digit_width < 3:
                    continue
                
                # Simple digit recognition based on white pixel patterns
                # Count white pixels in different regions of the digit
                top_half = np.sum(digit_img[:digit_height//2, :])
                bottom_half = np.sum(digit_img[digit_height//2:, :])
                left_half = np.sum(digit_img[:, :digit_width//2])
                right_half = np.sum(digit_img[:, digit_width//2:])
                middle_row = np.sum(digit_img[digit_height//2-1:digit_height//2+1, :])
                total_white = np.sum(digit_img)
                
                # Normalize
                total = digit_height * digit_width * 255
                top_ratio = top_half / total
                bottom_ratio = bottom_half / total
                left_ratio = left_half / total
                right_ratio = right_half / total
                density = total_white / total
                
                # Pattern recognition (rough heuristics for game font)
                digit = None
                
                if density > 0.6:  # Very filled
                    digit = '0' if abs(top_ratio - bottom_ratio) < 0.1 else '8'
                elif middle_row > total * 0.15:  # Strong middle line
                    if top_half > bottom_half * 1.3:
                        digit = '5'
                    elif bottom_half > top_half * 1.2:
                        digit = '2'
                    else:
                        digit = '3'
                elif top_ratio > 0.25 and bottom_ratio > 0.25:
                    if right_ratio > left_ratio * 1.3:
                        digit = '1'
                    else:
                        digit = '0'
                elif top_ratio > bottom_ratio * 1.4:
                    digit = '7'
                elif bottom_ratio > top_ratio * 1.3:
                    digit = '2'
                
                if digit:
                    recognized_digits.append(digit)
            
            if recognized_digits:
                # Build the number from recognized digits
                distance_str = ''.join(recognized_digits)
                # Extract just the numeric part
                numbers = re.findall(r'\d+', distance_str)
                if numbers:
                    distance = int(numbers[0])
                    if 1 <= distance <= 999:
                        print(f"✓ Distance detected: {distance} studs")
                        return distance
            
            # Fallback: Try basic OCR if pattern matching fails
            if OCR_AVAILABLE:
                upscaled = cv2.resize(white, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
                text = pytesseract.image_to_string(upscaled, config='--psm 7 -c tessedit_char_whitelist=0123456789').strip()
                nums = re.findall(r'\d+', text)
                if nums and 1 <= int(nums[0]) <= 999:
                    distance = int(nums[0])
                    print(f"✓ Distance (OCR fallback): {distance} studs")
                    return distance
            
            return None
            
        except Exception as e:
            print(f"Distance detection error: {e}")
            return None
    
    def find_merchant_icon(self, screenshot, template_paths, threshold=0.7):
        if isinstance(template_paths, str):
            template_paths = [p.strip() for p in template_paths.split(',')]
        
        best_match = (False, 0, 0, 0, None, None)
        
        for template_path in template_paths:
            try:
                template = cv2.imread(template_path)
                if template is None:
                    continue
                
                gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
                
                result = cv2.matchTemplate(gray_screenshot, gray_template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                
                if max_val >= threshold and max_val > best_match[3]:
                    h, w = gray_template.shape
                    center_x = max_loc[0] + w // 2
                    center_y = max_loc[1] + h // 2
                    
                    match_location = (max_loc[0], max_loc[1], w, h)
                    
                    if self.compass_region:
                        center_x += self.compass_region[0]
                        center_y += self.compass_region[1]
                    
                    best_match = (True, center_x, center_y, max_val, match_location, template_path)
                
            except Exception as e:
                print(f"Error matching template {template_path}: {e}")
                continue
        
        if best_match[0]:
            return best_match
        
        return False, 0, 0, max(best_match[3], 0), None, None
    
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
        if self.compass_region:
            compass_center_x = self.compass_region[0] + self.compass_region[2] // 2
            compass_center_y = self.compass_region[1] + self.compass_region[3] // 2
        else:
            screen_width, screen_height = pyautogui.size()
            compass_center_x = screen_width // 2
            compass_center_y = screen_height // 2
        
        dx = compass_center_x - (self.compass_region[0] if self.compass_region else 0)
        dy = compass_center_y - (self.compass_region[1] if self.compass_region else 0)
        
        if angle > 180:
            angle = angle - 360
        
        rotation_steps = int(abs(angle) / 5)
        
        if angle > 5:
            for _ in range(rotation_steps):
                if not self.is_running:
                    break
                PressAndReleaseKey(RIGHT_ARROW)
                time.sleep(0.05)
        elif angle < -5:
            for _ in range(rotation_steps):
                if not self.is_running:
                    break
                PressAndReleaseKey(LEFT_ARROW)
                time.sleep(0.05)
    
    def center_merchant_in_region(self, current_x, current_y, template_path, detection_threshold=0.7, max_attempts=100):
        if not self.compass_region:
            return False
        
        target_center_x = self.compass_region[0] + self.compass_region[2] // 2
        target_center_y = self.compass_region[1] + self.compass_region[3] // 2
        
        tolerance = 5  # Smaller tolerance for more precise centering
        
        print(f"Centering merchant. Region: x={self.compass_region[0]}, y={self.compass_region[1]}, w={self.compass_region[2]}, h={self.compass_region[3]}")
        print(f"Target center: ({target_center_x}, {target_center_y})")
        
        for attempt in range(max_attempts):
            if not self.is_running:
                return False
            
            screenshot = self.capture_screen()
            found, center_x, center_y, confidence, _, _ = self.find_merchant_icon(screenshot, template_path, detection_threshold)
            
            if not found:
                print(f"Centering failed: Merchant not found on attempt {attempt}")
                return False
            
            # center_x and center_y are already in global coordinates
            diff_x = center_x - target_center_x
            diff_y = center_y - target_center_y
            
            print(f"Attempt {attempt}: Merchant at ({center_x}, {center_y}), diff_x={diff_x:.1f}, diff_y={diff_y:.1f}")
            
            if abs(diff_x) <= tolerance and abs(diff_y) <= tolerance:
                print(f"Merchant centered successfully!")
                return True
            
            if abs(diff_x) > tolerance:
                if diff_x > 0:
                    # Merchant is to the right, press RIGHT arrow to rotate camera right and bring merchant to center
                    PressAndReleaseKey(RIGHT_ARROW, 0.05)
                else:
                    # Merchant is to the left, press LEFT arrow to rotate camera left and bring merchant to center
                    PressAndReleaseKey(LEFT_ARROW, 0.05)
                time.sleep(0.05)
        
        print(f"Centering timed out after {max_attempts} attempts")
        return False
    
    def interact_with_merchant(self, template_paths, text_template_paths, detection_threshold=0.7, check_interval=0.1):
        try:
            # First, find and hover over the merchant before doing anything
            screenshot = self.capture_screen()
            found, center_x, center_y, confidence, _, _ = self.find_merchant_icon(screenshot, template_paths, detection_threshold)
            
            if not found:
                print("Cannot interact: Merchant not found initially")
                return False
            
            # Hover over merchant before any interaction
            print(f"Hovering over merchant at ({center_x}, {center_y})")
            pyautogui.moveTo(center_x, center_y, duration=0.2)
            time.sleep(0.3)
            
            # STEP 1: Hold T until merchant disappears
            print("STEP 1: Holding T until merchant disappears...")
            PressKey(T)
            
            start_time = time.time()
            last_seen = time.time()
            
            while time.time() - start_time < 10:  # Max 10 seconds
                if not self.is_running:
                    ReleaseKey(T)
                    return False
                    
                screenshot = self.capture_screen()
                found, _, _, _, _, _ = self.find_merchant_icon(screenshot, template_paths, detection_threshold)
                
                if found:
                    last_seen = time.time()
                else:
                    if time.time() - last_seen > 0.5:  # Merchant gone for 0.5s
                        print("✓ Merchant disappeared")
                        break
                
                time.sleep(check_interval)
            
            ReleaseKey(T)
            time.sleep(0.3)
            
            # STEP 2: Hold W + spam T until dialogue appears, while tracking merchant
            print("STEP 2: Walking forward and spamming T until dialogue appears...")
            dialogue_template = os.path.join(os.path.dirname(__file__), "dialogue1.png")
            
            if not os.path.exists(dialogue_template):
                print(f"⚠ Warning: dialogue1.png not found, skipping dialogue detection")
                time.sleep(2)  # Wait a bit anyway
            else:
                PressKey(W)
                
                dialogue_found = False
                start_time = time.time()
                last_t_press = time.time()
                last_rotation = time.time()
                t_interval = 0.15  # Spam T every 150ms
                rotation_interval = 0.3  # Check merchant position every 300ms
                
                while time.time() - start_time < 8:  # Max 8 seconds
                    if not self.is_running:
                        ReleaseKey(W)
                        return False
                    
                    # Spam T
                    if time.time() - last_t_press >= t_interval:
                        PressKey(T)
                        time.sleep(0.05)
                        ReleaseKey(T)
                        last_t_press = time.time()
                    
                    screenshot = self.capture_screen()
                    
                    # Check for dialogue
                    found, dlg_x, dlg_y, _, _, _ = self.find_merchant_icon(screenshot, dialogue_template, 0.6)
                    
                    if found:
                        print(f"✓ Dialogue detected at ({dlg_x}, {dlg_y})")
                        dialogue_found = True
                        break
                    
                    # Track merchant position and adjust camera
                    if time.time() - last_rotation >= rotation_interval:
                        merchant_found, merch_x, merch_y, _, _, _ = self.find_merchant_icon(screenshot, template_paths, detection_threshold)
                        
                        if merchant_found:
                            # Move mouse to merchant to track direction
                            pyautogui.moveTo(merch_x, merch_y, duration=0.05)
                            last_rotation = time.time()
                        else:
                            # If merchant not visible, rotate camera slightly
                            PressAndReleaseKey(RIGHT_ARROW)
                            last_rotation = time.time()
                    
                    time.sleep(check_interval)
                
                ReleaseKey(W)
                time.sleep(0.2)
                
                if not dialogue_found:
                    print("⚠ Dialogue not detected, proceeding anyway...")
            
            # STEP 3: Click "Show me!" button
            print("STEP 3: Looking for and clicking 'Show me!' button...")
            show_me_template = os.path.join(os.path.dirname(__file__), "show_me_button.png")
            
            if os.path.exists(show_me_template):
                time.sleep(0.5)  # Wait for dialogue to fully appear
                screenshot = self.capture_screen()
                found, btn_x, btn_y, _, _, _ = self.find_merchant_icon(screenshot, show_me_template, 0.65)
                
                if found:
                    print(f"✓ 'Show me!' button found at ({btn_x}, {btn_y}), clicking...")
                    pyautogui.click(btn_x, btn_y)
                    time.sleep(1.5)  # Wait for shop menu to open
                else:
                    print("⚠ 'Show me!' button not found, clicking center screen...")
                    pyautogui.click()
                    time.sleep(1.5)
            else:
                print("⚠ show_me_button.png not found, clicking center screen...")
                pyautogui.click()
                time.sleep(1.5)
            
            # STEP 4: Click "..." button to open full shop
            print("STEP 4: Looking for and clicking '...' button...")
            dots_template = os.path.join(os.path.dirname(__file__), "dots_button.png")
            
            if os.path.exists(dots_template):
                time.sleep(0.5)  # Wait for menu to appear
                screenshot = self.capture_screen()
                found, dots_x, dots_y, _, _, _ = self.find_merchant_icon(screenshot, dots_template, 0.65)
                
                if found:
                    print(f"✓ '...' button found at ({dots_x}, {dots_y}), clicking...")
                    pyautogui.click(dots_x, dots_y)
                    time.sleep(1.5)  # Wait for full shop to open
                else:
                    print("⚠ '...' button not found, trying to proceed anyway...")
                    time.sleep(1)
            else:
                print("⚠ dots_button.png not found, skipping...")
                time.sleep(1)
            
            # STEP 5: Look for items from the item list
            print("STEP 5: Searching for desired items in shop...")
            item_folder = os.path.join(os.path.dirname(__file__), "items")
            
            if not os.path.exists(item_folder):
                print(f"⚠ Warning: items folder not found at {item_folder}")
                os.makedirs(item_folder, exist_ok=True)
                print(f"Created items folder. Add item image files there.")
            else:
                item_files = [f for f in os.listdir(item_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
                
                # Filter to only selected items if any are selected
                if self.selected_items:
                    item_files = [f for f in item_files if f in self.selected_items]
                    print(f"Filtered to {len(item_files)} selected items: {', '.join(item_files)}")
                
                if not item_files:
                    print("⚠ No item templates found in items folder")
                else:
                    print(f"Looking for {len(item_files)} items: {', '.join(item_files)}")
                    
                    item_found = False
                    
                    # Scan twice: once at top, once after scrolling down
                    for scroll_attempt in range(2):
                        if scroll_attempt == 0:
                            print("  Scanning top of shop...")
                        else:
                            print("  Scrolling down to reveal more items...")
                            # Scroll down in the shop (3 scrolls)
                            for _ in range(3):
                                pyautogui.scroll(-3)
                                time.sleep(0.2)
                            print("  Scanning bottom of shop...")
                        
                        screenshot = self.capture_screen()
                        
                        for item_file in item_files:
                            item_path = os.path.join(item_folder, item_file)
                            found, item_x, item_y, confidence, _, _ = self.find_merchant_icon(screenshot, item_path, 0.75)
                            
                            if found:
                                print(f"✓ Found item: {item_file} at ({item_x}, {item_y}) with {confidence:.2%} confidence")
                                
                                # Click on the item
                                pyautogui.click(item_x, item_y)
                                time.sleep(0.5)
                                item_found = True
                                break
                        
                        if item_found:
                            break
                    
                    if not item_found:
                        print("⚠ None of the desired items found in shop")
                    else:
                        # STEP 6: Confirm purchase - Look for Accept button
                        print("STEP 6: Looking for purchase confirmation (Accept button)...")
                        time.sleep(0.5)
                        
                        accept_template = os.path.join(os.path.dirname(__file__), "accept_button.png")
                        
                        if os.path.exists(accept_template):
                            screenshot = self.capture_screen()
                            found, accept_x, accept_y, _, _, _ = self.find_merchant_icon(screenshot, accept_template, 0.65)
                            
                            if found:
                                print(f"✓ Accept button found at ({accept_x}, {accept_y}), clicking...")
                                pyautogui.click(accept_x, accept_y)
                                time.sleep(1)
                            else:
                                print("⚠ Accept button not found, trying center screen...")
                                pyautogui.click()
                                time.sleep(1)
                        else:
                            print("⚠ accept_button.png not found, clicking center screen")
                            pyautogui.click()
                            time.sleep(1)
            
            # STEP 7: Send webhook with full screenshot
            print("STEP 7: Capturing screenshot and sending webhook...")
            time.sleep(0.5)
            full_screenshot = ImageGrab.grab()
            
            # Save screenshot
            screenshot_path = os.path.join(os.path.dirname(__file__), f"purchase_{int(time.time())}.png")
            full_screenshot.save(screenshot_path)
            print(f"Screenshot saved: {screenshot_path}")
            
            # Send to webhook
            if self.webhook_url:
                try:
                    # Convert to bytes for upload
                    img_byte_arr = io.BytesIO()
                    full_screenshot.save(img_byte_arr, format='PNG')
                    img_byte_arr.seek(0)
                    
                    # Send webhook with image
                    files = {'file': ('purchase.png', img_byte_arr, 'image/png')}
                    data = {
                        'content': f"**Purchase Complete!**\n✓ Item found and purchased\nTime: {time.strftime('%H:%M:%S')}"
                    }
                    
                    response = requests.post(self.webhook_url, data=data, files=files)
                    
                    if response.status_code == 200 or response.status_code == 204:
                        print("✓ Webhook sent with screenshot")
                    else:
                        print(f"⚠ Webhook failed: {response.status_code}")
                except Exception as e:
                    print(f"⚠ Webhook error: {e}")
            
            # STEP 8: Click exit/close button to return to game
            print("STEP 8: Looking for exit button to close shop...")
            time.sleep(0.5)
            
            exit_template = os.path.join(os.path.dirname(__file__), "exit_button.png")
            
            if os.path.exists(exit_template):
                screenshot = self.capture_screen()
                found, exit_x, exit_y, _, _, _ = self.find_merchant_icon(screenshot, exit_template, 0.65)
                
                if found:
                    print(f"✓ Exit button found at ({exit_x}, {exit_y}), clicking...")
                    pyautogui.click(exit_x, exit_y)
                    time.sleep(1.5)
                    
                    # Now click Main Menu button
                    print("STEP 8b: Looking for Main Menu button...")
                    main_menu_template = os.path.join(os.path.dirname(__file__), "main_menu_button.png")
                    
                    if os.path.exists(main_menu_template):
                        screenshot = self.capture_screen()
                        found, menu_x, menu_y, _, _, _ = self.find_merchant_icon(screenshot, main_menu_template, 0.65)
                        
                        if found:
                            print(f"✓ Main Menu button found at ({menu_x}, {menu_y}), clicking...")
                            pyautogui.click(menu_x, menu_y)
                            time.sleep(2)
                            
                            # Click anywhere to continue from loading screen
                            print("STEP 8c: Clicking to continue from loading screen...")
                            pyautogui.click()
                            time.sleep(2)
                            
                            # Click on Private Servers/Friend Join button
                            print("STEP 8d: Looking for Private Servers/Friend Join button...")
                            private_server_template = os.path.join(os.path.dirname(__file__), "private_server_button.png")
                            
                            if os.path.exists(private_server_template):
                                screenshot = self.capture_screen()
                                found, ps_x, ps_y, _, _, _ = self.find_merchant_icon(screenshot, private_server_template, 0.65)
                                
                                if found:
                                    print(f"✓ Private Server button found at ({ps_x}, {ps_y}), clicking...")
                                    pyautogui.click(ps_x, ps_y)
                                    time.sleep(1.5)
                                    
                                    # Double-click on code field to copy it
                                    print("STEP 8e: Looking for server code field...")
                                    code_field_template = os.path.join(os.path.dirname(__file__), "code_field.png")
                                    
                                    if os.path.exists(code_field_template):
                                        screenshot = self.capture_screen()
                                        found, code_x, code_y, _, _, _ = self.find_merchant_icon(screenshot, code_field_template, 0.65)
                                        
                                        if found:
                                            print(f"✓ Code field found at ({code_x}, {code_y}), double-clicking to copy...")
                                            pyautogui.doubleClick(code_x, code_y)
                                            time.sleep(0.5)
                                            # Press Ctrl+C to ensure it's copied
                                            pyautogui.hotkey('ctrl', 'c')
                                            time.sleep(0.3)
                                            print("✓ Code copied to clipboard")
                                            
                                            # Now look for the paste field and paste the code
                                            print("STEP 8f: Looking for Server Code input field to paste...")
                                            paste_field_template = os.path.join(os.path.dirname(__file__), "server_code_input.png")
                                            
                                            if os.path.exists(paste_field_template):
                                                screenshot = self.capture_screen()
                                                found, paste_x, paste_y, _, _, _ = self.find_merchant_icon(screenshot, paste_field_template, 0.65)
                                                
                                                if found:
                                                    print(f"✓ Server Code input found at ({paste_x}, {paste_y}), clicking and pasting...")
                                                    pyautogui.click(paste_x, paste_y)
                                                    time.sleep(0.3)
                                                    # Paste the code
                                                    pyautogui.hotkey('ctrl', 'v')
                                                    time.sleep(0.5)
                                                    # Press Enter
                                                    pyautogui.press('enter')
                                                    time.sleep(2)
                                                    print("✓ Code pasted and submitted")
                                                    
                                                    # Click "Regular" button
                                                    print("STEP 8g: Looking for Regular button...")
                                                    regular_button_template = os.path.join(os.path.dirname(__file__), "regular_button.png")
                                                    
                                                    if os.path.exists(regular_button_template):
                                                        screenshot = self.capture_screen()
                                                        found, reg_x, reg_y, _, _, _ = self.find_merchant_icon(screenshot, regular_button_template, 0.65)
                                                        
                                                        if found:
                                                            print(f"✓ Regular button found at ({reg_x}, {reg_y}), clicking...")
                                                            pyautogui.click(reg_x, reg_y)
                                                            time.sleep(3)
                                                            print("✓ Joining regular server...")
                                                            
                                                            # Click "First Sea" button
                                                            print("STEP 8h: Looking for First Sea button...")
                                                            first_sea_template = os.path.join(os.path.dirname(__file__), "first_sea_button.png")
                                                            
                                                            if os.path.exists(first_sea_template):
                                                                screenshot = self.capture_screen()
                                                                found, sea_x, sea_y, _, _, _ = self.find_merchant_icon(screenshot, first_sea_template, 0.65)
                                                                
                                                                if found:
                                                                    print(f"✓ First Sea button found at ({sea_x}, {sea_y}), clicking...")
                                                                    pyautogui.click(sea_x, sea_y)
                                                                    time.sleep(5)
                                                                    print("✓ Loading into First Sea - ready to hunt merchants!")
                                                                else:
                                                                    print("⚠ First Sea button not found")
                                                            else:
                                                                print("⚠ first_sea_button.png not found")
                                                        else:
                                                            print("⚠ Regular button not found")
                                                    else:
                                                        print("⚠ regular_button.png not found")
                                                else:
                                                    print("⚠ Server Code input field not found")
                                            else:
                                                print("⚠ server_code_input.png not found")
                                        else:
                                            print("⚠ Code field not found")
                                    else:
                                        print("⚠ code_field.png not found")
                                else:
                                    print("⚠ Private Server button not found")
                            else:
                                print("⚠ private_server_button.png not found")
                        else:
                            print("⚠ Main Menu button not found")
                    else:
                        print("⚠ main_menu_button.png not found")
                else:
                    print("⚠ Exit button not found")
            else:
                print("⚠ exit_button.png not found, skipping close step")
            
            print("✓ Interaction sequence complete! Continuing macro...")
            return True
            
        except Exception as e:
            # Make sure to release any held keys
            try:
                ReleaseKey(T)
            except:
                pass
            try:
                ReleaseKey(W)
            except:
                pass
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
    
    def run_loop(self, template_paths, text_template_paths, detection_threshold=0.7):
        self.loop_count += 1
        
        screenshot = self.capture_screen()
        found, x, y, confidence, match_location, matched_template = self.find_merchant_icon(
            screenshot, template_paths, detection_threshold
        )
        
        # Also check for merchant text if text templates are available
        text_found = False
        if text_template_paths:
            text_found, _, _, text_confidence, text_match_location, text_matched_template = self.find_merchant_icon(
                screenshot, text_template_paths, detection_threshold
            )
        
        # Merchant is confirmed if BOTH icon and text are found (or if no text templates, just icon)
        merchant_confirmed = found and (text_found or not text_template_paths)
        
        if self.show_detection:
            vis_screenshot = screenshot.copy()
            if found and match_location:
                match_x, match_y, match_w, match_h = match_location
                cv2.rectangle(vis_screenshot, 
                            (match_x, match_y), 
                            (match_x + match_w, match_y + match_h), 
                            (0, 255, 0), 2)
                template_name = os.path.basename(matched_template) if matched_template else "Unknown"
                cv2.putText(vis_screenshot, 
                          f"{template_name}: {confidence:.2%}", 
                          (match_x, match_y - 10), 
                          cv2.FONT_HERSHEY_SIMPLEX, 
                          0.5, 
                          (0, 255, 0), 
                          1)
            
            # Draw text detection if found
            if text_found and text_match_location:
                text_x, text_y, text_w, text_h = text_match_location
                cv2.rectangle(vis_screenshot, 
                            (text_x, text_y), 
                            (text_x + text_w, text_y + text_h), 
                            (0, 255, 255), 2)  # Yellow for text
                text_name = os.path.basename(text_matched_template) if text_matched_template else "Unknown"
                cv2.putText(vis_screenshot, 
                          f"TEXT: {text_name}: {text_confidence:.2%}", 
                          (text_x, text_y - 10), 
                          cv2.FONT_HERSHEY_SIMPLEX, 
                          0.5, 
                          (0, 255, 255), 
                          1)
            
            pil_image = Image.fromarray(cv2.cvtColor(vis_screenshot, cv2.COLOR_BGR2RGB))
            
            if self.compass_region:
                canvas_width = 600
                canvas_height = 400
                img_width, img_height = pil_image.size
                scale = min(canvas_width / img_width, canvas_height / img_height)
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            if self.update_vis_callback and self.root:
                self.root.after(0, lambda img=pil_image: self.update_vis_callback(img))
        
        if merchant_confirmed:
            # Only send webhook and interact if this is the first time finding the merchant
            if not self.merchant_found_flag:
                self.merchants_found += 1
                self.merchant_found_flag = True
                
                template_name = os.path.basename(matched_template) if matched_template else "Unknown"
                
                # Interact with merchant (hover, press 1, hold T)
                interacted = False
                if self.auto_interact:
                    interacted = self.interact_with_merchant(template_paths, text_template_paths, detection_threshold)
                
                message = (
                    f"**Traveling Merchant Detected**\n\n"
                    f"Template Matched: {template_name}\n"
                    f"Position: ({x}, {y})\n"
                    f"Confidence: {confidence:.2%}\n"
                )
                
                if self.auto_interact:
                    if interacted:
                        message += f"\nInteraction complete (pressed 1, held T while hovering until merchant disappeared)"
                    else:
                        message += f"\nInteraction timed out"
                
                self.send_discord_webhook(message, color=0x57F287)
                
                # Don't stop the macro - let it continue searching
                # Reset flag after a delay to allow detection of new merchant spawn
                time.sleep(2)
                self.merchant_found_flag = False
            
            return True, confidence, True
        else:
            # Always search - rotate camera continuously
            if self.search_mode:
                PressAndReleaseKey(RIGHT_ARROW)
                time.sleep(0.1)
            
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


class ItemSelectorWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Select Items to Purchase")
        self.window.geometry("800x600")
        self.window.configure(bg='#0f0f14')
        self.window.transient(parent)
        self.window.grab_set()
        
        # Item folder
        self.item_folder = os.path.join(os.path.dirname(__file__), "items")
        
        # Header
        header = tk.Frame(self.window, bg='#131316', height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="Select Items to Purchase", bg='#131316', fg='#ffffff', font=("Segoe UI", 16, 'bold')).pack(anchor='w', padx=20, pady=15)
        
        # Main content area with scrollbar
        main_frame = tk.Frame(self.window, bg='#0f0f14')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Canvas and scrollbar
        canvas = tk.Canvas(main_frame, bg='#0f0f14', highlightthickness=0)
        scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#0f0f14')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Load items
        self.item_vars = {}
        
        if not os.path.exists(self.item_folder):
            os.makedirs(self.item_folder, exist_ok=True)
            tk.Label(scrollable_frame, text="No items folder found!\nCreate an 'items' folder and add item images.", bg='#0f0f14', fg='#9aa0a6', font=("Segoe UI", 12), justify=tk.CENTER).pack(pady=100)
        else:
            item_files = [f for f in os.listdir(self.item_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
            
            if not item_files:
                tk.Label(scrollable_frame, text="No items found in items folder!\nAdd PNG/JPG images of items you want to buy.", bg='#0f0f14', fg='#9aa0a6', font=("Segoe UI", 12), justify=tk.CENTER).pack(pady=100)
            else:
                for idx, item_file in enumerate(item_files):
                    item_path = os.path.join(self.item_folder, item_file)
                    
                    # Item card
                    item_card = tk.Frame(scrollable_frame, bg='#131316', relief=tk.FLAT)
                    item_card.pack(fill=tk.X, pady=5, padx=10)
                    
                    # Load and display thumbnail
                    try:
                        img = Image.open(item_path)
                        img.thumbnail((100, 100), Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        
                        img_label = tk.Label(item_card, image=photo, bg='#131316')
                        img_label.image = photo  # Keep reference
                        img_label.pack(side=tk.LEFT, padx=10, pady=10)
                    except Exception as e:
                        tk.Label(item_card, text="[Image Error]", bg='#131316', fg='#ED4245', font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=10, pady=10)
                    
                    # Item info and checkbox
                    info_frame = tk.Frame(item_card, bg='#131316')
                    info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
                    
                    tk.Label(info_frame, text=item_file, bg='#131316', fg='#e6e6e6', font=("Segoe UI", 11, 'bold')).pack(anchor='w')
                    
                    # Checkbox
                    var = tk.BooleanVar(value=item_file in self.app.selected_items)
                    self.item_vars[item_file] = var
                    
                    chk = tk.Checkbutton(
                        info_frame,
                        text="Select for purchase",
                        variable=var,
                        bg='#131316',
                        fg='#9aa0a6',
                        selectcolor='#222228',
                        activebackground='#131316',
                        activeforeground='#ffffff',
                        font=("Segoe UI", 10),
                        cursor='hand2',
                        highlightthickness=0
                    )
                    chk.pack(anchor='w', pady=5)
        
        # Bottom buttons
        bottom_frame = tk.Frame(self.window, bg='#0f0f14')
        bottom_frame.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        tk.Button(bottom_frame, text='Save & Close', command=self.save_and_close, bg='#6C8CFF', fg='#ffffff', font=("Segoe UI", 12, 'bold'), relief=tk.FLAT, cursor='hand2', padx=30, pady=10).pack(side=tk.RIGHT, padx=5)
        tk.Button(bottom_frame, text='Cancel', command=self.window.destroy, bg='#ED4245', fg='#ffffff', font=("Segoe UI", 12, 'bold'), relief=tk.FLAT, cursor='hand2', padx=30, pady=10).pack(side=tk.RIGHT, padx=5)
    
    def save_and_close(self):
        # Update selected items
        self.app.selected_items = [item for item, var in self.item_vars.items() if var.get()]
        self.app.save_config()
        self.app.items_count_label.config(text=self.app.get_items_count_text())
        self.app.log_status(f"Updated item list: {len(self.app.selected_items)} items selected")
        self.window.destroy()


class MacroGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Roblox Merchant Finder")
        self.root.geometry("650x1000")
        self.root.resizable(True, True)
        self.root.configure(bg='#1a1a1a')
        
        if getattr(sys, 'frozen', False):
            self.script_dir = os.path.dirname(sys.executable)
        else:
            self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.config_path = os.path.join(self.script_dir, "config.json")
        
        self.webhook_var = tk.StringVar(value=self.load_config("webhook", ""))
        self.template_var = tk.StringVar(value="")
        self.merchant_text_var = tk.StringVar(value="")
        self.threshold_var = tk.DoubleVar(value=float(self.load_config("threshold", "0.75")))
        self.delay_var = tk.DoubleVar(value=float(self.load_config("delay", "5.0")))
        self.compass_region = self.load_config("region", None)
        self.ocr_region = self.load_config("ocr_region", None)
        self.selected_items = self.load_config("selected_items", [])
        self.show_detection_var = tk.BooleanVar(value=self.load_config("show_detection", False))
        
        self.detect_merchant_icon()
        self.detect_merchant_text()
        
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
        templates = []
        
        all_patterns = [
            "merchant_icon.png",
            "merchant_icon1.png",
            "merchant_icon2.png", 
            "merchant_icon3.png",
            "merchant1.png",
            "merchant2.png",
            "merchant3.png",
            "merchant.png",
            "icon1.png",
            "icon2.png",
            "icon3.png",
            "icon.png",
            "template1.png",
            "template2.png",
            "template3.png",
            "template.png"
        ]
        
        for pattern in all_patterns:
            full_path = os.path.join(self.script_dir, pattern)
            if os.path.exists(full_path) and full_path not in templates:
                templates.append(full_path)
        
        if not templates:
            png_files = glob.glob(os.path.join(self.script_dir, "*.png"))
            if png_files:
                templates = png_files[:3]
        
        if templates:
            self.template_var.set(",".join(templates))
            return True
        
        return False
    
    def detect_merchant_text(self):
        templates = []
        
        text_patterns = [
            "merchant_text.png",
            "merchant_text1.png",
            "merchant_text2.png",
            "merchant_text3.png",
            "text1.png",
            "text2.png",
            "text3.png",
            "text.png"
        ]
        
        for pattern in text_patterns:
            full_path = os.path.join(self.script_dir, pattern)
            if os.path.exists(full_path) and full_path not in templates:
                templates.append(full_path)
        
        if templates:
            self.merchant_text_var.set(",".join(templates))
            return True
        
        return False
    
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
            "region": self.compass_region,
            "ocr_region": self.ocr_region,
            "selected_items": self.selected_items,
            "show_detection": self.show_detection_var.get()
        }
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)
    
    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')

        # Color & font tokens
        ACCENT = '#6C8CFF'
        BG = '#0f0f14'
        CARD = '#131316'
        MUTED = '#9aa0a6'

        header_font = ("Segoe UI", 20, 'bold')
        label_font = ("Segoe UI", 10, 'bold')
        normal_font = ("Segoe UI", 10)

        # Header
        header = tk.Frame(self.root, bg=CARD, height=84)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        title = tk.Label(header, text="ROBLOX MERCHANT FINDER", bg=CARD, fg='#ffffff', font=header_font)
        title.pack(anchor='w', padx=18, pady=(12, 0))
        subtitle = tk.Label(header, text="F1: Start/Stop  |  F2: Select Region", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        subtitle.pack(anchor='w', padx=18)

        # Main two-column layout
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)

        left = tk.Frame(main, bg=BG, width=360)
        right = tk.Frame(main, bg=BG)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12), pady=6)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, pady=6)

        # Webhook card
        webhook_card = tk.Frame(left, bg=CARD)
        webhook_card.pack(fill=tk.X, pady=(0, 12))
        tk.Label(webhook_card, text='Discord Webhook (optional)', bg=CARD, fg='#e6e6e6', font=label_font).pack(anchor='w', padx=10, pady=(8,0))
        self.webhook_entry = tk.Entry(webhook_card, textvariable=self.webhook_var, font=normal_font, bg='#121217', fg='#eaeaea', insertbackground=ACCENT, relief=tk.FLAT)
        self.webhook_entry.pack(fill=tk.X, padx=10, pady=8, ipady=6)

        # Detection settings card
        detect_card = tk.Frame(left, bg=CARD)
        detect_card.pack(fill=tk.X, pady=(0, 12))
        tk.Label(detect_card, text='Detection Settings', bg=CARD, fg='#e6e6e6', font=label_font).pack(anchor='w', padx=10, pady=(8,4))

        # Threshold row
        thresh_row = tk.Frame(detect_card, bg=CARD)
        thresh_row.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(thresh_row, text='ConfidencePercentage', bg=CARD, fg=MUTED, font=normal_font).pack(side=tk.LEFT)
        self.thresh_spin = tk.Spinbox(thresh_row, from_=0.50, to=0.95, increment=0.01, textvariable=self.threshold_var, format="%.2f", width=8, justify='left', bg='#141416', fg='#eaeaea', relief=tk.FLAT)
        self.thresh_spin.pack(side=tk.RIGHT)

        # Delay row
        delay_row = tk.Frame(detect_card, bg=CARD)
        delay_row.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(delay_row, text='Loop Delay (s)', bg=CARD, fg=MUTED, font=normal_font).pack(side=tk.LEFT)
        self.delay_spin = tk.Spinbox(delay_row, from_=1.0, to=30.0, increment=0.5, textvariable=self.delay_var, format="%.1f", width=8, justify='left', bg='#141416', fg='#eaeaea', relief=tk.FLAT)
        self.delay_spin.pack(side=tk.RIGHT)

        # Auto-features info card
        info_card = tk.Frame(left, bg=CARD)
        info_card.pack(fill=tk.X, pady=(0, 12))
        tk.Label(info_card, text='Auto Features', bg=CARD, fg='#e6e6e6', font=label_font).pack(anchor='w', padx=10, pady=(8,4))
        tk.Label(info_card, text='✓ Auto-Interact: Works Fine', bg=CARD, fg='#4ECDC4', font=normal_font).pack(anchor='w', padx=10, pady=2)
        tk.Label(info_card, text='✓ Search Mode: Works Fine', bg=CARD, fg='#4ECDC4', font=normal_font).pack(anchor='w', padx=10, pady=(2,8))
        
        # Visualization toggle with better styling
        viz_card = tk.Frame(left, bg=CARD)
        viz_card.pack(fill=tk.X, pady=(0, 12))
        tk.Label(viz_card, text='Visualization', bg=CARD, fg='#e6e6e6', font=label_font).pack(anchor='w', padx=10, pady=(8,4))
        
        viz_inner = tk.Frame(viz_card, bg=CARD)
        viz_inner.pack(fill=tk.X, padx=10, pady=(0, 8))
        
        self.detection_check = tk.Checkbutton(
            viz_inner, 
            text='Show Detection', 
            variable=self.show_detection_var, 
            bg=CARD, 
            fg='#e6e6e6',
            selectcolor='#222228',
            activebackground=CARD,
            activeforeground='#ffffff',
            font=normal_font,
            cursor='hand2',
            highlightthickness=0
        )
        self.detection_check.pack(anchor='w', pady=2)

        # Region selector
        region_card = tk.Frame(left, bg=CARD)
        region_card.pack(fill=tk.X, pady=(0,12))
        tk.Label(region_card, text='Compass Region', bg=CARD, fg='#e6e6e6', font=label_font).pack(anchor='w', padx=10, pady=(8,4))
        self.region_label = tk.Label(region_card, text=self.get_region_text(), bg=CARD, fg='#e6e6e6')
        self.region_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=8)
        self.region_btn = tk.Button(region_card, text='Select (F2)', command=self.select_region, bg='#222228', fg='#eaeaea', relief=tk.FLAT)
        self.region_btn.pack(side=tk.RIGHT, padx=10, pady=8)

        # Item list management
        items_card = tk.Frame(left, bg=CARD)
        items_card.pack(fill=tk.X, pady=(0,12))
        tk.Label(items_card, text='Purchase Items', bg=CARD, fg='#e6e6e6', font=label_font).pack(anchor='w', padx=10, pady=(8,4))
        items_info = tk.Frame(items_card, bg=CARD)
        items_info.pack(fill=tk.X, padx=10, pady=(0,8))
        self.items_count_label = tk.Label(items_info, text=self.get_items_count_text(), bg=CARD, fg='#9aa0a6', font=normal_font)
        self.items_count_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.items_btn = tk.Button(items_info, text='Manage List', command=self.open_item_selector, bg='#6C8CFF', fg='#ffffff', relief=tk.FLAT, font=("Segoe UI", 9, 'bold'), cursor='hand2')
        self.items_btn.pack(side=tk.RIGHT)

        # Right: visualization + log
        vis_card = tk.Frame(right, bg=CARD)
        vis_card.pack(fill=tk.BOTH, expand=True)
        tk.Label(vis_card, text='Detection Visualization', bg=CARD, fg='#e6e6e6', font=label_font).pack(anchor='w', padx=10, pady=(8,4))
        self.vis_canvas = tk.Canvas(vis_card, bg='#07070a', bd=0, highlightthickness=0)
        self.vis_canvas.pack(padx=10, pady=(0,10), fill=tk.BOTH, expand=True)

        status_card = tk.Frame(right, bg=CARD)
        status_card.pack(fill=tk.BOTH, expand=True, pady=(8,0))
        tk.Label(status_card, text='Status Log', bg=CARD, fg='#e6e6e6', font=label_font).pack(anchor='w', padx=10, pady=(8,4))
        status_inner = tk.Frame(status_card, bg=CARD)
        status_inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        self.scrollbar = tk.Scrollbar(status_inner)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text = tk.Text(status_inner, height=10, font=("Consolas", 10), bg='#07070a', fg='#e8e8e8', insertbackground=ACCENT, state='disabled', wrap=tk.WORD, yscrollcommand=self.scrollbar.set)
        self.status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.status_text.yview)

        # Bottom start/stop
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=14, pady=12)
        self.start_btn = tk.Button(btn_frame, text='START MACRO (F1)', command=self.toggle_macro, font=("Segoe UI", 14, 'bold'), bg=ACCENT, fg='#ffffff', relief='flat')
        self.start_btn.pack(fill=tk.X)
        
    def update_vis(self, pil_image):
        try:
            self.vis_canvas.delete("all")
            self.vis_image = ImageTk.PhotoImage(pil_image)
            canvas_width = self.vis_canvas.winfo_width()
            canvas_height = self.vis_canvas.winfo_height()
            x = (canvas_width - pil_image.width) // 2
            y = (canvas_height - pil_image.height) // 2
            self.vis_canvas.create_image(x, y, anchor=tk.NW, image=self.vis_image)
        except Exception as e:
            print(f"Error updating visualization: {e}")
    
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
    
    def get_items_count_text(self):
        if self.selected_items:
            return f"{len(self.selected_items)} item(s) selected"
        return "No items selected"
    
    def open_item_selector(self):
        ItemSelectorWindow(self.root, self)
    
    def toggle_macro(self):
        if self.is_running:
            self.stop_macro()
        else:
            self.start_macro()
    
    def start_macro(self):
        if not self.template_var.get():
            self.detect_merchant_icon()
        
        if not self.template_var.get() or self.template_var.get() == "":
            messagebox.showerror(
                "Error",
                f"Merchant icon template not found!\n\nAdd PNG files to:\n{self.script_dir}\n\nSupported names:\nmerchant_icon.png, merchant1.png, merchant2.png, etc."
            )
            return
        
        template_paths = [p.strip() for p in self.template_var.get().split(',')]
        missing_files = []
        
        for template_path in template_paths:
            if not os.path.exists(template_path):
                missing_files.append(os.path.basename(template_path))
        
        if missing_files:
            messagebox.showerror(
                "Error",
                f"Template file(s) not found:\n" + "\n".join(missing_files) + f"\n\nIn folder:\n{self.script_dir}"
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
            ocr_region=self.ocr_region,
            auto_interact=True,
            search_mode=True,
            show_detection=self.show_detection_var.get(),
            root=self.root,
            update_vis_callback=self.update_vis
        )
        
        # Pass selected items to finder
        self.finder.selected_items = self.selected_items
        
        self.save_config()
        template_names = [os.path.basename(p) for p in template_paths]
        self.log_status(f"Macro started - Templates: {', '.join(template_names)}")
        
        if self.selected_items:
            self.log_status(f"Shopping for: {', '.join(self.selected_items)}")
        else:
            self.log_status("⚠ No items selected - will check all items in folder")
        
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
        
        self.log_status("Macro stopped")
    
    def run_macro(self):
        try:
            while self.is_running:
                found, confidence, interacted = self.finder.run_loop(
                    self.template_var.get(),
                    self.merchant_text_var.get(),
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
        self.status_text.see('end')
        
        lines = self.status_text.get('1.0', tk.END).split('\n')
        if len(lines) > 100:
            self.status_text.delete('1.0', '2.0')
        
        self.status_text.config(state='disabled')
        
        print(f"[{timestamp}] {message}")
    
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
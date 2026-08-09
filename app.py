import tkinter as tk
import asyncio
import edge_tts
import pygame
import tempfile
import os
from groq import Groq
import threading
import time
import speech_recognition as sr
import queue
import re
import yt_dlp
import cv2
import numpy as np
from PIL import Image, ImageTk

# ============================================
# CONFIGURATION - REPLACE WITH YOUR API KEY
# ============================================
GROQ_API_KEY = "enter it"  # Get from https://console.groq.com
# ============================================

# Initialize Groq client
client = Groq(api_key=GROQ_API_KEY)

class VoiceRobot:
    def __init__(self, root):
        self.root = root
        
        # FULL SCREEN - NO BORDERS, NO BUTTONS
        self.root.overrideredirect(True)
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg='#0a0a1a')
        
        # Get screen dimensions
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        
        # Main canvas
        self.canvas = tk.Canvas(root, width=self.screen_width, height=self.screen_height,
                               bg='#0a0a1a', highlightthickness=0, bd=0)
        self.canvas.pack(expand=True, fill=tk.BOTH)
        
        # Camera variables
        self.camera_window = None
        self.camera_running = False
        self.cap = None
        
        # Hidden text input (debug - Ctrl+T)
        self.input_entry = tk.Entry(root, width=30, font=('Arial', 10),
                                   bg='#2d2d44', fg='#fff', insertbackground='white')
        self.input_entry.place(x=-1000, y=0)
        self.input_entry.bind('<Return>', lambda e: self.process_text_input())
        
        # Keyboard shortcuts
        self.root.bind('<Control-t>', self.show_text_input)
        self.root.bind('<Escape>', lambda e: self.on_closing())
        self.root.bind('<F11>', lambda e: self.toggle_fullscreen())
        
        # DOUBLE TAP / DOUBLE RIGHT-CLICK TO EXIT
        self.last_click_time = 0
        self.click_count = 0
        
        # Bind exit events
        self.canvas.bind('<Button-1>', self.on_single_tap)
        self.canvas.bind('<Button-3>', self.on_right_click)
        self.root.bind('<Button-1>', self.on_single_tap)
        self.root.bind('<Button-3>', self.on_right_click)
        
        # Initialize pygame
        pygame.mixer.init()
        
        # Speech recognition
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        
        # Command queue
        self.command_queue = queue.Queue()
        
        # Robot state
        self.speaking = False
        self.listening = False
        self.running = True
        self.current_state = "normal"
        self.current_language = "en"
        self.playing_song = False
        self.vision_mode = False
        self.mouth_open = 0
        self.mouth_direction = 1
        
        # Wake words
        self.WAKE_WORDS = ['sam', 'hey', 'hello', 'some']
        self.HINDI_KEYWORDS = ['hindi', 'हिंदी', 'hindi me bolo', 'हिंदी में बोलो']
        self.SONG_KEYWORDS = ['play song', 'play music', 'गाना बजाओ']
        self.VISION_KEYWORDS = ['woodpecker', 'see', 'look', 'camera']
        
        # Scale robot
        self.scale = min(self.screen_width, self.screen_height) / 500
        
        # Draw robot
        self.draw_robot("normal")
        
        # Start threads
        self.start_voice_recognition()
        self.start_command_processor()
        self.start_mouth_animation()
        
        # Welcome message
        self.root.after(1000, lambda: self.speak_with_expression(
            "Namaste! I am SAM. Say my name to talk. Say Woodpecker for me to see! Double tap to exit.",
            "normal", "en"))
    
    # ============================================
    # EXIT HANDLERS
    # ============================================
    def on_single_tap(self, event):
        current_time = time.time()
        if current_time - self.last_click_time < 0.5:
            self.click_count += 1
            if self.click_count >= 2:
                self.click_count = 0
                self.show_exit_confirmation()
                return
        else:
            self.click_count = 1
        self.last_click_time = current_time
        self.root.after(500, self.reset_click_count)
    
    def on_right_click(self, event):
        current_time = time.time()
        if current_time - self.last_click_time < 0.5:
            self.click_count += 1
            if self.click_count >= 2:
                self.click_count = 0
                self.show_exit_confirmation()
                return
        else:
            self.click_count = 1
        self.last_click_time = current_time
        self.root.after(500, self.reset_click_count)
    
    def reset_click_count(self):
        self.click_count = 0
    
    def show_exit_confirmation(self):
        def flash_exit(count=0):
            if count < 3:
                if count % 2 == 0:
                    self.draw_robot("playing")
                else:
                    self.draw_robot("normal")
                self.root.after(200, lambda: flash_exit(count + 1))
            else:
                self.draw_robot("normal")
                self.root.after(500, self.on_closing)
        flash_exit()
    
    def toggle_fullscreen(self):
        is_fullscreen = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not is_fullscreen)
        if not is_fullscreen:
            self.root.overrideredirect(True)
    
    # ============================================
    # DRAW ROBOT
    # ============================================
    def draw_robot(self, state="normal", mouth_open=0):
        self.canvas.delete("all")
        
        colors = {
            "normal": {"eye": '#00ffff', "mouth": '#00ffff'},
            "listening": {"eye": '#9b59b6', "mouth": '#9b59b6'},
            "speaking": {"eye": '#3498db', "mouth": '#3498db'},
            "playing": {"eye": '#e74c3c', "mouth": '#e74c3c'},
            "vision": {"eye": '#2ecc71', "mouth": '#2ecc71'}
        }
        
        color = colors.get(state, colors["normal"])
        eye_color = color["eye"]
        mouth_color = color["mouth"]
        
        center_x = self.screen_width // 2
        center_y = self.screen_height // 2
        s = self.scale
        
        head_width = 300 * s
        head_height = 270 * s
        head_x = center_x - head_width // 2
        head_y = center_y - head_height // 2 - 50 * s
        
        eye_size = 60 * s
        eye_y = center_y - 40 * s
        left_eye_x = center_x - 90 * s - eye_size // 2
        right_eye_x = center_x + 90 * s - eye_size // 2
        
        mouth_width = 100 * s
        mouth_y = center_y + 60 * s
        
        # Head
        self.canvas.create_rectangle(head_x, head_y, head_x + head_width, head_y + head_height,
                                    fill='#1a1a2e', tags="head", outline='')
        
        # Eyes
        self.canvas.create_oval(left_eye_x, eye_y, left_eye_x + eye_size, eye_y + eye_size,
                               outline='#2c3e50', width=int(3*s), fill=eye_color)
        self.canvas.create_oval(right_eye_x, eye_y, right_eye_x + eye_size, eye_y + eye_size,
                               outline='#2c3e50', width=int(3*s), fill=eye_color)
        
        # Pupils
        pupil_size = 10 * s
        if state == "listening":
            self.canvas.create_oval(left_eye_x + eye_size//2 - pupil_size//2,
                                   eye_y + eye_size//2 - pupil_size//2,
                                   left_eye_x + eye_size//2 + pupil_size//2,
                                   eye_y + eye_size//2 + pupil_size//2, fill='black')
            self.canvas.create_oval(right_eye_x + eye_size//2 - pupil_size//2,
                                   eye_y + eye_size//2 - pupil_size//2,
                                   right_eye_x + eye_size//2 + pupil_size//2,
                                   eye_y + eye_size//2 + pupil_size//2, fill='black')
            self.canvas.create_oval(left_eye_x - 10*s, eye_y - 10*s,
                                   left_eye_x + eye_size + 10*s, eye_y + eye_size + 10*s,
                                   outline=eye_color, width=int(2*s))
            self.canvas.create_oval(right_eye_x - 10*s, eye_y - 10*s,
                                   right_eye_x + eye_size + 10*s, eye_y + eye_size + 10*s,
                                   outline=eye_color, width=int(2*s))
        elif state == "speaking":
            self.canvas.create_oval(left_eye_x + eye_size//2 - pupil_size//2,
                                   eye_y + eye_size//2 - pupil_size//2,
                                   left_eye_x + eye_size//2 + pupil_size//2,
                                   eye_y + eye_size//2 + pupil_size//2, fill='black')
            self.canvas.create_oval(right_eye_x + eye_size//2 - pupil_size//2,
                                   eye_y + eye_size//2 - pupil_size//2,
                                   right_eye_x + eye_size//2 + pupil_size//2,
                                   eye_y + eye_size//2 + pupil_size//2, fill='black')
        elif state == "playing":
            self.canvas.create_oval(left_eye_x + eye_size//2 - pupil_size//2,
                                   eye_y + eye_size//2 - pupil_size//2,
                                   left_eye_x + eye_size//2 + pupil_size//2,
                                   eye_y + eye_size//2 + pupil_size//2, fill='black')
            self.canvas.create_oval(right_eye_x + eye_size//2 - pupil_size//2,
                                   eye_y + eye_size//2 - pupil_size//2,
                                   right_eye_x + eye_size//2 + pupil_size//2,
                                   eye_y + eye_size//2 + pupil_size//2, fill='black')
            self.canvas.create_text(left_eye_x - 40*s, eye_y - 20*s,
                                   text="♪", fill='#e74c3c', font=('Arial', int(30*s)))
            self.canvas.create_text(right_eye_x + eye_size + 40*s, eye_y - 20*s,
                                   text="♫", fill='#e74c3c', font=('Arial', int(30*s)))
        elif state == "vision":
            self.canvas.create_oval(left_eye_x + eye_size//2 - pupil_size//2,
                                   eye_y + eye_size//2 - pupil_size//2,
                                   left_eye_x + eye_size//2 + pupil_size//2,
                                   eye_y + eye_size//2 + pupil_size//2, fill='black')
            self.canvas.create_oval(right_eye_x + eye_size//2 - pupil_size//2,
                                   eye_y + eye_size//2 - pupil_size//2,
                                   right_eye_x + eye_size//2 + pupil_size//2,
                                   eye_y + eye_size//2 + pupil_size//2, fill='black')
            self.canvas.create_line(left_eye_x + eye_size//2, eye_y - 15*s,
                                   left_eye_x + eye_size//2, eye_y + 15*s,
                                   fill='#2ecc71', width=int(2*s))
            self.canvas.create_line(left_eye_x - 15*s, eye_y + eye_size//2,
                                   left_eye_x + 15*s, eye_y + eye_size//2,
                                   fill='#2ecc71', width=int(2*s))
            self.canvas.create_line(right_eye_x + eye_size//2, eye_y - 15*s,
                                   right_eye_x + eye_size//2, eye_y + 15*s,
                                   fill='#2ecc71', width=int(2*s))
            self.canvas.create_line(right_eye_x - 15*s, eye_y + eye_size//2,
                                   right_eye_x + 15*s, eye_y + eye_size//2,
                                   fill='#2ecc71', width=int(2*s))
        else:
            self.canvas.create_oval(left_eye_x + eye_size//2 - pupil_size//2,
                                   eye_y + eye_size//2 - pupil_size//2,
                                   left_eye_x + eye_size//2 + pupil_size//2,
                                   eye_y + eye_size//2 + pupil_size//2, fill='black')
            self.canvas.create_oval(right_eye_x + eye_size//2 - pupil_size//2,
                                   eye_y + eye_size//2 - pupil_size//2,
                                   right_eye_x + eye_size//2 + pupil_size//2,
                                   eye_y + eye_size//2 + pupil_size//2, fill='black')
        
        # MOUTH WITH REAL OPENING/CLOSING
        if state == "speaking":
            mouth_height = 5*s + (mouth_open / 100) * 35*s
            self.canvas.create_arc(center_x - mouth_width//2, mouth_y - mouth_height/2,
                                  center_x + mouth_width//2, mouth_y + mouth_height/2,
                                  start=0, extent=180,
                                  style='arc', outline=mouth_color, width=int(3*s))
            if mouth_height > 15*s:
                self.canvas.create_arc(center_x - mouth_width//2 + 5*s,
                                       mouth_y - mouth_height/2 + 2*s,
                                       center_x + mouth_width//2 - 5*s,
                                       mouth_y - mouth_height/2 + 8*s,
                                       start=0, extent=180,
                                       style='arc', outline='white', width=int(2*s))
        elif state == "listening":
            self.canvas.create_arc(center_x - mouth_width//2, mouth_y - 15*s,
                                  center_x + mouth_width//2, mouth_y + 15*s,
                                  start=0, extent=180,
                                  style='arc', outline=mouth_color, width=int(3*s))
            for i in range(3):
                x_offset = (30 + i * 15) * s
                self.canvas.create_arc(center_x - mouth_width//2 - x_offset, mouth_y - 20*s,
                                       center_x - mouth_width//2 - x_offset + 20*s, mouth_y + 20*s,
                                      start=60, extent=60, outline=mouth_color,
                                      width=int(2*s), style='arc')
                self.canvas.create_arc(center_x + mouth_width//2 + x_offset, mouth_y - 20*s,
                                       center_x + mouth_width//2 + x_offset + 20*s, mouth_y + 20*s,
                                      start=120, extent=60, outline=mouth_color,
                                      width=int(2*s), style='arc')
        elif state == "playing":
            self.canvas.create_arc(center_x - mouth_width//2, mouth_y - 20*s,
                                  center_x + mouth_width//2, mouth_y + 20*s,
                                  start=0, extent=180,
                                  style='arc', outline=mouth_color, width=int(3*s))
            self.canvas.create_text(center_x, mouth_y + 25*s, text="♪♫",
                                   fill='#e74c3c', font=('Arial', int(20*s)))
        elif state == "vision":
            self.canvas.create_arc(center_x - mouth_width//2, mouth_y - 15*s,
                                  center_x + mouth_width//2, mouth_y + 15*s,
                                  start=0, extent=180,
                                  style='arc', outline=mouth_color, width=int(3*s))
            self.canvas.create_oval(center_x - 15*s, mouth_y - 5*s,
                                   center_x + 15*s, mouth_y + 5*s,
                                   outline=mouth_color, width=int(2*s))
            self.canvas.create_text(center_x, mouth_y + 30*s, text="📷",
                                   fill='#2ecc71', font=('Arial', int(25*s)))
        else:
            self.canvas.create_line(center_x - mouth_width//2, mouth_y,
                                   center_x + mouth_width//2, mouth_y,
                                   fill=mouth_color, width=int(3*s))
        
        # Status dots
        if state == "listening":
            dot_color = '#9b59b6'
            self.canvas.create_oval(self.screen_width - 60*s, self.screen_height - 40*s,
                                   self.screen_width - 52*s, self.screen_height - 32*s,
                                   fill=dot_color, outline=dot_color)
            self.canvas.create_oval(self.screen_width - 52*s, self.screen_height - 45*s,
                                   self.screen_width - 44*s, self.screen_height - 37*s,
                                   fill=dot_color, outline=dot_color)
            self.canvas.create_oval(self.screen_width - 56*s, self.screen_height - 50*s,
                                   self.screen_width - 48*s, self.screen_height - 42*s,
                                   fill=dot_color, outline=dot_color)
        elif state == "speaking":
            dot_color = '#3498db'
            self.canvas.create_oval(self.screen_width - 60*s, self.screen_height - 40*s,
                                   self.screen_width - 52*s, self.screen_height - 32*s,
                                   fill=dot_color, outline=dot_color)
            self.canvas.create_oval(self.screen_width - 52*s, self.screen_height - 45*s,
                                   self.screen_width - 44*s, self.screen_height - 37*s,
                                   fill=dot_color, outline=dot_color)
        elif state == "playing":
            dot_color = '#e74c3c'
            self.canvas.create_oval(self.screen_width - 60*s, self.screen_height - 40*s,
                                   self.screen_width - 52*s, self.screen_height - 32*s,
                                   fill=dot_color, outline=dot_color)
            self.canvas.create_oval(self.screen_width - 52*s, self.screen_height - 45*s,
                                   self.screen_width - 44*s, self.screen_height - 37*s,
                                   fill=dot_color, outline=dot_color)
            self.canvas.create_oval(self.screen_width - 56*s, self.screen_height - 50*s,
                                   self.screen_width - 48*s, self.screen_height - 42*s,
                                   fill=dot_color, outline=dot_color)
        elif state == "vision":
            dot_color = '#2ecc71'
            self.canvas.create_oval(self.screen_width - 60*s, self.screen_height - 40*s,
                                   self.screen_width - 52*s, self.screen_height - 32*s,
                                   fill=dot_color, outline=dot_color)
            self.canvas.create_oval(self.screen_width - 52*s, self.screen_height - 45*s,
                                   self.screen_width - 44*s, self.screen_height - 37*s,
                                   fill=dot_color, outline=dot_color)
            self.canvas.create_oval(self.screen_width - 56*s, self.screen_height - 50*s,
                                   self.screen_width - 48*s, self.screen_height - 42*s,
                                   fill=dot_color, outline=dot_color)
            self.canvas.create_oval(self.screen_width - 64*s, self.screen_height - 45*s,
                                   self.screen_width - 56*s, self.screen_height - 37*s,
                                   fill=dot_color, outline=dot_color)
        
        # Glow effect
        if state in ["listening", "speaking", "playing", "vision"]:
            glow_color = color["eye"]
            for i in range(3):
                offset = i * 20 * s
                self.canvas.create_oval(head_x - offset, head_y - offset,
                                       head_x + head_width + offset, head_y + head_height + offset,
                                       outline=glow_color, width=int(2*s), stipple='gray50')
        
        self.current_state = state
    
    # ============================================
    # MOUTH ANIMATION
    # ============================================
    def start_mouth_animation(self):
        def animate_mouth():
            while self.running:
                if self.current_state == "speaking":
                    self.mouth_open += self.mouth_direction * 3
                    if self.mouth_open >= 100:
                        self.mouth_direction = -1
                    elif self.mouth_open <= 0:
                        self.mouth_direction = 1
                    self.root.after(0, lambda: self.draw_robot("speaking", self.mouth_open))
                    time.sleep(0.04)
                else:
                    time.sleep(0.1)
        threading.Thread(target=animate_mouth, daemon=True).start()
    
    # ============================================
    # CAMERA VISION
    # ============================================
    def start_camera_vision(self):
        try:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                self.speak_with_expression("Camera not found.", "normal", "en")
                return
            
            self.camera_running = True
            self.vision_mode = True
            
            self.camera_window = tk.Toplevel(self.root)
            self.camera_window.title("SAM's Vision")
            self.camera_window.attributes('-fullscreen', True)
            self.camera_window.configure(bg='#0a0a1a')
            self.camera_window.protocol("WM_DELETE_WINDOW", self.stop_camera)
            self.camera_window.bind('<Escape>', lambda e: self.stop_camera())
            self.camera_window.bind('<Button-1>', lambda e: self.stop_camera())
            self.camera_window.bind('<Button-3>', lambda e: self.stop_camera())
            
            self.camera_label = tk.Label(self.camera_window, bg='#0a0a1a')
            self.camera_label.pack(expand=True, fill=tk.BOTH)
            
            status_label = tk.Label(self.camera_window, text="👁️ SAM is watching... Tap or press ESC to close",
                                   font=('Arial', 20), bg='#0a0a1a', fg='#2ecc71')
            status_label.pack(pady=10)
            
            self.update_camera_feed()
            self.speak_with_expression("Camera is ready. I can see you now!", "vision", "en")
            
        except Exception as e:
            print(f"Camera error: {e}")
            self.speak_with_expression("Sorry, I couldn't access the camera.", "normal", "en")
    
    def update_camera_feed(self):
        if not self.camera_running or not self.cap:
            return
        
        try:
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.flip(frame, 1)
                
                face_cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                )
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                
                for (x, y, w, h) in faces:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (46, 204, 113), 3)
                    cv2.putText(frame, "SAM sees you!", (x, y-10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (46, 204, 113), 2)
                    
                    if len(faces) > 0:
                        self.root.after(0, lambda: self.draw_robot("vision"))
                
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                
                screen_width = self.camera_window.winfo_screenwidth()
                screen_height = self.camera_window.winfo_screenheight()
                img = img.resize((screen_width, screen_height - 100), Image.Resampling.LANCZOS)
                
                img_tk = ImageTk.PhotoImage(image=img)
                self.camera_label.config(image=img_tk)
                self.camera_label.image = img_tk
            
            if self.camera_running:
                self.root.after(30, self.update_camera_feed)
                
        except Exception as e:
            print(f"Camera feed error: {e}")
            self.stop_camera()
    
    def stop_camera(self):
        self.camera_running = False
        self.vision_mode = False
        if self.cap:
            self.cap.release()
            self.cap = None
        if self.camera_window:
            self.camera_window.destroy()
            self.camera_window = None
        self.draw_robot("normal")
        self.speak_with_expression("Camera closed.", "normal", "en")
    
    # ============================================
    # YOUTUBE MUSIC
    # ============================================
    def search_and_play_youtube(self, song_name):
        try:
            self.root.after(0, lambda: self.draw_robot("playing"))
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
                'extract_audio': True,
                'audio_format': 'mp3',
                'outtmpl': 'temp_audio.%(ext)s',
            }
            
            search_query = f"ytsearch1:{song_name} official audio"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=True)
                if info and 'entries' in info:
                    video = info['entries'][0]
                    title = video.get('title', song_name)
                    
                    audio_file = "temp_audio.mp3"
                    time.sleep(1)
                    
                    if os.path.exists(audio_file):
                        self.root.after(0, lambda: self.speak_with_expression(
                            f"Playing {title}", "normal", "en"))
                        time.sleep(2)
                        pygame.mixer.music.load(audio_file)
                        pygame.mixer.music.play()
                        
                        while pygame.mixer.music.get_busy():
                            self.root.after(0, lambda: self.draw_robot("playing"))
                            time.sleep(1)
                        
                        pygame.mixer.music.unload()
                        if os.path.exists(audio_file):
                            os.remove(audio_file)
                        
                        self.root.after(0, lambda: self.draw_robot("normal"))
                        self.root.after(0, lambda: self.speak_with_expression(
                            "Hope you enjoyed the song!", "normal", "en"))
                    else:
                        self.root.after(0, lambda: self.speak_with_expression(
                            "Sorry, couldn't download the song.", "normal", "en"))
                        
        except Exception as e:
            print(f"Error playing song: {e}")
            self.root.after(0, lambda: self.speak_with_expression(
                "Sorry, I couldn't play that song.", "normal", "en"))
            self.root.after(0, lambda: self.draw_robot("normal"))
    
    # ============================================
    # GROQ AI RESPONSE
    # ============================================
    def get_ai_response(self, command, language="en"):
        try:
            if language == "hi":
                system_prompt = """You are SAM, a friendly robot built by students of Army Public Kota for their school's AI Lab.
                You must respond in HINDI. Keep responses very short (1 sentence max).
                Be warm and helpful. Always mention you were built by Army Public Kota students."""
            else:
                system_prompt = """You are SAM, a friendly robot built by students of Army Public Kota for their school's AI Lab.
                Keep responses very short (1 sentence max). Be warm and helpful.
                Always mention you were built by Army Public Kota students."""
            
            completion = client.chat.completions.create(
                model="mixtral-8x7b-32768",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": command}
                ],
                temperature=0.7,
                max_tokens=80
            )
            
            return completion.choices[0].message.content
            
        except Exception as e:
            if language == "hi":
                return "क्षमा करें, तकनीकी समस्या है।"
            else:
                return "Sorry, technical issue."
    
    # ============================================
    # VOICE RECOGNITION
    # ============================================
    def start_voice_recognition(self):
        def listen_continuously():
            while self.running:
                try:
                    with self.microphone as source:
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                        audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=5)
                    
                    try:
                        text = self.recognizer.recognize_google(audio, language='en-IN')
                        text_lower = text.lower().strip()
                        
                        if self.is_wake_word(text_lower):
                            if any(keyword in text_lower for keyword in self.HINDI_KEYWORDS):
                                self.current_language = "hi"
                            else:
                                self.current_language = "en"
                            
                            self.root.after(0, lambda: self.draw_robot("listening"))
                            
                            with self.microphone as source2:
                                self.recognizer.adjust_for_ambient_noise(source2, duration=0.2)
                                audio2 = self.recognizer.listen(source2, timeout=5, phrase_time_limit=10)
                            
                            try:
                                command = self.recognizer.recognize_google(audio2, language='en-IN')
                                self.command_queue.put((command, self.current_language))
                            except sr.UnknownValueError:
                                if self.current_language == "hi":
                                    self.root.after(0, lambda: self.speak_with_expression(
                                        "माफ़ करें, मुझे समझ नहीं आया।", "normal", "hi"))
                                else:
                                    self.root.after(0, lambda: self.speak_with_expression(
                                        "Sorry, I didn't catch that.", "normal", "en"))
                            except sr.RequestError:
                                if self.current_language == "hi":
                                    self.root.after(0, lambda: self.speak_with_expression(
                                        "नेटवर्क समस्या।", "normal", "hi"))
                                else:
                                    self.root.after(0, lambda: self.speak_with_expression(
                                        "Network error.", "normal", "en"))
                        
                    except sr.UnknownValueError:
                        pass
                    except sr.RequestError:
                        pass
                
                except Exception as e:
                    print(f"Voice error: {e}")
                    time.sleep(0.5)
        
        threading.Thread(target=listen_continuously, daemon=True).start()
    
    def is_wake_word(self, text):
        words = text.split()
        for word in words:
            if word in self.WAKE_WORDS:
                return True
        return False
    
    # ============================================
    # COMMAND PROCESSOR
    # ============================================
    def start_command_processor(self):
        def process_commands():
            while self.running:
                try:
                    command, language = self.command_queue.get(timeout=1)
                    self.root.after(0, lambda: self.process_voice_command(command, language))
                except queue.Empty:
                    continue
        threading.Thread(target=process_commands, daemon=True).start()
    
    def process_voice_command(self, command, language="en"):
        if self.speaking:
            return
        
        # Check for vision request
        if any(keyword in command.lower() for keyword in self.VISION_KEYWORDS):
            if not self.camera_running:
                self.root.after(0, lambda: self.speak_with_expression(
                    "Opening camera.", "vision", "en"))
                threading.Thread(target=self.start_camera_vision, daemon=True).start()
            else:
                self.root.after(0, lambda: self.speak_with_expression(
                    "Camera is already open.", "vision", "en"))
            return
        
        # Check for song request
        if any(keyword in command.lower() for keyword in self.SONG_KEYWORDS):
            song_name = command.lower()
            for phrase in ['play song', 'play music', 'गाना बजाओ']:
                song_name = song_name.replace(phrase, '')
            song_name = song_name.strip()
            if song_name:
                self.root.after(0, lambda: self.speak_with_expression(
                    f"Playing {song_name}", "normal", "en"))
                threading.Thread(target=self.search_and_play_youtube, args=(song_name,), daemon=True).start()
                return
            else:
                self.root.after(0, lambda: self.speak_with_expression(
                    "What song would you like to hear?", "normal", language))
                return
        
        # Normal AI response
        self.root.after(0, lambda: self.draw_robot("listening"))
        
        def get_response():
            response = self.get_ai_response(command, language)
            self.root.after(0, lambda: self.speak_with_expression(response, "normal", language))
        
        threading.Thread(target=get_response, daemon=True).start()
    
    # ============================================
    # SPEECH OUTPUT
    # ============================================
    def speak_with_expression(self, text, emotion="normal", language="en"):
        if self.speaking:
            return
        
        self.speaking = True
        self.root.after(0, lambda: self.draw_robot("speaking"))
        threading.Thread(target=self.speak_text, args=(text, language), daemon=True).start()
    
    def speak_text(self, text, language="en"):
        try:
            voice = "hi-IN-SwaraNeural" if language == "hi" else "en-IN-NeerjaNeural"
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tmp_path = tmp_file.name
            
            async def generate_speech():
                tts = edge_tts.Communicate(text, voice)
                await tts.save(tmp_path)
            
            asyncio.run(generate_speech())
            
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            
            pygame.mixer.music.unload()
            os.unlink(tmp_path)
            
            self.root.after(0, lambda: self.draw_robot("normal"))
            self.speaking = False
            
        except Exception as e:
            print(f"Speech error: {e}")
            self.root.after(0, lambda: self.draw_robot("normal"))
            self.speaking = False
    
    # ============================================
    # TEXT INPUT (DEBUG)
    # ============================================
    def process_text_input(self):
        text = self.input_entry.get().strip()
        if text and not self.speaking:
            self.input_entry.delete(0, tk.END)
            self.process_voice_command(text, "en")
    
    def show_text_input(self, event=None):
        self.input_entry.place(x=self.screen_width//2 - 150, y=self.screen_height - 100)
        self.input_entry.focus()
        self.root.after(5000, lambda: self.input_entry.place(x=-1000, y=0))
    
    # ============================================
    # CLEANUP
    # ============================================
    def on_closing(self):
        self.running = False
        if self.camera_running:
            self.stop_camera()
        self.root.destroy()

# ============================================
# MAIN
# ============================================
def main():
    root = tk.Tk()
    robot = VoiceRobot(root)
    root.protocol("WM_DELETE_WINDOW", robot.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
import time
import threading
from datetime import datetime, timedelta
from pynput import mouse, keyboard
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
import os
import sys
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.font_manager import FontProperties
import pygame
import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.figure as mplfig

# Logging setup
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("program_gui.log"),
                        logging.StreamHandler()
                    ])

# Global variables
INACTIVITY_THRESHOLD = 60  # seconds
use_custom_time = False
time_offset = timedelta(0)
last_activity_time = None
inactivity_start_time = None
inactivity_periods = []
hourly_charts_dir = 'hourly_charts'
hourly_csv_dir = 'hourly_csv'
is_running = False
mouse_listener = None
keyboard_listener = None
status_update_thread = None
main_thread = None
last_checked_hour = None
last_checked_day = None

# Ensure directories exist
os.makedirs(hourly_charts_dir, exist_ok=True)
os.makedirs(hourly_csv_dir, exist_ok=True)


class InactivityTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Inactivity Tracker")
        self.root.geometry("900x700")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.setup_gui()
        self.live_view_active = False
        self.live_view_timer = None
        self.current_chart_path = None
        self.start_time = None

    def setup_gui(self):
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create tabs
        self.control_tab = ttk.Frame(self.notebook)
        self.live_view_tab = ttk.Frame(self.notebook)
        self.stats_tab = ttk.Frame(self.notebook)
        self.settings_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.control_tab, text="Control")
        self.notebook.add(self.live_view_tab, text="Live View")
        self.notebook.add(self.stats_tab, text="Statistics")
        self.notebook.add(self.settings_tab, text="Settings")

        # Setup each tab
        self.setup_control_tab()
        self.setup_live_view_tab()
        self.setup_stats_tab()
        self.setup_settings_tab()

        # Status bar at the bottom
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)

        self.status_label = ttk.Label(self.status_frame, text="Status: Not running", anchor=tk.W)
        self.status_label.pack(side=tk.LEFT)

        self.activity_status = ttk.Label(self.status_frame, text="Activity: N/A", anchor=tk.E)
        self.activity_status.pack(side=tk.RIGHT)

    def setup_control_tab(self):
        control_frame = ttk.LabelFrame(self.control_tab, text="Inactivity Tracker Controls")
        control_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Start/Stop buttons
        self.btn_frame = ttk.Frame(control_frame)
        self.btn_frame.pack(pady=20)

        self.start_btn = ttk.Button(self.btn_frame, text="Start Tracking", command=self.start_tracking)
        self.start_btn.pack(side=tk.LEFT, padx=10)

        self.stop_btn = ttk.Button(self.btn_frame, text="Stop Tracking", command=self.stop_tracking, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=10)

        # Current session info
        self.info_frame = ttk.LabelFrame(control_frame, text="Current Session")
        self.info_frame.pack(fill=tk.X, padx=10, pady=10)

        # Time running
        self.time_label = ttk.Label(self.info_frame, text="Time running: 00:00:00")
        self.time_label.pack(anchor=tk.W, padx=10, pady=5)

        # Inactivity time
        self.inactivity_label = ttk.Label(self.info_frame, text="Total inactivity: 00:00:00")
        self.inactivity_label.pack(anchor=tk.W, padx=10, pady=5)

        # Inactivity percentage
        self.percentage_label = ttk.Label(self.info_frame, text="Inactivity percentage: 0.00%")
        self.percentage_label.pack(anchor=tk.W, padx=10, pady=5)

        # Current status
        self.current_status_label = ttk.Label(self.info_frame, text="Currently: Active")
        self.current_status_label.pack(anchor=tk.W, padx=10, pady=5)

        # Recent activity log
        self.log_frame = ttk.LabelFrame(control_frame, text="Recent Activity Log")
        self.log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.log_text = tk.Text(self.log_frame, height=10, width=50, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.log_scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=self.log_scrollbar.set)
        self.log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def setup_live_view_tab(self):
        self.live_frame = ttk.Frame(self.live_view_tab)
        self.live_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Controls for live view
        self.live_control_frame = ttk.Frame(self.live_frame)
        self.live_control_frame.pack(fill=tk.X, pady=10)

        self.view_label = ttk.Label(self.live_control_frame, text="View: ")
        self.view_label.pack(side=tk.LEFT, padx=5)

        self.view_type = ttk.Combobox(self.live_control_frame, values=["Current Hour", "Today's Summary"])
        self.view_type.current(0)
        self.view_type.pack(side=tk.LEFT, padx=5)

        self.refresh_btn = ttk.Button(self.live_control_frame, text="Refresh View", command=self.refresh_live_view)
        self.refresh_btn.pack(side=tk.LEFT, padx=10)

        self.auto_refresh_var = tk.BooleanVar(value=False)
        self.auto_refresh_check = ttk.Checkbutton(self.live_control_frame, text="Auto Refresh (30s)", 
                                                  variable=self.auto_refresh_var, 
                                                  command=self.toggle_auto_refresh)
        self.auto_refresh_check.pack(side=tk.LEFT, padx=10)

        # Save button
        self.save_btn = ttk.Button(self.live_control_frame, text="Save Chart", command=self.save_current_chart)
        self.save_btn.pack(side=tk.RIGHT, padx=10)

        # Canvas for displaying charts
        self.chart_frame = ttk.LabelFrame(self.live_frame, text="Activity Visualization")
        self.chart_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create a Figure and a canvas to display it
        self.fig = mplfig.Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def setup_stats_tab(self):
        stats_frame = ttk.LabelFrame(self.stats_tab, text="Activity Statistics")
        stats_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Date selection
        self.date_frame = ttk.Frame(stats_frame)
        self.date_frame.pack(fill=tk.X, pady=10)

        self.date_label = ttk.Label(self.date_frame, text="Select Date: ")
        self.date_label.pack(side=tk.LEFT, padx=5)

        today = datetime.now().strftime("%Y-%m-%d")
        self.date_entry = ttk.Entry(self.date_frame)
        self.date_entry.insert(0, today)
        self.date_entry.pack(side=tk.LEFT, padx=5)

        self.calendar_btn = ttk.Button(self.date_frame, text="Calendar", command=self.show_calendar)
        self.calendar_btn.pack(side=tk.LEFT, padx=5)

        self.load_stats_btn = ttk.Button(self.date_frame, text="Load Statistics", command=self.load_statistics)
        self.load_stats_btn.pack(side=tk.LEFT, padx=10)

        # Statistics display area
        self.stats_display_frame = ttk.Frame(stats_frame)
        self.stats_display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Summary box
        self.summary_frame = ttk.LabelFrame(self.stats_display_frame, text="Daily Summary")
        self.summary_frame.pack(fill=tk.X, pady=10)

        self.total_active_label = ttk.Label(self.summary_frame, text="Total Active Time: N/A")
        self.total_active_label.pack(anchor=tk.W, padx=10, pady=5)

        self.total_inactive_label = ttk.Label(self.summary_frame, text="Total Inactive Time: N/A")
        self.total_inactive_label.pack(anchor=tk.W, padx=10, pady=5)

        self.inactive_percent_label = ttk.Label(self.summary_frame, text="Inactive Percentage: N/A")
        self.inactive_percent_label.pack(anchor=tk.W, padx=10, pady=5)

        # Hour by hour breakdown
        self.hourly_frame = ttk.LabelFrame(self.stats_display_frame, text="Hourly Breakdown")
        self.hourly_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.hourly_canvas = tk.Canvas(self.hourly_frame)
        self.hourly_scrollbar = ttk.Scrollbar(self.hourly_frame, orient="vertical", command=self.hourly_canvas.yview)
        self.hourly_scrollable_frame = ttk.Frame(self.hourly_canvas)

        self.hourly_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.hourly_canvas.configure(
                scrollregion=self.hourly_canvas.bbox("all")
            )
        )

        self.hourly_canvas.create_window((0, 0), window=self.hourly_scrollable_frame, anchor="nw")
        self.hourly_canvas.configure(yscrollcommand=self.hourly_scrollbar.set)

        self.hourly_canvas.pack(side="left", fill="both", expand=True)
        self.hourly_scrollbar.pack(side="right", fill="y")

    def setup_settings_tab(self):
        settings_frame = ttk.LabelFrame(self.settings_tab, text="Application Settings")
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Inactivity threshold
        self.threshold_frame = ttk.Frame(settings_frame)
        self.threshold_frame.pack(fill=tk.X, pady=10)

        self.threshold_label = ttk.Label(self.threshold_frame, text="Inactivity Threshold (seconds): ")
        self.threshold_label.pack(side=tk.LEFT, padx=5)

        self.threshold_var = tk.IntVar(value=INACTIVITY_THRESHOLD)
        self.threshold_entry = ttk.Entry(self.threshold_frame, textvariable=self.threshold_var)
        self.threshold_entry.pack(side=tk.LEFT, padx=5)

        # Directory settings
        self.dir_frame = ttk.LabelFrame(settings_frame, text="Directory Settings")
        self.dir_frame.pack(fill=tk.X, pady=10, padx=10)

        # Hourly charts directory
        self.hourly_dir_frame = ttk.Frame(self.dir_frame)
        self.hourly_dir_frame.pack(fill=tk.X, pady=5)

        self.hourly_dir_label = ttk.Label(self.hourly_dir_frame, text="Hourly Charts Directory: ")
        self.hourly_dir_label.pack(side=tk.LEFT, padx=5)

        self.hourly_dir_var = tk.StringVar(value=hourly_charts_dir)
        self.hourly_dir_entry = ttk.Entry(self.hourly_dir_frame, textvariable=self.hourly_dir_var, width=30)
        self.hourly_dir_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.hourly_dir_btn = ttk.Button(self.hourly_dir_frame, text="Browse", 
                                         command=lambda: self.select_directory("hourly"))
        self.hourly_dir_btn.pack(side=tk.LEFT, padx=5)

        # Hourly CSV directory
        self.csv_dir_frame = ttk.Frame(self.dir_frame)
        self.csv_dir_frame.pack(fill=tk.X, pady=5)

        self.csv_dir_label = ttk.Label(self.csv_dir_frame, text="Hourly CSV Directory: ")
        self.csv_dir_label.pack(side=tk.LEFT, padx=5)

        self.csv_dir_var = tk.StringVar(value=hourly_csv_dir)
        self.csv_dir_entry = ttk.Entry(self.csv_dir_frame, textvariable=self.csv_dir_var, width=30)
        self.csv_dir_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.csv_dir_btn = ttk.Button(self.csv_dir_frame, text="Browse", 
                                      command=lambda: self.select_directory("csv"))
        self.csv_dir_btn.pack(side=tk.LEFT, padx=5)

        # Custom time settings
        self.custom_time_frame = ttk.LabelFrame(settings_frame, text="Time Settings")
        self.custom_time_frame.pack(fill=tk.X, pady=10, padx=10)

        self.custom_time_var = tk.BooleanVar(value=use_custom_time)
        self.custom_time_check = ttk.Checkbutton(self.custom_time_frame, text="Use Custom Time", 
                                                 variable=self.custom_time_var)
        self.custom_time_check.pack(anchor=tk.W, padx=5, pady=5)

        self.custom_time_entry_frame = ttk.Frame(self.custom_time_frame)
        self.custom_time_entry_frame.pack(fill=tk.X, pady=5)

        self.custom_time_label = ttk.Label(self.custom_time_entry_frame, text="Custom Start Time: ")
        self.custom_time_label.pack(side=tk.LEFT, padx=5)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.custom_time_entry = ttk.Entry(self.custom_time_entry_frame, width=20)
        self.custom_time_entry.insert(0, current_time)
        self.custom_time_entry.pack(side=tk.LEFT, padx=5)

        # Save settings button
        self.save_settings_btn = ttk.Button(settings_frame, text="Save Settings", command=self.save_settings)
        self.save_settings_btn.pack(pady=20)

    def select_directory(self, dir_type):
        directory = filedialog.askdirectory()
        if directory:
            if dir_type == "hourly":
                self.hourly_dir_var.set(directory)
            elif dir_type == "csv":
                self.csv_dir_var.set(directory)

    def show_calendar(self):
        # A simple date picker dialog could be implemented here
        # For now, we'll just show a message
        messagebox.showinfo("Calendar", "Calendar functionality to be implemented.")

    def save_settings(self):
        global INACTIVITY_THRESHOLD, hourly_charts_dir, hourly_csv_dir, use_custom_time, time_offset
        
        # Update inactivity threshold
        INACTIVITY_THRESHOLD = self.threshold_var.get()
        
        # Update directories
        hourly_charts_dir = self.hourly_dir_var.get()
        hourly_csv_dir = self.csv_dir_var.get()
        
        # Ensure directories exist
        os.makedirs(hourly_charts_dir, exist_ok=True)
        os.makedirs(hourly_csv_dir, exist_ok=True)
        
        # Update custom time settings
        use_custom_time = self.custom_time_var.get()
        if use_custom_time:
            try:
                custom_start_time = datetime.strptime(self.custom_time_entry.get(), "%Y-%m-%d %H:%M:%S")
                time_offset = custom_start_time - datetime.now()
            except ValueError:
                messagebox.showerror("Error", "Invalid date format. Use YYYY-MM-DD HH:MM:SS")
                return
        else:
            time_offset = timedelta(0)
        
        messagebox.showinfo("Settings Saved", "Settings have been updated successfully.")

    def start_tracking(self):
        global is_running, last_activity_time, inactivity_start_time, inactivity_periods
        global last_checked_hour, last_checked_day, mouse_listener, keyboard_listener, main_thread, status_update_thread
        
        # Initialize tracking values
        is_running = True
        self.start_time = datetime.now() 
        last_activity_time = get_current_time()
        inactivity_start_time = None
        inactivity_periods = []
        last_checked_hour = get_current_time().hour
        last_checked_day = get_current_time().day
        
        # Start listeners for mouse and keyboard
        mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
        keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        
        mouse_listener.start()
        keyboard_listener.start()
        
        # Start the main tracking thread
        main_thread = threading.Thread(target=self.tracking_loop, daemon=True)
        main_thread.start()
        
        # Start status update thread
        status_update_thread = threading.Thread(target=self.update_status_file, daemon=True)
        status_update_thread.start()
        
        # Start UI update thread
        self.start_ui_updates()
        
        # Update UI
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Status: Running")
        
        # Update log
        self.add_to_log(f"Tracking started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Create status file
        self.create_status_file()

    def stop_tracking(self):
        global is_running, mouse_listener, keyboard_listener
        
        if not is_running:
            return
        
        is_running = False
        
        # Stop listeners
        if mouse_listener:
            mouse_listener.stop()
        
        if keyboard_listener:
            keyboard_listener.stop()
        
        # Update UI
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Status: Not running")
        
        # Update log
        self.add_to_log(f"Tracking stopped at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Update status file
        with open("program_status.txt", "w") as status_file:
            status_file.write(f"Program started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            status_file.write(f"Program stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            status_file.write("Status: STOPPED\n")

    def tracking_loop(self):
        global is_running, last_checked_hour, last_checked_day, inactivity_start_time, inactivity_periods
        
        start_time = datetime.now()
        
        try:
            while is_running:
                time.sleep(0.5)
                
                current_time = get_current_time()
                
                # Check for inactivity
                inactive_seconds = (current_time - last_activity_time).total_seconds()
                
                # Start inactivity period if threshold is reached and we're not already tracking inactivity
                if inactive_seconds >= INACTIVITY_THRESHOLD and not inactivity_start_time:
                    inactivity_start_time = last_activity_time
                    logging.info(f"Inactivity detected. Start time: {inactivity_start_time}")
                    self.add_to_log(f"Inactivity started at {inactivity_start_time.strftime('%H:%M:%S')}")
                
                # Handle hour change - Process charts exactly at hour boundary
                if current_time.hour != last_checked_hour:
                    logging.info(f"Hour change detected: {last_checked_hour} -> {current_time.hour}")
                    
                    # Calculate the exact hour boundary for the completed hour
                    previous_hour = last_checked_hour
                    hour_date = current_time.date()
                    
                    # Adjust date if crossing midnight
                    if current_time.hour == 0:
                        previous_hour = 23
                        hour_date = hour_date - timedelta(days=1)
                    
                    # Create exact timestamps for hour boundaries
                    hour_start = datetime.combine(hour_date, datetime.min.time().replace(hour=previous_hour))
                    hour_end = hour_start + timedelta(hours=1)
                    
                    logging.info(f"Processing data for hour: {hour_start} to {hour_end}")
                    
                    # If we're in an inactivity period that spans the hour change, log it up to the hour boundary
                    if inactivity_start_time and inactivity_start_time < hour_end:
                        log_inactivity(inactivity_start_time, hour_end)
                        inactivity_start_time = hour_end  # Continue inactivity from the new hour
                    
                    # Generate CSV for the completed hour - only include periods that belong to this hour
                    hour_inactivity = []
                    for start, end in inactivity_periods:
                        # Only include periods that overlap with this hour
                        if start < hour_end and end > hour_start:
                            # Clip to hour boundary
                            adjusted_start = max(start, hour_start)
                            adjusted_end = min(end, hour_end)
                            hour_inactivity.append((adjusted_start, adjusted_end))
                    
                    # Format filename with exact hour information
                    hourly_csv_name = os.path.join(hourly_csv_dir, f'{hour_start.strftime("%Y-%m-%d_%H")}.csv')
                    generate_csv_log(hour_inactivity, hourly_csv_name)
                    
                    # Generate chart with the correct hour label and time period
                    if previous_hour == 23:
                        title = f'23rd hour ------ {hour_date.strftime("%d %B %Y")}'
                    else:
                        title = f'{previous_hour} to {(previous_hour + 1) % 24} ----- {hour_date.strftime("%d %B %Y")}'
                    
                    # Use the exact hour for chart generation
                    generate_hourly_bar_chart(hourly_csv_name, title, (previous_hour + 1) % 24, hour_end)
                    
                    # Remove logged inactivity periods that are completely before the new hour
                    inactivity_periods = [(start, end) for start, end in inactivity_periods if end > hour_end]
                    
                    # Update last checked hour
                    last_checked_hour = current_time.hour
                    
                    # Update log
                    self.add_to_log(f"Hour change processed: {previous_hour} -> {current_time.hour}")
                
                # Handle day change
                if current_time.day != last_checked_day:
                    logging.info(f"Day change detected: {last_checked_day} -> {current_time.day}")
                    
                    # Reset for new day
                    last_checked_day = current_time.day
                    
                    # Clear old inactivity periods (optional)
                    day_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
                    inactivity_periods = [(start, end) for start, end in inactivity_periods if end > day_start]
                    
                    # Update log
                    self.add_to_log(f"Day change processed: {(day_start - timedelta(days=1)).strftime('%Y-%m-%d')} -> {day_start.strftime('%Y-%m-%d')}")
        
        except Exception as e:
            logging.error(f"Error in tracking loop: {str(e)}")
            self.add_to_log(f"Error: {str(e)}")
            
            # Update status file
            with open("program_status.txt", "w") as status_file:
                status_file.write(f"Program started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                status_file.write(f"Program crashed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                status_file.write("Status: ERROR\n")
                status_file.write(f"Error message: {str(e)}\n")

    def update_status_file(self):
        while is_running:
            with open("program_status.txt", "w") as status_file:
                status_file.write(f"Program started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                status_file.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                status_file.write("Status: RUNNING\n")
                status_file.write(f"Tracking inactivity periods: {len(inactivity_periods)}\n")
            time.sleep(300)  # Update every 5 minutes

    def create_status_file(self):
        with open("program_status.txt", "w") as status_file:
            status_file.write(f"Program started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            status_file.write("Status: RUNNING\n")

    def start_ui_updates(self):
        # Start a timer to update UI elements
        self.update_ui()
        
    def update_ui(self):
        if not is_running:
            return
            
        # Update time running
        if self.start_time: 
            running_time = datetime.now() - self.start_time
            hours, remainder = divmod(running_time.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.time_label.config(text=f"Time running: {int(hours):02}:{int(minutes):02}:{int(seconds):02}")
        
        # Update inactivity time
        total_inactivity = sum((end - start).total_seconds() for start, end in inactivity_periods)
        if inactivity_start_time:
            total_inactivity += (get_current_time() - inactivity_start_time).total_seconds()
        
        hours, remainder = divmod(total_inactivity, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.inactivity_label.config(text=f"Total inactivity: {int(hours):02}:{int(minutes):02}:{int(seconds):02}")
        
        # Update inactivity percentage
        if running_time.total_seconds() > 0:
            percentage = (total_inactivity / running_time.total_seconds()) * 100
            self.percentage_label.config(text=f"Inactivity percentage: {percentage:.2f}%")
        
        # Update current status
        if inactivity_start_time:
            self.current_status_label.config(text="Currently: Inactive")
            self.activity_status.config(text="Activity: Inactive")
        else:
            self.current_status_label.config(text="Currently: Active")
            self.activity_status.config(text="Activity: Active")
        
        # Schedule the next update
        self.root.after(1000, self.update_ui)

    def add_to_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def refresh_live_view(self):
        view_type = self.view_type.get()
        
        # Clear the current figure
        self.fig.clf()
        
        if view_type == "Current Hour":
            self.display_current_hour()
        elif view_type == "Today's Summary":
            self.display_daily_summary()
        
        self.canvas.draw()
    
    def toggle_auto_refresh(self):
        if self.auto_refresh_var.get():
            # Start auto refresh
            self.refresh_live_view()
            self.schedule_auto_refresh()
        else:
            # Cancel auto refresh if scheduled
            if self.live_view_timer:
                self.root.after_cancel(self.live_view_timer)
                self.live_view_timer = None
    
    def schedule_auto_refresh(self):
        # Cancel any existing timer
        if self.live_view_timer:
            self.root.after_cancel(self.live_view_timer)
        
        # Schedule next refresh in 30 seconds
        self.live_view_timer = self.root.after(30000, self.auto_refresh_callback)
    
    def auto_refresh_callback(self):
        self.refresh_live_view()
        self.schedule_auto_refresh()
    
    def display_current_hour(self):
        current_time = get_current_time()
        hour_start = current_time.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)
        
        ax = self.fig.add_subplot(111)
        ax.set_facecolor('#E60039')
        self.fig.patch.set_facecolor('#E60039')
        
        ax.set_xlim(hour_start, hour_end)
        
        # Apply gradient background
        background_cmap = LinearSegmentedColormap.from_list("background_cmap", list(zip([0, 1], ["#000000", "#333333"])))
        apply_gradient(ax, [mdates.date2num(hour_start), mdates.date2num(hour_end), 0, 1], background_cmap)
        
        # Plot current inactivity periods
        total_inactive_time = timedelta()
        for start, end in inactivity_periods:
            if start < hour_end and end > hour_start:
                adjusted_start = max(start, hour_start)
                adjusted_end = min(end, hour_end)
                
                if adjusted_start < adjusted_end:
                    ax.axvspan(adjusted_start, adjusted_end, facecolor='white', edgecolor='black', hatch='///', alpha=0.5)
                    total_inactive_time += adjusted_end - adjusted_start
        
        # Add current inactivity period if exists
        if inactivity_start_time and inactivity_start_time < hour_end:
            adjusted_start = max(inactivity_start_time, hour_start)
            adjusted_end = current_time
            
            if adjusted_start < adjusted_end:
                ax.axvspan(adjusted_start, adjusted_end, facecolor='white', edgecolor='black', hatch='///', alpha=0.5)
                total_inactive_time += adjusted_end - adjusted_start
        
        # Set up time axis
        ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=15))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        
        # Add title
        title = f'Current Hour ({hour_start.strftime("%H:00")}-{hour_end.strftime("%H:00")}) - {hour_start.strftime("%d %B %Y")}'
        ax.set_title(title, color='#C0C0C0', fontsize=16, fontweight='bold', pad=20)
        
        ax.tick_params(axis='x', colors='white', labelsize=12)
        ax.xaxis.set_visible(True)
        ax.yaxis.set_visible(False)
        
        # Calculate metrics
        total_inactive_minutes = total_inactive_time.total_seconds() / 60
        elapsed_minutes = (min(current_time, hour_end) - hour_start).total_seconds() / 60
        
        if elapsed_minutes > 0:
            total_inactive_percentage = (total_inactive_minutes / elapsed_minutes) * 100
        else:
            total_inactive_percentage = 0
        
        # Add metrics as text
        self.fig.text(0.85, 0.8, f"{total_inactive_minutes:.2f}",
                      fontsize=24, color='yellow', ha='left', va='center', fontweight='bold')
        
        self.fig.text(0.85, 0.3, f"{total_inactive_percentage:.2f}%",
                      fontsize=24, color='silver', ha='left', va='center', fontweight='bold')
        
        # Add labels
        self.fig.text(0.85, 0.9, "Minutes Inactive:",
                      fontsize=12, color='white', ha='left', va='center')
        
        self.fig.text(0.85, 0.4, "Percentage Inactive:",
                      fontsize=12, color='white', ha='left', va='center')
        
        # Save path for later use
        self.current_chart_path = os.path.join(
            hourly_charts_dir, 
            hour_start.strftime('%d %B %Y'), 
            f"{hour_start.strftime('%d %B %Y_%H')}.png"
        )
    
    def display_daily_summary(self):
        current_time = get_current_time()
        day_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        ax = self.fig.add_subplot(111)
        ax.set_facecolor('#40E0D0')
        self.fig.patch.set_facecolor('#40E0D0')
        
        ax.set_xlim(day_start, day_end)
        
        # Apply gradient background
        background_cmap = LinearSegmentedColormap.from_list("background_cmap", list(zip([0, 1], ["#000000", "#333333"])))
        apply_gradient(ax, [mdates.date2num(day_start), mdates.date2num(day_end), 0, 1], background_cmap)
        
        # Collect all inactivity periods for the day
        total_inactive_time = timedelta()
        for start, end in inactivity_periods:
            if start < day_end and end > day_start:
                adjusted_start = max(start, day_start)
                adjusted_end = min(end, day_end)
                
                if adjusted_start < adjusted_end:
                    ax.axvspan(adjusted_start, adjusted_end, facecolor='white', edgecolor='black', hatch='///', alpha=0.5)
                    total_inactive_time += adjusted_end - adjusted_start
        
        # Add current inactivity period if exists
        if inactivity_start_time and inactivity_start_time < day_end:
            adjusted_start = max(inactivity_start_time, day_start)
            adjusted_end = current_time
            
            if adjusted_start < adjusted_end:
                ax.axvspan(adjusted_start, adjusted_end, facecolor='white', edgecolor='black', hatch='///', alpha=0.5)
                total_inactive_time += adjusted_end - adjusted_start
        
        # Set up time axis
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
        
        # Add title
        title = f"Today's Summary - {day_start.strftime('%d %B %Y')}"
        ax.set_title(title, color='#000080', fontsize=16, fontweight='bold', pad=20)
        
        ax.tick_params(axis='x', colors='#000080', labelsize=12)
        ax.xaxis.set_visible(True)
        ax.yaxis.set_visible(False)
        
        # Calculate metrics
        total_inactive_hours = total_inactive_time.total_seconds() / 3600
        elapsed_hours = (min(current_time, day_end) - day_start).total_seconds() / 3600
        
        if elapsed_hours > 0:
            total_inactive_percentage = (total_inactive_hours / elapsed_hours) * 100
        else:
            total_inactive_percentage = 0
        
        # Add metrics as text with conditional coloring
        if total_inactive_hours <= 10:
            inactive_hours_color = '#004D40'
            inactive_pct_color = '#002171'
        elif total_inactive_hours > 10 and total_inactive_hours < 15:
            inactive_hours_color = '#B71C1C'
            inactive_pct_color = '#4A148C'
        else:
            inactive_hours_color = '#1B5E20'
            inactive_pct_color = '#BF360C'
        
        self.fig.text(0.85, 0.8, f"{total_inactive_hours:.2f}",
                      fontsize=24, color=inactive_hours_color, ha='left', va='center', fontweight='bold')
        
        self.fig.text(0.83, 0.3, f"{total_inactive_percentage:.2f}%",
                      fontsize=24, color=inactive_pct_color, ha='left', va='center', fontweight='bold')
        
        # Save path for later use
        self.current_chart_path = os.path.join(
            'daily_charts',
            f"{day_start.strftime('%Y-%m-%d')}.png"
        )
    
    def save_current_chart(self):
        if not self.current_chart_path:
            messagebox.showinfo("Save Chart", "No chart to save.")
            return
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.current_chart_path), exist_ok=True)
        
        # Save the figure
        self.fig.savefig(self.current_chart_path)
        messagebox.showinfo("Save Chart", f"Chart saved to: {self.current_chart_path}")
    
    def load_statistics(self):
        try:
            selected_date = datetime.strptime(self.date_entry.get(), "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Invalid date format. Use YYYY-MM-DD")
            return
        
        # Clear previous hour data
        for widget in self.hourly_scrollable_frame.winfo_children():
            widget.destroy()
        
        # Check if we have data for this date
        date_str = selected_date.strftime('%Y-%m-%d')
        daily_data = []
        
        # Look for hourly CSV files
        for i in range(24):
            file_name = os.path.join(hourly_csv_dir, f'{date_str}_{i:02d}.csv')
            if os.path.exists(file_name):
                try:
                    df = pd.read_csv(file_name)
                    if not df.empty:
                        df['Start Time'] = pd.to_datetime(df['Start Time'])
                        df['End Time'] = pd.to_datetime(df['End Time'])
                        
                        # Calculate total inactive time for this hour
                        total_inactive = sum((row['End Time'] - row['Start Time']).total_seconds() / 60 for _, row in df.iterrows())
                        
                        daily_data.append({
                            'hour': i,
                            'inactive_minutes': total_inactive,
                            'inactive_percentage': (total_inactive / 60) * 100
                        })
                        
                        # Add to hourly breakdown
                        hour_frame = ttk.Frame(self.hourly_scrollable_frame)
                        hour_frame.pack(fill=tk.X, pady=5)
                        
                        hour_label = ttk.Label(hour_frame, text=f"{i:02d}:00 - {(i+1) % 24:02d}:00", width=15)
                        hour_label.pack(side=tk.LEFT, padx=5)
                        
                        inactive_label = ttk.Label(hour_frame, text=f"{total_inactive:.2f} min", width=15)
                        inactive_label.pack(side=tk.LEFT, padx=5)
                        
                        percent_label = ttk.Label(hour_frame, text=f"{(total_inactive / 60) * 100:.2f}%", width=15)
                        percent_label.pack(side=tk.LEFT, padx=5)
                        
                        # Add a progress bar
                        progress = ttk.Progressbar(hour_frame, length=200, maximum=100, 
                                                  value=(total_inactive / 60) * 100)
                        progress.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
                except Exception as e:
                    logging.error(f"Error loading hour {i}: {str(e)}")
        
        # Update summary
        if daily_data:
            total_inactive_minutes = sum(hour['inactive_minutes'] for hour in daily_data)
            total_hours = len(daily_data)
            total_inactive_percentage = sum(hour['inactive_percentage'] for hour in daily_data) / total_hours if total_hours > 0 else 0
            
            self.total_inactive_label.config(text=f"Total Inactive Time: {total_inactive_minutes:.2f} minutes ({total_inactive_minutes/60:.2f} hours)")
            self.total_active_label.config(text=f"Total Active Time: {(total_hours * 60 - total_inactive_minutes):.2f} minutes ({(total_hours - total_inactive_minutes/60):.2f} hours)")
            self.inactive_percent_label.config(text=f"Inactive Percentage: {total_inactive_percentage:.2f}%")
        else:
            self.total_inactive_label.config(text="Total Inactive Time: No data available")
            self.total_active_label.config(text="Total Active Time: No data available")
            self.inactive_percent_label.config(text="Inactive Percentage: No data available")
            
            # Show message in hourly frame
            no_data_label = ttk.Label(self.hourly_scrollable_frame, text="No data available for selected date")
            no_data_label.pack(pady=20)
    
    def on_closing(self):
        if is_running:
            if messagebox.askyesno("Quit", "Tracking is still running. Do you want to stop tracking and quit?"):
                self.stop_tracking()
                self.root.destroy()
        else:
            self.root.destroy()


# Function to get the current time (either real or custom)
def get_current_time():
    return datetime.now() + time_offset


# Function to log inactivity
def log_inactivity(start_time, end_time):
    # Only log if there's a meaningful duration
    if (end_time - start_time).total_seconds() > 0:
        inactivity_periods.append((start_time, end_time))
        logging.info(f"Inactivity logged from {start_time} to {end_time}")


# Update last activity time and log inactivity if necessary
def update_activity_time():
    global last_activity_time, inactivity_start_time
    current_time = get_current_time()

    # If we were in an inactivity period, log it before updating
    if inactivity_start_time:
        log_inactivity(inactivity_start_time, current_time)
        inactivity_start_time = None
        logging.info(f"Activity resumed at {current_time}")

    last_activity_time = current_time


# Mouse and keyboard event handlers
def on_move(x, y):
    update_activity_time()


def on_click(x, y, button, pressed):
    update_activity_time()


def on_scroll(x, y, dx, dy):
    update_activity_time()


def on_press(key):
    update_activity_time()


def on_release(key):
    update_activity_time()


def apply_gradient(ax, extent, cmap, alpha=1):
    """Apply a gradient background to a plot."""
    gradient = np.linspace(0, 1, 256)
    gradient = np.vstack((gradient, gradient))
    ax.imshow(gradient, aspect='auto', cmap=cmap, extent=extent, alpha=alpha, origin='lower', zorder=-10)


# Function to generate bar chart for the hourly periods
def generate_hourly_bar_chart(file_name, title, hour_display, exact_end_time):
    try:
        # Check if font file exists, otherwise use default
        font_path = 'fonts/TrajanPro-Regular.ttf'
        if os.path.exists(font_path):
            trajan_font = FontProperties(fname=font_path, size=18)
        else:
            trajan_font = FontProperties(size=18)  # Use default font if custom font not found

        # Calculate exact hour boundaries based on the exact end time
        hour_end = exact_end_time
        hour_start = hour_end - timedelta(hours=1)

        logging.info(f"Generating hourly bar chart for period: {hour_start} to {hour_end}. File: {file_name}")

        # Check if file exists
        if not os.path.exists(file_name):
            logging.warning(f"CSV file not found: {file_name}")
            return

        df = pd.read_csv(file_name)
        if df.empty:
            logging.info(f"No inactivity data for hour {hour_display}")
            return

        df['Start Time'] = pd.to_datetime(df['Start Time'])
        df['End Time'] = pd.to_datetime(df['End Time'])

        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=200)
        ax.set_facecolor('#E60039')
        fig.patch.set_facecolor('#E60039')

        ax.set_xlim(hour_start, hour_end)
        apply_gradient(ax, [mdates.date2num(hour_start), mdates.date2num(hour_end), 0, 1], 
                      LinearSegmentedColormap.from_list("background_cmap", list(zip([0, 1], ["#000000", "#333333"]))))

        total_inactive_time = timedelta()
        for _, row in df.iterrows():
            adjusted_start = max(row['Start Time'], hour_start)
            adjusted_end = min(row['End Time'], hour_end)

            if adjusted_start < adjusted_end:
                ax.axvspan(adjusted_start, adjusted_end, facecolor='white', edgecolor='black', hatch='///', alpha=0.5)
                total_inactive_time += adjusted_end - adjusted_start

        ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=15))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

        ax.set_title(title, fontproperties=trajan_font, color='#C0C0C0', fontsize=40, fontweight='bold', pad=20)
        ax.tick_params(axis='x', colors='white', labelsize=21)
        ax.xaxis.set_visible(True)
        ax.yaxis.set_visible(False)

        # Calculate metrics - ensure proper values
        total_inactive_minutes = total_inactive_time.total_seconds() / 60
        total_inactive_percentage = (total_inactive_minutes / 60) * 100

        # Add the metrics text with better positioning and visibility
        # Number of minutes - yellow text
        fig.text(0.85, 0.8, f"{total_inactive_minutes:.2f}",
                 fontproperties=trajan_font,
                 fontsize=55,
                 color='yellow',
                 ha='left',
                 va='center',
                 fontweight='bold')

        # Percentage - silver text
        fig.text(0.85, 0.3, f"{total_inactive_percentage:.2f}%",
                 fontproperties=trajan_font,
                 fontsize=55,
                 color='silver',
                 ha='left',
                 va='center',
                 fontweight='bold')

        # Add labels for clarity
        fig.text(0.85, 0.9, "Minutes Inactive:",
                 fontproperties=trajan_font,
                 fontsize=20,
                 color='white',
                 ha='left',
                 va='center')

        fig.text(0.85, 0.4, "Percentage Inactive:",
                 fontproperties=trajan_font,
                 fontsize=20,
                 color='white',
                 ha='left',
                 va='center')

        fig.subplots_adjust(left=0.1, right=0.8, top=0.9, bottom=0.1)

        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontproperties(trajan_font)

        plt.grid(True, linestyle='--', linewidth=0.5)
        plt.tight_layout(rect=[0, 0, 0.8, 1])

        # Create directory for the date of the chart (based on hour_start)
        date_str = hour_start.strftime('%d %B %Y')
        date_dir = os.path.join(hourly_charts_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)

        # Save the plot in the directory with the correct format - using hour_start for consistent naming
        hour_label = hour_start.hour
        chart_date = f"{hour_start.strftime('%d %B %Y_')}{hour_label}"

        save_path = os.path.join(date_dir, f'{chart_date}.png')
        plt.savefig(save_path)
        plt.close()

        logging.info(f"Hourly bar chart saved: {save_path}")

    except Exception as e:
        logging.error(f"Error generating chart: {str(e)}")


# Function to generate CSV log
def generate_csv_log(inactivity_periods, file_name):
    try:
        if not inactivity_periods:
            # Create an empty CSV file
            with open(file_name, 'w') as f:
                f.write("Start Time,End Time\n")
            logging.info(f"Empty CSV log created: {file_name}")
            return
        
        df = pd.DataFrame(inactivity_periods, columns=['Start Time', 'End Time'])
        df.to_csv(file_name, index=False)
        logging.info(f"CSV log saved: {file_name}")

    except Exception as e:
        logging.error(f"Error generating CSV log: {str(e)}")


def main():
    # Create the main window
    root = tk.Tk()
    app = InactivityTrackerApp(root)
    
    # Set a custom icon (if available)
    try:
        root.iconbitmap("app_icon.ico")
    except:
        pass  # Use default icon if custom one is not available
    
    # Start the main loop
    root.mainloop()


if __name__ == "__main__":
    main()
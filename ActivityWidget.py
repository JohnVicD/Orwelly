import time
import threading
from datetime import datetime, timedelta
from pynput import mouse, keyboard
import os
import logging
import tkinter as tk
from tkinter import ttk

# Logging setup
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("desktop_widget.log"),
                        logging.StreamHandler()
                    ])

# Global variables
INACTIVITY_THRESHOLD = 60  # seconds
use_custom_time = False
time_offset = timedelta(0)
last_activity_time = None
inactivity_start_time = None
inactivity_periods = []
hourly_csv_dir = 'hourly_csv'
is_running = False
mouse_listener = None
keyboard_listener = None
main_thread = None
session_start_time = None

# Ensure directory exists
os.makedirs(hourly_csv_dir, exist_ok=True)


class DesktopWidgetApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tracker")
        
        # Make it frameless
        self.root.overrideredirect(True)
        
        # Set initial position
        self.root.geometry("180x90+50+50")
        
        # Make semi-transparent with dark background
        self.root.attributes('-alpha', 0.85)
        
        # Keep on top of other windows
        self.root.attributes('-topmost', True)
        
        # Track if we're currently moving the window
        self.dragging = False
        self.drag_x = 0
        self.drag_y = 0
        
        self.setup_gui()
        
        # Bind events for window dragging
        self.frame.bind("<ButtonPress-1>", self.start_drag)
        self.frame.bind("<ButtonRelease-1>", self.stop_drag)
        self.frame.bind("<B1-Motion>", self.on_drag)
        
        # Right-click menu
        self.setup_context_menu()
        self.frame.bind("<ButtonPress-3>", self.show_menu)

    def setup_gui(self):
        # Main frame with dark theme
        self.frame = tk.Frame(self.root, bg='#121212')
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Status indicator (small colored circle)
        self.status_frame = tk.Frame(self.frame, bg='#121212')
        self.status_frame.pack(anchor=tk.W, padx=5, pady=2)
        
        self.status_indicator = tk.Canvas(self.status_frame, width=10, height=10, 
                                         bg='#121212', highlightthickness=0)
        self.status_indicator.pack(side=tk.LEFT)
        self.status_dot = self.status_indicator.create_oval(1, 1, 9, 9, fill='#757575')  # Gray when not running
        
        # Times display with monospace font for better readability
        self.times_frame = tk.Frame(self.frame, bg='#121212')
        self.times_frame.pack(anchor=tk.W, padx=5, pady=2)
        
        self.active_label = tk.Label(self.times_frame, text="Active:", 
                                    bg='#121212', fg='#BBBBBB', font=('Consolas', 9))
        self.active_label.grid(row=0, column=0, sticky=tk.W)
        
        self.active_time = tk.Label(self.times_frame, text="00:00:00", 
                                   bg='#121212', fg='#4CAF50', font=('Consolas', 9))
        self.active_time.grid(row=0, column=1, padx=5, sticky=tk.W)
        
        self.inactive_label = tk.Label(self.times_frame, text="Inactive:", 
                                      bg='#121212', fg='#BBBBBB', font=('Consolas', 9))
        self.inactive_label.grid(row=1, column=0, sticky=tk.W)
        
        self.inactive_time = tk.Label(self.times_frame, text="00:00:00", 
                                     bg='#121212', fg='#F44336', font=('Consolas', 9))
        self.inactive_time.grid(row=1, column=1, padx=5, sticky=tk.W)
        
        # Start/Stop button
        self.btn_frame = tk.Frame(self.frame, bg='#121212')
        self.btn_frame.pack(pady=2)
        
        self.toggle_btn = tk.Button(self.btn_frame, text="▶", command=self.toggle_tracking,
                                   bg='#333333', fg='#FFFFFF', font=('Arial', 8),
                                   activebackground='#555555', activeforeground='#FFFFFF', 
                                   relief=tk.FLAT, width=2, height=1)
        self.toggle_btn.pack(side=tk.LEFT, padx=2)
        
        # Pin/Unpin button - changes alpha value from full to semi-transparent
        self.pin_btn = tk.Button(self.btn_frame, text="📌", command=self.toggle_pin,
                               bg='#333333', fg='#FFFFFF', font=('Arial', 8),
                               activebackground='#555555', activeforeground='#FFFFFF', 
                               relief=tk.FLAT, width=2, height=1)
        self.pin_btn.pack(side=tk.LEFT, padx=2)
        self.pinned = True
        
        # Close button
        self.close_btn = tk.Button(self.btn_frame, text="✕", command=self.on_close,
                                  bg='#333333', fg='#FFFFFF', font=('Arial', 8),
                                  activebackground='#555555', activeforeground='#FFFFFF', 
                                  relief=tk.FLAT, width=2, height=1)
        self.close_btn.pack(side=tk.LEFT, padx=2)

    def setup_context_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Start Tracking" if not is_running else "Stop Tracking", 
                             command=self.toggle_tracking)
        self.menu.add_command(label="Reset Statistics", command=self.reset_stats)
        self.menu.add_separator()
        self.menu.add_command(label="Always on Top", command=self.toggle_always_on_top)
        self.menu.add_command(label="Unpin" if self.pinned else "Pin", command=self.toggle_pin)
        self.menu.add_separator()
        self.menu.add_command(label="Exit", command=self.on_close)

    def show_menu(self, event):
        # Update menu items based on current state
        self.menu.entryconfigure(0, label="Stop Tracking" if is_running else "Start Tracking")
        self.menu.entryconfigure(4, label="Unpin" if self.pinned else "Pin")
        
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def toggle_always_on_top(self):
        current = self.root.attributes('-topmost')
        self.root.attributes('-topmost', not current)

    def toggle_pin(self):
        if self.pinned:
            self.root.attributes('-alpha', 0.4)  # More transparent when unpinned
            self.pinned = False
            self.pin_btn.configure(text="📍")  # Change icon
        else:
            self.root.attributes('-alpha', 0.85)  # Less transparent when pinned
            self.pinned = True
            self.pin_btn.configure(text="📌")  # Change icon

    def reset_stats(self):
        global inactivity_periods, session_start_time
        
        if is_running:
            inactivity_periods = []
            session_start_time = datetime.now()
            self.update_ui()

    def toggle_tracking(self):
        global is_running
        
        if not is_running:
            self.start_tracking()
            self.toggle_btn.config(text="⏸")
            self.status_indicator.itemconfig(self.status_dot, fill='#4CAF50')  # Green when running
        else:
            self.stop_tracking()
            self.toggle_btn.config(text="▶")
            self.status_indicator.itemconfig(self.status_dot, fill='#757575')  # Gray when not running

    def start_tracking(self):
        global is_running, last_activity_time, inactivity_start_time, inactivity_periods
        global mouse_listener, keyboard_listener, main_thread, session_start_time
        
        # Initialize tracking values
        is_running = True
        session_start_time = datetime.now()
        last_activity_time = get_current_time()
        inactivity_start_time = None
        inactivity_periods = []
        
        # Start listeners for mouse and keyboard
        mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
        keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        
        mouse_listener.start()
        keyboard_listener.start()
        
        # Start the main tracking thread
        main_thread = threading.Thread(target=self.tracking_loop, daemon=True)
        main_thread.start()
        
        # Create status file
        self.create_status_file()
        
        # Start UI updates
        self.update_ui()
        
        # Update context menu
        self.menu.entryconfigure(0, label="Stop Tracking")

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
        
        # Update status file
        with open("widget_status.txt", "w") as status_file:
            status_file.write(f"Program started at: {session_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            status_file.write(f"Program stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            status_file.write("Status: STOPPED\n")
        
        # Update context menu
        self.menu.entryconfigure(0, label="Start Tracking")

    def tracking_loop(self):
        global is_running, inactivity_start_time, inactivity_periods
        
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
                    # Update status indicator to show inactive state
                    self.root.after(0, lambda: self.status_indicator.itemconfig(self.status_dot, fill='#F44336'))  # Red when inactive
                
        except Exception as e:
            logging.error(f"Error in tracking loop: {str(e)}")
            
            # Update status file
            with open("widget_status.txt", "w") as status_file:
                status_file.write(f"Program started at: {session_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                status_file.write(f"Program crashed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                status_file.write("Status: ERROR\n")
                status_file.write(f"Error message: {str(e)}\n")

    def create_status_file(self):
        with open("widget_status.txt", "w") as status_file:
            status_file.write(f"Program started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            status_file.write("Status: RUNNING\n")

    def update_ui(self):
        if not is_running:
            return
        
        # Calculate active and inactive times
        current_time = datetime.now()
        session_duration = current_time - session_start_time
        
        # Calculate total inactive time
        total_inactive_seconds = sum((end - start).total_seconds() for start, end in inactivity_periods)
        
        # Add current inactive period if exists
        if inactivity_start_time:
            current_inactive = (get_current_time() - inactivity_start_time).total_seconds()
            total_inactive_seconds += current_inactive
            
            # Make sure status shows inactive
            self.status_indicator.itemconfig(self.status_dot, fill='#F44336')  # Red when inactive
        else:
            # Make sure status shows active
            self.status_indicator.itemconfig(self.status_dot, fill='#4CAF50')  # Green when active
        
        # Calculate active time
        total_active_seconds = session_duration.total_seconds() - total_inactive_seconds
        
        # Format times
        active_hours, active_remainder = divmod(int(total_active_seconds), 3600)
        active_minutes, active_seconds = divmod(active_remainder, 60)
        
        inactive_hours, inactive_remainder = divmod(int(total_inactive_seconds), 3600)
        inactive_minutes, inactive_seconds = divmod(inactive_remainder, 60)
        
        # Update labels
        self.active_time.config(text=f"{active_hours:02d}:{active_minutes:02d}:{active_seconds:02d}")
        self.inactive_time.config(text=f"{inactive_hours:02d}:{inactive_minutes:02d}:{inactive_seconds:02d}")
        
        # Save the stats to a file
        with open("current_stats.txt", "w") as stats_file:
            stats_file.write(f"Session start: {session_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            stats_file.write(f"Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            stats_file.write(f"Active time: {active_hours:02d}:{active_minutes:02d}:{active_seconds:02d}\n")
            stats_file.write(f"Inactive time: {inactive_hours:02d}:{inactive_minutes:02d}:{inactive_seconds:02d}\n")
            active_pct = (total_active_seconds / session_duration.total_seconds()) * 100 if session_duration.total_seconds() > 0 else 0
            stats_file.write(f"Productivity: {active_pct:.2f}%\n")
        
        # Schedule next update
        self.root.after(1000, self.update_ui)

    def start_drag(self, event):
        self.dragging = True
        self.drag_x = event.x
        self.drag_y = event.y

    def stop_drag(self, event):
        self.dragging = False

    def on_drag(self, event):
        if self.dragging:
            x = self.root.winfo_x() + event.x - self.drag_x
            y = self.root.winfo_y() + event.y - self.drag_y
            self.root.geometry(f"+{x}+{y}")

    def on_close(self):
        if is_running:
            self.stop_tracking()
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


def main():
    # Create the main window
    root = tk.Tk()
    app = DesktopWidgetApp(root)
    
    # Start the main loop
    root.mainloop()


if __name__ == "__main__":
    main()
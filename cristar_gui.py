#Final Version of GUI for the Cristar Project 
#Fixing buttons on fire command

#Activate the venv using: 
#cd /home/cristar/Documents/GUI_Development
#source .venv/bin/activate

#Code Drafted by  G. Caribe, D. Yu and A. Wainwright
#Code optimized with the assitance of ChatGPT

# ============================================================
# FEATURES
# ============================================================
# - Laser status readoutcd
# - Laser OFF + thermalize controls
# - Translation stage control
# - Sample positioning
# - Manual stage jogging
# - Auto stage advancement
# - Sensor readouts
# - SPACEBAR safety interlock
# - Keyboard hotkeys
#
# HOTKEYS (hold Control while pressing key)
#
# Control + F  -> FIRE LASER
# Control + O  -> LASER OFF
# Control + T  -> THERMALIZE
# Control + N  -> NEXT SAMPLE
# Control + G  -> GO TO SAMPLE
# Control + H  -> HOME STAGE
# Control + LEFT/RIGHT -> JOG STAGE
# ============================================================

# ============================================================
# IMPORTS
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import serial
from laser_controller import IvyLaser

import threading
import time
import csv
import os
import math
import numpy as np

from datetime import datetime

from zaber_motion import Library
from zaber_motion.ascii import Connection

import subprocess
from PIL import Image, ImageTk
import io
import board
import busio

from adafruit_bme280 import basic as adafruit_bme280

from adafruit_bno08x import (
    BNO_REPORT_ACCELEROMETER,
    BNO_REPORT_GYROSCOPE,
    BNO_REPORT_ROTATION_VECTOR
)

from adafruit_bno08x.i2c import BNO08X_I2C

# ============================================================
# SENSOR IMPORTS
# ============================================================

try:
    from sensors import (
        init_i2c,
        init_bme280,
        init_bno085
    )
    SENSORS_IMPORT_ERROR = None

except Exception as e:

    init_i2c = None
    init_bme280 = None
    init_bno085 = None

    SENSORS_IMPORT_ERROR = e

# ============================================================
# MAIN GUI
# ============================================================

class LabControlSystem:

    def __init__(self, root):
        self.root = root

        self.root.title(
            "Laser Analysis & Sample Control System"
        )

        self.root.geometry("1300x900")

        # ====================================================
        # STATE VARIABLES
        # ====================================================
        self.fire_active = False
        self.is_experimenting = False

        self.current_file = None

        self.current_sample = tk.IntVar(value=1)

        self.accel_val = tk.DoubleVar(value=0.00)
        self.temp_val = tk.DoubleVar(value=0.00)
        self.humid_val = tk.DoubleVar(value=0.00)

        self.laser_status = tk.StringVar(value="UNKNOWN")
        self.countdown_val = tk.StringVar(value="Ready")
        self.laser_ready = True
        self.cavitation_active = False

        # ====================================================
        # STAGE VARIABLES
        # ====================================================

        self.stage_position = tk.DoubleVar(value=0.0)

        self.sample_spacing = tk.DoubleVar(value=8.0)

        self.stage_busy = False

        # ====================================================
        # SENSOR STATE
        # ====================================================

        self.i2c = None
        self.bme280 = None
        self.bno = None

        self.sensor_error_logged = False

        # ====================================================
        # STAGE CONTROL
        # ====================================================

        try:

            PORT = "/dev/ttyUSB0"

            self.connection = Connection.open_serial_port(PORT)

            devices = self.connection.detect_devices()

            if len(devices) == 0:
                raise Exception("No Zaber devices detected")

            device = devices[0]

            self.axis = device.get_axis(1)

            print("Homing stage...")

            self.axis.home()

            self.zero_pos = self.axis.get_position(unit="mm")

            self.stage_position.set(
                round(self.zero_pos, 3)
            )

            print(
                f"Stage homed at {self.zero_pos:.2f} mm"
            )

        except Exception as e:

            print(f"Stage initialization failed: {e}")

            self.connection = None
            self.axis = None

        # ====================================================
        # CAMERA
        # ====================================================

        print("Launching Pi camera preview...")

        # ====================================================
        # CAMERA STREAM
        # ====================================================

        self.latest_frame = None
        self.camera_lock = threading.Lock()
        self.camera_running = True

        # =========================
        # DATA + VIDEO STATE
        # =========================

        self.logging_active = False
        self.logging_thread = None

        self.video_process = None
        self.video_start_time = None

        self.csv_file = None
        self.csv_writer = None

        # ====================================================
        # LASER CONTROL
        # ====================================================

        try:

            self.laser = IvyLaser()

            self.laser.connect()

            print("Laser connected")

        except Exception as e:

            print(f"Laser connection failed: {e}")

            self.laser = None

            return

        try:

            print("Laser initialization started...")

            self.laser.initialize(
                timeout=600,
                stability_time=3.0
            )

            print("Laser initialized")

        except Exception as e:

            print(f"Laser initialization failed: {e}")

        # ====================================================
        # FILE SETTINGS
        # ====================================================

        self.save_to_file = tk.BooleanVar(value=False)

        self.file_path_var = tk.StringVar(value="")

        # ====================================================
        # UI
        # ====================================================

        self.setup_ui()
        self.countdown_running = False

        self.start_camera_stream()

        # ====================================================
        # HOTKEY BINDINGS
        # ====================================================
        self.root.bind_all("<Control-f>", self.hotkey_fire)
        self.root.bind_all("<Control-o>", self.hotkey_off)
        self.root.bind_all("<Control-t>", self.hotkey_thermalize)
        self.root.bind_all("<Control-n>", self.hotkey_next_sample)
        self.root.bind_all("<Control-g>", self.hotkey_go_sample)
        self.root.bind_all("<Control-h>", self.hotkey_home)

        self.root.bind_all("<Control-Left>", self.hotkey_left)
        self.root.bind_all("<Control-Right>", self.hotkey_right)

        # ====================================================
        # SENSOR INIT
        # ====================================================

        self.init_sensors()

        # ====================================================
        # LOOPS
        # ====================================================

        self.update_sensors()

        self.update_laser_status()

        # ====================================================
        # CLEAN EXIT
        # ====================================================

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.on_close
        )
    # ========================================================
    # Interupt Setup
    # ========================================================

        self.after_ids = []
        self.operation_busy = False

    # ========================================================
    # UI SETUP
    # ========================================================

    def setup_ui(self):

        self.control_panel = tk.Frame(self.root)

        self.control_panel.pack(
            side=tk.LEFT,
            fill=tk.BOTH,
            expand=True,
            padx=10,
            pady=10
        )

        # ====================================================
        # CAMERA DISPLAY
        # ====================================================

        camera_frame = tk.LabelFrame(
            self.root,
            text="Live Camera",
            font=("Arial", 12, "bold")
        )

        camera_frame.pack(
            side=tk.RIGHT,
            padx=10,
            pady=10
        )


        self.video_label = tk.Label(
            camera_frame,
            width=640,
            height=480,
            bg="black"
        )

        self.video_label.pack()
        # ====================================================
        # SENSOR READOUTS
        # ====================================================

        tk.Label(
            self.control_panel,
            text="Sensor Readouts",
            font=('Arial', 14, 'bold')
        ).pack(pady=5)

        self.create_readout(
            "Acceleration (g):",
            self.accel_val
        )

        self.create_readout(
            "Temperature (°C):",
            self.temp_val
        )

        self.create_readout(
            "Humidity (%):",
            self.humid_val
        )

        tk.Frame(
            self.control_panel,
            height=2,
            bd=1,
            relief=tk.SUNKEN
        ).pack(fill=tk.X, pady=10)

        # ====================================================
        # LASER STATUS
        # ====================================================

        tk.Label(
            self.control_panel,
            text="Laser Status",
            font=('Arial', 12, 'bold')
        ).pack()

        status_frame = tk.Frame(self.control_panel)

        status_frame.pack(
            fill=tk.X,
            pady=5
        )

        tk.Label(
            status_frame,
            text="State:"
        ).pack(side=tk.LEFT)

        tk.Label(
            status_frame,
            textvariable=self.laser_status,
            fg="red",
            font=('Courier', 12, 'bold')
        ).pack(side=tk.RIGHT)

        # ====================================================
        # STAGE CONTROL
        # ====================================================

        tk.Frame(
            self.control_panel,
            height=2,
            bd=1,
            relief=tk.SUNKEN
        ).pack(fill=tk.X, pady=10)

        tk.Label(
            self.control_panel,
            text="Translation Stage Control",
            font=('Arial', 12, 'bold')
        ).pack()

        # ----------------------------------------------------
        # POSITION
        # ----------------------------------------------------

        pos_frame = tk.Frame(self.control_panel)

        pos_frame.pack(fill=tk.X, pady=2)

        tk.Label(
            pos_frame,
            text="Position (mm):"
        ).pack(side=tk.LEFT)

        tk.Label(
            pos_frame,
            textvariable=self.stage_position,
            fg="blue",
            font=('Courier', 12, 'bold')
        ).pack(side=tk.RIGHT)

        # ----------------------------------------------------
        # SAMPLE NUMBER
        # ----------------------------------------------------

        sample_frame = tk.Frame(self.control_panel)

        sample_frame.pack(fill=tk.X, pady=2)

        tk.Label(
            sample_frame,
            text="Sample #:"
        ).pack(side=tk.LEFT)

        tk.Entry(
            sample_frame,
            textvariable=self.current_sample,
            width=8
        ).pack(side=tk.RIGHT)

        # ----------------------------------------------------
        # SAMPLE SPACING
        # ----------------------------------------------------

        spacing_frame = tk.Frame(self.control_panel)

        spacing_frame.pack(fill=tk.X, pady=2)

        tk.Label(
            spacing_frame,
            text="Spacing (mm):"
        ).pack(side=tk.LEFT)

        tk.Entry(
            spacing_frame,
            textvariable=self.sample_spacing,
            width=8
        ).pack(side=tk.RIGHT)

        # ----------------------------------------------------
        # STAGE BUTTONS
        # ----------------------------------------------------

        stage_btn_frame = tk.Frame(self.control_panel)

        stage_btn_frame.pack(pady=5)

        self.btn_home = tk.Button(
            stage_btn_frame,
            text="(H)OME",
            width=10,
            command=self.home_stage
        )

        self.btn_home.grid(
            row=0,
            column=0,
            padx=2
        )


        self.btn_go_sample = tk.Button(
            stage_btn_frame,
            text="(G)O TO SAMPLE",
            width=16,
            command=self.move_platform
        )

        self.btn_go_sample.grid(
            row=0,
            column=1,
            padx=2
        )


        self.btn_next_sample = tk.Button(
            stage_btn_frame,
            text="(N)EXT",
            width=10,
            command=self.next_sample
        )

        self.btn_next_sample.grid(
            row=0,
            column=2,
            padx=2
        )

        # ----------------------------------------------------
        # JOGGING
        # ----------------------------------------------------

        jog_frame = tk.Frame(self.control_panel)

        jog_frame.pack(pady=5)

        tk.Button(
            jog_frame,
            text="← 1 mm",
            width=12,
            command=lambda: self.jog_stage(-1)
        ).grid(row=0, column=0, padx=5)

        tk.Button(
            jog_frame,
            text="1 mm →",
            width=12,
            command=lambda: self.jog_stage(1)
        ).grid(row=0, column=1, padx=5)

        tk.Frame(
            self.control_panel,
            height=2,
            bd=1,
            relief=tk.SUNKEN
        ).pack(fill=tk.X, pady=10)

        # ====================================================
        # EXPERIMENT CONTROL
        # ====================================================

        self.btn_exp = tk.Button(
            self.control_panel,
            text="START EXPERIMENT",
            bg="green",
            fg="white",
            font=('Arial', 12, 'bold'),
            command=self.toggle_experiment
        )

        self.btn_exp.pack(
            pady=10,
            fill=tk.X
        )

        self.btn_fire = tk.Button(
            self.control_panel,
            text="(F)IRE LASER",
            state=tk.DISABLED,
            bg="#2e2e2e",
            fg="#555555",
            font=('Arial', 12, 'bold'),
            command=self.fire_laser
        )

        self.btn_fire.pack(
            pady=10,
            fill=tk.X
        )

        self.btn_laser_off = tk.Button(
            self.control_panel,
            text="LASER (O)FF",
            state=tk.DISABLED,
            bg="#2e2e2e",
            fg="#555555",
            font=('Arial', 12, 'bold'),
            command=self.stop_laser
        )

        self.btn_laser_off.pack(
            pady=10,
            fill=tk.X
        )

        self.btn_thermalize = tk.Button(
            self.control_panel,
            text="(T)HERMALIZE LASER",
            state=tk.DISABLED,
            bg="#2e2e2e",
            fg="#555555",
            font=('Arial', 12, 'bold'),
            command=self.thermalize_laser
        )

        self.btn_thermalize.pack(
            pady=10,
            fill=tk.X
        )

        tk.Label(
            self.control_panel,
            text="Laser Countdown",
            font=('Arial', 12, 'bold')
        ).pack()

        tk.Label(
            self.control_panel,
            textvariable=self.countdown_val,
            fg="purple",
            font=('Courier', 14, 'bold')
        ).pack(pady=5)

    # ========================================================
    # CAMERA FUNCTIONS
    # ========================================================

    def start_camera_stream(self):

        FOCUS_POSITION = "6"

        self.camera_process = subprocess.Popen(
            [
                "rpicam-vid",
                "-t", "0",
                "--codec", "mjpeg",
                "--width", "640",
                "--height", "480",
                "--framerate", "30",
                "--autofocus-mode", "manual",
                "--lens-position",
                FOCUS_POSITION,
                "-o",
                "-",
                "--inline",
                "-n"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0
        )


        threading.Thread(
            target=self.read_camera_stream,
            daemon=True
        ).start()


        self.update_camera_display()


    def read_camera_stream(self):

        buffer = b""

        while self.camera_running:

            data = self.camera_process.stdout.read(4096)

            if not data:
                break

            buffer += data

            start = buffer.find(b"\xff\xd8")
            end = buffer.find(b"\xff\xd9")


            if start != -1 and end != -1:

                jpg = buffer[start:end+2]

                buffer = buffer[end+2:]

                try:

                    image = Image.open(
                        io.BytesIO(jpg)
                    )

                    image.load()

                    with self.camera_lock:
                        self.latest_frame = image.copy()

                    if (
                        self.logging_active and
                        hasattr(self, "video_writer") and
                        self.video_writer is not None
                    ):
                        frame = cv2.cvtColor(
                            np.array(image),
                            cv2.COLOR_RGB2BGR
                        )

                        self.video_writer.write(frame)

                except Exception:
                    pass


    def update_camera_display(self):

        if not hasattr(self, "video_label"):
            return

        if self.latest_frame is not None:

            with self.camera_lock:
                frame = self.latest_frame.copy()


            img = ImageTk.PhotoImage(frame)

            self.video_label.configure(
                image=img
            )

            self.video_label.image = img


        self.root.after(
            30,
            self.update_camera_display
        )
    # ========================================================
    # READOUT HELPER
    # ========================================================

    def create_readout(self, label, var):

        f = tk.Frame(self.control_panel)

        f.pack(fill=tk.X)

        tk.Label(
            f,
            text=label
        ).pack(side=tk.LEFT)

        tk.Label(
            f,
            textvariable=var,
            fg="blue",
            font=('Courier', 12, 'bold')
        ).pack(side=tk.RIGHT)

    #=================
    # Laser countdown
    #=================
    def start_countdown(self, seconds):

        self.countdown_running = True

        def run():
            for t in range(seconds, -1, -1):

                if not self.countdown_running:
                    return  # ✅ STOP immediately

                self.countdown_val.set(f"{t} s")
                time.sleep(1)

            if self.countdown_running:
                self.countdown_val.set("Thermalized")
                self.laser_ready = True

                self.btn_fire.config(
                    state=tk.NORMAL,
                    bg="red",
                    fg="white"
                )

        threading.Thread(target=run, daemon=True).start()
    # ========================================================
    # SENSOR INIT
    # ========================================================

    def init_sensors(self):

        if SENSORS_IMPORT_ERROR:
            return

        try:

            self.i2c = init_i2c()

            self.bme280 = init_bme280(self.i2c)

            self.bno = init_bno085(self.i2c)

            print("Sensors initialized")

        except Exception as e:

            print(f"Sensor init failed: {e}")

    # ========================================================
    # SENSOR LOOP
    # ========================================================

    def update_sensors(self):

        if self.bme280 and self.bno:

            try:

                t = self.bme280.temperature

                h = self.bme280.relative_humidity

                ax, ay, az = self.bno.acceleration

                accel = (
                    math.sqrt(
                        ax**2 +
                        ay**2 +
                        az**2
                    ) / 9.80665
                )

                self.temp_val.set(round(t, 2))

                self.humid_val.set(round(h, 2))

                self.accel_val.set(round(accel, 3))

            except Exception:
                pass

        self.root.after(
            500,
            self.update_sensors
        )

    # ========================================================
    # LASER STATUS LOOP
    # ========================================================

    def update_laser_status(self):

        if not self.laser:

            self.laser_status.set("DISCONNECTED")

            return

        try:

            if hasattr(self.laser, "get_status"):

                status = self.laser.get_status()

            elif hasattr(self.laser, "state"):

                status = self.laser.state

            else:

                self.laser_status.set("CONNECTED")

                return

            if status == 24576:

                state_str = "THERMALIZED"

            elif status == 24577:

                state_str = "EMISSION ON"

            elif status == 16384:

                state_str = "EMISSION OFF"

            elif status == 20480:

                state_str = "Thermalizing"

            else:

                state_str = f"UNKNOWN ({status})"

            self.laser_status.set(state_str)

        except Exception as e:

            self.laser_status.set(
                f"ERROR ({str(e)[:20]})"
            )

        self.root.after(
            500,
            self.update_laser_status
        )

    # ========================================================
    # STAGE FUNCTIONS
    # ========================================================
    def move_platform(self):

        if not self.axis:

            print("Stage unavailable")

            return

        if self.stage_busy:

            print("Stage already moving")

            return

        threading.Thread(
            target=self._move_platform_thread,
            daemon=True
        ).start()

    def _move_platform_thread(self):

        self.stage_busy = True

        try:

            sample = self.current_sample.get()

            spacing = self.sample_spacing.get()

            target_mm = (
                self.zero_pos +
                ((sample-1) * spacing+5)
            )

            print(f"Moving to Sample {sample}")

            print(
                f"Target position: {target_mm:.3f} mm"
            )

            self.axis.move_absolute(
                target_mm,
                unit="mm"
            )

            pos = self.axis.get_position(unit="mm")

            self.stage_position.set(round(pos, 3))

            print("Move complete")

        except Exception as e:

            print(f"Stage move failed: {e}")

        self.stage_busy = False

    def next_sample(self):

        self.current_sample.set(
            self.current_sample.get() + 1
        )

        self.move_platform()

    def home_stage(self):

        if not self.axis:
            return

        threading.Thread(
            target=self._home_stage_thread,
            daemon=True
        ).start()

    def _home_stage_thread(self):

        self.stage_busy = True

        try:

            print("Homing stage...")

            self.axis.home()

            self.zero_pos = self.axis.get_position(
                unit="mm"
            )

            self.stage_position.set(
                round(self.zero_pos, 3)
            )

            print("Stage homed")

        except Exception as e:

            print(f"Home failed: {e}")

        self.stage_busy = False

    def jog_stage(self, step_mm):

        if not self.axis:
            return

        if self.stage_busy:
            return

        threading.Thread(
            target=self._jog_stage_thread,
            args=(step_mm,),
            daemon=True
        ).start()

    def _jog_stage_thread(self, step_mm):

        self.stage_busy = True

        try:

            current = self.axis.get_position(
                unit="mm"
            )

            target = current + step_mm

            self.axis.move_absolute(
                target,
                unit="mm"
            )

            pos = self.axis.get_position(
                unit="mm"
            )

            self.stage_position.set(
                round(pos, 3)
            )

            print(f"Jogged to {pos:.3f} mm")

        except Exception as e:

            print(f"Jog failed: {e}")

        self.stage_busy = False

    # ========================================================
    # HOTKEY SAFETY
    # ========================================================

    def space_down(self, event):

        self.space_pressed = True

    def space_up(self, event):

        self.space_pressed = False

    def require_space(self):

        if not self.space_pressed:

            print("Hold SPACEBAR to enable hotkeys")

            return False

        return True

    # ========================================================
    # HOTKEYS
    # ========================================================
    def hotkey_fire(self, event):
        if self.cavitation_active:
            self.End_Cavitation()
        else:
            self.fire_laser()

    def hotkey_off(self, event):
        self.stop_laser()

    def hotkey_thermalize(self, event):
        self.thermalize_laser()

    def hotkey_next_sample(self, event):
        self.next_sample()

    def hotkey_go_sample(self, event):
        self.move_platform()

    def hotkey_home(self, event):
        self.home_stage()

    def hotkey_left(self, event):
        self.jog_stage(-1)

    def hotkey_right(self, event):
        self.jog_stage(1)

    # ========================================================
    # EXPERIMENT CONTROL
    # ========================================================

    def toggle_experiment(self):

        if not self.is_experimenting:

            self.is_experimenting = True

            self.btn_exp.config(
                text="STOP EXPERIMENT",
                bg="orange"
            )

            self.btn_fire.config(
                state=tk.NORMAL,
                bg="red",
                fg="white"
            )

            self.btn_laser_off.config(
                state=tk.NORMAL,
                bg="#8b0000",
                fg="white"
            )

            self.btn_thermalize.config(
                state=tk.NORMAL,
                bg="#444444",
                fg="white"
            )

        else:

            self.is_experimenting = False

            self.btn_exp.config(
                text="START EXPERIMENT",
                bg="green"
            )

            self.btn_fire.config(
                state=tk.DISABLED,
                bg="#2e2e2e",
                fg="#555555"
            )

            self.btn_laser_off.config(
                state=tk.DISABLED,
                bg="#2e2e2e",
                fg="#555555"
            )

            self.btn_thermalize.config(
                state=tk.DISABLED,
                bg="#2e2e2e",
                fg="#555555"
            )


    # ========================================================
    # DATA LOGGING COMMANDS
    # ========================================================

    def start_data_logging(self):

        if self.logging_active:
            print("Logging already active")
            return

        # ----------------------------
        # Timestamp
        # ----------------------------
        self.video_start_time = datetime.now()
        timestamp_str = self.video_start_time.strftime("%Y%m%d_%H%M%S")

        # ----------------------------
        # Filenames
        # ----------------------------
        sample = self.current_sample.get()

        base_dir = os.path.expanduser("~/Flight_Data")
        os.makedirs(base_dir, exist_ok=True)

        video_filename = os.path.join(
            base_dir,
            f"S{sample:03d}_video_{timestamp_str}.mp4"
        )

        csv_filename = os.path.join(
            base_dir,
            f"S{sample:03d}_log_{timestamp_str}.csv"
        )

        print("Saving to directory:", base_dir)
        print("CSV path:", csv_filename)
        print("Video path:", video_filename)

        # ----------------------------
        # Start VideoWriter
        # ----------------------------
        self.video_writer = cv2.VideoWriter(
            video_filename,
            cv2.VideoWriter_fourcc(*"mp4v"),
            30.0,
            (640, 480)
        )

        if not self.video_writer.isOpened():
            print("ERROR: Failed to open VideoWriter!")
            self.video_writer = None
            return

        # ----------------------------
        # Open CSV
        # ----------------------------
        try:
            self.csv_file = open(csv_filename, "w", newline="")
            self.csv_writer = csv.writer(self.csv_file)

        except Exception as e:
            print("CSV OPEN FAILED:", e)

            self.video_writer.release()
            self.video_writer = None
            return

        self.csv_writer.writerow([
            "Timestamp",
            "Time_s",
            "Video_Time_s",
            "Temperature_C",
            "Humidity_pct",
            "Accel_g",
            "Stage_Position_mm"
        ])

        self.csv_writer.writerow([])
        self.csv_writer.writerow(["Sample", sample])
        self.csv_writer.writerow(["Spacing_mm", self.sample_spacing.get()])
        self.csv_writer.writerow(["--- Data ---"])

        self.logging_active = True

        self.logging_thread = threading.Thread(
            target=self.logging_loop,
            daemon=True
        )

        self.logging_thread.start()

        print("Logging started.")

    def logging_loop(self):
        start_time = time.time()

        while self.logging_active:

            try:
                now = datetime.now()

                t = time.time() - start_time
                video_t = (now - self.video_start_time).total_seconds()

                # ---- stage ----
                if self.axis:
                    stage_pos = self.stage_position.get()
                    
                else:
                    stage_pos = float("nan")

                # ---- sensors ----
                temperature = self.temp_val.get()
                humidity = self.humid_val.get()
                accel = self.accel_val.get()

                # ---- write ----
                self.csv_writer.writerow([
                    now.strftime("%Y-%m-%d %H:%M:%S.%f"),
                    t,
                    video_t,
                    temperature,
                    humidity,
                    accel,
                    stage_pos
                ])

                self.csv_file.flush()

            except Exception as e:
                if not self.sensor_error_logged:
                    print(f"Logging error: {e}")
                    self.sensor_error_logged = True

            time.sleep(0.5)

    def stop_data_logging(self):

        # ----------------------------
        # Stop logging loop
        # ----------------------------
        self.logging_active = False

        if self.logging_thread:
            self.logging_thread.join(timeout=2)

        # ----------------------------
        # Close CSV file
        # ----------------------------
        if self.csv_file:
            try:
                self.csv_file.close()
            except:
                pass
            self.csv_file = None

        # ----------------------------
        # Stop video recording cleanly
        # ----------------------------
        if hasattr(self, "video_writer"):

            self.video_writer.release()

            self.video_writer = None

        # ----------------------------
        # IMPORTANT: allow camera to release
        # ----------------------------
        time.sleep(0.5)

        # ----------------------------
        # Kill any existing preview
        # ----------------------------
        if hasattr(self, "camera_process") and self.camera_process:
            try:
                self.camera_process.terminate()
                self.camera_process.wait(timeout=2)
            except:
                try:
                    self.camera_process.kill()
                except:
                    pass

        # ----------------------------
        # Restart preview cleanly
        # ----------------------------
        try:

            self.camera_running = True

            self.start_camera_stream()

            print("Embedded preview restarted")

        except Exception as e:

            print(f"Preview restart failed: {e}")

        print("Logging stopped.")
    
    # ========================================================
    # LASER COMMANDS
    # ========================================================

    def fire_laser(self):
        if self.operation_busy:
            print("System busy — cannot fire")
            return
        
        if not self.laser:
            return

        if not self.laser_ready:
            print("Laser not ready (cooling)")
            return

        try:

            # ✅ START DATA + VIDEO HERE
            self.start_data_logging()

            self.laser_ready = False

            self.laser.emission_on()
            print("LASER FIRED")

            self.disable_experiment_controls()

            self.btn_fire.config(
                state=tk.DISABLED,
                bg="#2e2e2e",
                fg="#555555"
            )

            # Switch button → END mode
            self.cavitation_active = True

            self.btn_fire.config(
                text="STOP",
                state=tk.NORMAL,
                bg="black",
                fg="yellow",
                command=self.End_Cavitation
            )

            self.btn_laser_off.config(
                state=tk.DISABLED,
                bg="#2e2e2e",
                fg="#555555"
            )

            self.btn_thermalize.config(
                state=tk.DISABLED,
                bg="#2e2e2e",
                fg="#555555"
            )

            # ---- thermalization timer ----
            self.start_countdown(18)
            
            id1 =self.root.after(18000, self.laser.thermalize)
            id4 = self.root.after(21000,self.reset_fire_button)

            # ---- Advance sample and end recording ----
            id2 =self.root.after(21000, self.next_sample)
            id3 =self.root.after(21000,self.stop_data_logging)

            self.after_ids.extend([id1, id2, id3, id4])

        except Exception as e:
            print(f"Laser fire failed: {e}")

    def reset_fire_button(self):

        self.cavitation_active = False

        self.btn_fire.config(
            text="(F)IRE LASER",
            state=tk.NORMAL,
            bg="red",
            fg="white",
            command=self.fire_laser
        )

        self.btn_laser_off.config(
            state=tk.NORMAL,
            bg="#8b0000",
            fg="white"
        )

        self.btn_thermalize.config(
            state=tk.NORMAL,
            bg="#444444",
            fg="white"
        )

        self.laser_ready = True

        self.enable_experiment_controls()
    # ========================================================
    # LASER OFF
    # ========================================================
    def stop_laser(self):
        for aid in self.after_ids:
            try:
                self.root.after_cancel(aid)
            except:
                pass

        self.after_ids.clear()

        if not self.laser:
            return

        try:
            self.stop_all_activity()
            print("LASER OFF")

        except Exception as e:
            print(f"Laser off failed: {e}")
            
    # ========================================================
    # THERMALIZE
    # ========================================================
    def thermalize_laser(self):
        for aid in self.after_ids:
            try:
                self.root.after_cancel(aid)
            except:
                pass

        self.after_ids.clear()

        if not self.laser:
            return

        try:
            self.laser.thermalize()
            print("LASER THERMALIZED")
    
        except Exception as e:
            print(f"Thermalize failed: {e}")

        try:
            self.stop_data_logging()
            print("LASER THERMALIZED (manual stop)")
        except Exception as e:
            print(f"Failed to stop logging: {e}")

# ========================================================
# Early stop
# ========================================================
    def End_Cavitation(self):
        if self.operation_busy:
            print("System busy — please wait")
            return
        
        self.btn_fire.config(state=tk.DISABLED)
        self.btn_laser_off.config(state=tk.DISABLED)
        self.btn_thermalize.config(state=tk.DISABLED)

        self.operation_busy = True

        """
        Safely stop laser emission AND all recording/logging 
        before advancing to the next sample.
        """

        self.countdown_running = False

        for aid in self.after_ids:
            try:
                self.root.after_cancel(aid)
            except:
                pass

        self.after_ids.clear()

        try:
            if self.laser:
                self.laser.thermalize()
        except Exception as e:
            print(f"Failed to Thermalize: {e}")

        # Stop logging + video
        try:
            self.stop_data_logging()
        except Exception as e:
            print(f"Failed to stop logging: {e}")

        # Reset UI state
        self.laser_ready = True
        self.countdown_val.set("Ended")
        self.next_sample()

        print("Ready for next sample.")

                # Reset toggle state
        self.cavitation_active = False

        # Reset Laser Fire Button
        self.btn_fire.config(
            text="(F)IRE LASER",
            state=tk.NORMAL,
            bg="red",
            fg="white",
            command=self.fire_laser
        )

        self.operation_busy = False

        self.btn_fire.config(
            text="(F)IRE LASER",
            state=tk.NORMAL,
            bg="red",
            fg="white",
            command=self.fire_laser
        )

        self.btn_laser_off.config(
            state=tk.NORMAL,
            bg="#8b0000",
            fg="white"
        )

        self.btn_thermalize.config(
            state=tk.NORMAL,
            bg="#444444",
            fg="white"
        )

        self.enable_experiment_controls()

# ========================================================
# Emergency stop
# ========================================================
    def stop_all_activity(self):
        self.operation_busy = False
        self.countdown_running = False
        self.cavitation_active = False

        self.enable_experiment_controls()

        # Cancel scheduled tasks
        for aid in self.after_ids:
            try:
                self.root.after_cancel(aid)
            except:
                pass

        self.after_ids.clear()
        """
        Safely stop laser emission AND all recording/logging.
        """
        try:
            if self.laser:
                self.laser.emission_off()
        except Exception as e:
            print(f"Emergency laser off failed: {e}")

        # Stop logging + video
        try:
            self.stop_data_logging()
        except Exception as e:
            print(f"Failed to stop logging: {e}")

        # Reset UI state
        self.laser_ready = True
        self.countdown_val.set("Laser OFF")

        self.btn_fire.config(
            state=tk.NORMAL,
            bg="red",
            fg="white",
            text="(F)IRE LASER",
            command=self.fire_laser
        )

        self.btn_laser_off.config(
            state=tk.NORMAL,
            bg="#8b0000",
            fg="white"
        )

        self.btn_thermalize.config(
            state=tk.NORMAL,
            bg="#444444",
            fg="white"
        )

        print("All activity stopped.")
    # ========================================================
    # CLEAN EXIT
    # ========================================================

    def on_close(self):

        print("Closing application...")


        try:
            self.stop_data_logging()
        except Exception:
            pass

        try:

            if self.laser:

                self.laser.emission_off()

                self.laser.disconnect()

        except Exception:
            pass

        try:

            if self.connection:

                self.connection.close()

        except Exception:
            pass

        try:

            self.camera_process.terminate()

        except Exception:
            pass

        self.root.destroy()

    def disable_experiment_controls(self):
            # Laser controls
            self.btn_fire.config(
                state=tk.DISABLED,
                bg="#2e2e2e",
                fg="#555555"
            )

            self.btn_thermalize.config(
                state=tk.DISABLED,
                bg="#2e2e2e",
                fg="#555555"
            )

            # Keep laser OFF available for safety
            self.btn_laser_off.config(
                state=tk.NORMAL,
                bg="#8b0000",
                fg="white"
            )

            # Stage controls
            self.btn_home.config(
                state=tk.DISABLED
            )

            self.btn_go_sample.config(
                state=tk.DISABLED
            )

            self.btn_next_sample.config(
                state=tk.DISABLED
            )
####
    def enable_experiment_controls(self):

        if self.is_experimenting:

            self.btn_fire.config(
                state=tk.NORMAL,
                bg="red",
                fg="white"
            )

            self.btn_thermalize.config(
                state=tk.NORMAL,
                bg="#444444",
                fg="white"
            )

            self.btn_laser_off.config(
                state=tk.NORMAL,
                bg="#8b0000",
                fg="white"
            )

            self.btn_home.config(state=tk.NORMAL)
            self.btn_go_sample.config(state=tk.NORMAL)
            self.btn_next_sample.config(state=tk.NORMAL)
###
# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = LabControlSystem(root)

    root.mainloop()

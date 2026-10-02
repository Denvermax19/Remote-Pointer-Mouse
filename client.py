import tkinter as tk
import ctypes
import json
import asyncio
import threading
import random
import string
import websockets

# ==================== CONFIGURATION ====================
# REPLACE WITH YOUR RENDER URL (Must start with wss://)
SERVER_URL = input("Enter your signaling server URL: ").strip()

# "wss://YOUR_RENDER_URL.onrender.com"
# ========================================================

user32 = ctypes.windll.user32


class ScreenPointerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ScreenPointer")
        self.root.geometry("350x260")

        self.ws = None
        self.loop = None
        self.code = ""
        self.role = None
        self.calibrator = None
        self.overlay = None

        self.setup_ui()

        # Start AsyncIO background thread for WebSockets
        self.thread = threading.Thread(target=self.start_async_loop, daemon=True)
        self.thread.start()

    def setup_ui(self):
        self.frame = tk.Frame(self.root, padx=15, pady=15)
        self.frame.pack(fill=tk.BOTH, expand=True)

        self.lbl_title = tk.Label(
            self.frame, text="ScreenPointer Setup", font=("Segoe UI", 14, "bold")
        )
        self.lbl_title.pack(pady=5)

        self.btn_student = tk.Button(
            self.frame,
            text="Student Mode (Receive)",
            width=25,
            height=2,
            command=self.start_student,
        )
        self.btn_student.pack(pady=5)

        self.btn_teacher = tk.Button(
            self.frame,
            text="Teacher Mode (Point)",
            width=25,
            height=2,
            command=self.start_teacher,
        )
        self.btn_teacher.pack(pady=5)

        self.lbl_status = tk.Label(self.frame, text="Ready", fg="gray")
        self.lbl_status.pack(pady=10)

    # ------------------ NETWORKING ------------------
    def start_async_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def connect_and_listen(self):
        self.lbl_status.config(text="Connecting to cloud server...")
        try:
            async with websockets.connect(SERVER_URL) as ws:
                self.ws = ws
                self.lbl_status.config(text=f"Connected! Code: {self.code}", fg="green")

                # Register room
                if self.role == "student":
                    await ws.send(
                        json.dumps({"type": "create_room", "code": self.code})
                    )
                else:
                    await ws.send(json.dumps({"type": "join_room", "code": self.code}))

                async for message in ws:
                    data = json.loads(message)
                    if data.get("type") == "peer_connected":
                        self.lbl_status.config(text="Paired with partner!", fg="blue")
                    elif data.get("type") == "signal" and self.role == "student":
                        self.update_student_overlay(data)

        except Exception as e:
            self.lbl_status.config(text="Connection lost / error.", fg="red")

    def send_ws_payload(self, data):
        if self.ws and self.loop:
            asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(data)), self.loop)

    # ------------------ STUDENT LOGIC ------------------
    def start_student(self):
        self.role = "student"
        self.code = "".join(random.choices(string.digits, k=6))
        self.btn_student.config(state="disabled")
        self.btn_teacher.config(state="disabled")

        self.setup_student_overlay()
        asyncio.run_coroutine_threadsafe(self.connect_and_listen(), self.loop)

    def setup_student_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.geometry(
            f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0"
        )
        self.overlay.attributes("-topmost", True)
        self.overlay.config(bg="black")

        # Transparent background key
        self.overlay.wm_attributes("-transparentcolor", "black")

        # Win32 Click-Through Styles
        hwnd = user32.GetParent(self.overlay.winfo_id())
        style = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(
            hwnd, -20, style | 0x80000 | 0x20
        )  # WS_EX_LAYERED | WS_EX_TRANSPARENT

        self.canvas = tk.Canvas(self.overlay, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.dot = self.canvas.create_oval(
            -50, -50, -50, -50, fill="#FF3333", outline="white", width=2
        )
        self.overlay.withdraw()

    def update_student_overlay(self, data):
        visible = data.get("visible", False)
        if visible:
            sw = self.overlay.winfo_screenwidth()
            sh = self.overlay.winfo_screenheight()
            x = int(data.get("x", 0) * sw)
            y = int(data.get("y", 0) * sh)
            r = 12

            self.root.after(
                0, lambda: self.canvas.coords(self.dot, x - r, y - r, x + r, y + r)
            )
            self.root.after(0, self.overlay.deiconify)
        else:
            self.root.after(0, self.overlay.withdraw)

    # ------------------ TEACHER LOGIC ------------------
    def start_teacher(self):
        self.role = "teacher"
        self.frame.destroy()

        # Teacher input UI for code
        self.frame = tk.Frame(self.root, padx=15, pady=15)
        self.frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(self.frame, text="Enter Student's 6-Digit Code:").pack(pady=5)
        self.ent_code = tk.Entry(self.frame, font=("Segoe UI", 12), justify="center")
        self.ent_code.pack(pady=5)

        tk.Button(self.frame, text="Connect", command=self.connect_teacher).pack(pady=5)
        self.lbl_status = tk.Label(self.frame, text="Ready", fg="gray")
        self.lbl_status.pack(pady=5)

    def connect_teacher(self):
        self.code = self.ent_code.get().strip()
        if len(self.code) == 6:
            self.setup_teacher_calibrator()
            asyncio.run_coroutine_threadsafe(self.connect_and_listen(), self.loop)

    def setup_teacher_calibrator(self):
        self.calibrator = tk.Toplevel(self.root)
        self.calibrator.title("Align Over Google Meet Screen Share Area")
        self.calibrator.geometry("700x500+100+100")
        self.calibrator.attributes("-alpha", 0.3)
        self.calibrator.config(bg="blue")

        self.poll_teacher_input()

    def poll_teacher_input(self):
        # 0x11 is VK_CONTROL
        is_ctrl = (user32.GetAsyncKeyState(0x11) & 0x8000) != 0

        point = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))

        # Check bounds of calibrator window
        wx = self.calibrator.winfo_rootx()
        wy = self.calibrator.winfo_rooty()
        ww = self.calibrator.winfo_width()
        wh = self.calibrator.winfo_height()

        inside = (wx <= point.x <= wx + ww) and (wy <= point.y <= wy + wh)
        visible = is_ctrl and inside

        if visible and ww > 0 and wh > 0:
            rel_x = (point.x - wx) / ww
            rel_y = (point.y - wy) / wh
            self.send_ws_payload(
                {"type": "signal", "x": rel_x, "y": rel_y, "visible": True}
            )
        else:
            self.send_ws_payload({"type": "signal", "visible": False})

        # Poll every 25ms (~40Hz)
        self.root.after(25, self.poll_teacher_input)


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenPointerApp(root)
    root.mainloop()

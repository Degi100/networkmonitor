import tkinter as tk
import psutil
import threading
import time
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import deque
import json
import os

class SpeedOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Netzwerk-Speed")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", 0.9)
        self.root.configure(bg="black")
        self.root.minsize(750, 140)
        self.root.geometry(f"350x140+{self.root.winfo_screenwidth()-980}+{self.root.winfo_screenheight()-180}")

        # Label oben
        self.label = tk.Label(
            self.root,
            text="↓ 00.00 Mbps  ↑ 00.00 Mbps",
            fg="lime",
            bg="black",
            font=("Consolas", 16),
            width=28,
            anchor="w"
        )
        self.label.pack(fill="x", expand=False, side="top")

        # Chart darunter
        self.history_len = 60
        self.down_history = deque([0]*self.history_len, maxlen=self.history_len)
        self.up_history = deque([0]*self.history_len, maxlen=self.history_len)
        self.fig = Figure(figsize=(3.5, 0.8), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("black")
        self.ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        self.down_line, = self.ax.plot([], [], color="lime", label="Download", linewidth=2)
        self.up_line, = self.ax.plot([], [], color="cyan", label="Upload", linewidth=2)
        self.ax.set_ylim(0, 100)
        self.ax.set_ylabel("Mbit/s", color="white", fontsize=8)
        self.ax.yaxis.label.set_color('white')
        self.ax.set_xlabel("Sekunden", color="white", fontsize=8)
        self.ax.xaxis.label.set_color('white')
        self.ax.set_xticks([0, self.history_len//2, self.history_len])
        self.ax.set_xticklabels([str(self.history_len), str(self.history_len//2), "0"], color="white", fontsize=7)
        self.ax.grid(True, color="#333333", linestyle="--", linewidth=0.5)
        self.ax.legend(loc="upper left", fontsize=6, facecolor="black", labelcolor="white")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.chart_widget = self.canvas.get_tk_widget()
        self.chart_widget.pack(fill="x", expand=False, side="top")

        # Toggle-Chart-Button ganz rechts außen (ganz links von den drei Buttons)
        self.show_chart = True  # <-- Diese Zeile VOR dem Button!
        self.toggle_btn = tk.Button(
            self.root, text="▼", command=self.toggle_chart,
            bg="gray20", fg="white", bd=0, font=("Consolas",6), width=2, height=1
        )
        self.toggle_btn.place(relx=0.88, rely=0.0, anchor="ne")

        # Minimieren-/Hide-Button in der Mitte
        self.min_btn = tk.Button(
            self.root, text="–", command=self.minimize,
            bg="gray20", fg="white", bd=0, font=("Consolas", 6), width=2, height=1
        )
        self.min_btn.place(relx=0.94, rely=0.0, anchor="ne")

        # Schließen-Button ganz rechts
        self.close_btn = tk.Button(
            self.root, text="❌", command=self.close,
            bg="gray20", fg="white", bd=0, font=("Consolas", 6), width=2, height=1
        )
        self.close_btn.place(relx=1.0, rely=0.0, anchor="ne")

        # Resize-Griff unten rechts
        self.grip = tk.Label(
            self.root,
            text="↘",
            bg="gray30",
            fg="white",
            cursor="bottom_right_corner",
            width=2,
            height=1,
            font=("Consolas", 6)
        )
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.grip.bind("<Button-1>", self.start_resize)
        self.grip.bind("<B1-Motion>", self.do_resize)

        self.running = True
        threading.Thread(target=self.update_speed, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        # Fenster verschieben mit Maus
        self.offset_x = 0
        self.offset_y = 0
        self.label.bind("<Button-1>", self.start_move)
        self.label.bind("<B1-Motion>", self.do_move)

        self.start_width_limit = self.root.winfo_width()
        self.start_height_limit = self.root.winfo_height()
        self.show_chart = True

        self.total_down = 0  # in Bytes
        self.total_up = 0    # in Bytes
        self.session_down = 0  # in Bytes
        self.session_up = 0    # in Bytes
        self.data_file = "traffic_stats.json"
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    stats = json.load(f)
                    self.total_down = stats.get("total_down", 0)
                    self.total_up = stats.get("total_up", 0)
            except Exception:
                self.total_down = 0
                self.total_up = 0

        # Session Label
        self.session_label = tk.Label(
            self.root,
            text="Session: ↓ 0.00 MB  ↑ 0.00 MB",
            fg="white",
            bg="black",
            font=("Consolas", 10),
            anchor="e",
            width=32,
            justify="center"
        )
        self.session_label.place(relx=0.5, rely=0.23, anchor="n")  # Rechts neben dem Chart, ggf. rely anpassen

    def start_move(self, event):
        self.offset_x = event.x
        self.offset_y = event.y

    def do_move(self, event):
        x = self.root.winfo_x() + event.x - self.offset_x
        y = self.root.winfo_y() + event.y - self.offset_y
        self.root.geometry(f"+{x}+{y}")

    def start_resize(self, event):
        self.start_width = self.root.winfo_width()
        self.start_height = self.root.winfo_height()
        self.start_x = event.x_root
        self.start_y = event.y_root

    def do_resize(self, event):
        min_width = self.start_width_limit
        min_height = self.start_height_limit
        new_width = max(min_width, self.start_width + (event.x_root - self.start_x))
        new_height = max(min_height, self.start_height + (event.y_root - self.start_y))
        self.root.geometry(f"{int(new_width)}x{int(new_height)}")

    def update_speed(self):
        old = psutil.net_io_counters()
        while self.running:
            time.sleep(1)
            new = psutil.net_io_counters()
            down = (new.bytes_recv - old.bytes_recv) * 8 / 1_000_000
            up = (new.bytes_sent - old.bytes_sent) * 8 / 1_000_000
            self.total_down += new.bytes_recv - old.bytes_recv
            self.total_up += new.bytes_sent - old.bytes_sent

            # Session-Zähler erhöhen
            self.session_down += new.bytes_recv - old.bytes_recv
            self.session_up += new.bytes_sent - old.bytes_sent

            # Formatierung für MB/GB
            def fmt(size):
                if size > 1024**3:
                    return f"{size/1024**3:.2f} GB"
                else:
                    return f"{size/1024**2:.2f} MB"

            self.label.config(
                text=f"↓ {down:.2f} Mbps  ↑ {up:.2f} Mbps   "
                     f"↓Σ {fmt(self.total_down)}  ↑Σ {fmt(self.total_up)}"
            )
            # Session-Label aktualisieren
            self.session_label.config(
                text=f"Session: ↓ {fmt(self.session_down)}  ↑ {fmt(self.session_up)}"
            )
            old = new
            self.down_history.append(down)
            self.up_history.append(up)
            self.update_chart()

    def update_chart(self):
        self.down_line.set_data(range(len(self.down_history)), list(self.down_history))
        self.up_line.set_data(range(len(self.up_history)), list(self.up_history))
        self.ax.set_xlim(0, self.history_len)
        max_speed = max(max(self.down_history), max(self.up_history), 10)
        self.ax.set_ylim(0, max_speed * 1.2)
        # Max/Min/Avg Download berechnen
        max_down = max(self.down_history)
        min_down = min(self.down_history)
        avg_down = sum(self.down_history) / len(self.down_history) if self.down_history else 0
        # Vorherigen Text entfernen, falls vorhanden
        if hasattr(self, "chart_text"):
            self.chart_text.remove()
        # Vorherige Legende entfernen, falls vorhanden
        if hasattr(self, "chart_legend"):
            self.chart_legend.remove()
        # Text oben links einfügen
        self.chart_text = self.ax.text(
            0.01, 0.98,
            f"Max ↓: {max_down:.2f} Mbps\n"
            f"Min ↓: {min_down:.2f} Mbps\n"
            f"Ø ↓: {avg_down:.2f} Mbps",
            color="white", fontsize=8, va="top", ha="left", transform=self.ax.transAxes,
            bbox=dict(facecolor="black", alpha=0.5, edgecolor="none", pad=2)
        )
        # Legende direkt darunter einfügen
        self.chart_legend = self.ax.legend(
            loc="upper left",
            bbox_to_anchor=(0.0, 0.32),  # etwas unterhalb von 1.0 (oben)
            fontsize=6,
            facecolor="black",
            labelcolor="white",
            framealpha=0.5
        )
        self.canvas.draw_idle()
        self.grip.lift()
        self.toggle_btn.lift()

    def toggle_chart(self):
        if self.show_chart:
            self.chart_widget.forget()
            self.toggle_btn.config(text="▲")
            self.show_chart = False
            self.root.minsize(350, 50)
            self.root.geometry(f"{max(self.root.winfo_width(), 350)}x50")
        else:
            self.chart_widget.pack(fill="x", expand=False, side="top")
            self.grip.lift()
            self.toggle_btn.lift()
            self.toggle_btn.config(text="▼")
            self.show_chart = True
            self.root.minsize(350, 140)
            self.root.geometry(f"{max(self.root.winfo_width(), 350)}x140")

    def minimize(self):
        self.root.overrideredirect(False)
        self.root.iconify()
        self.root.after(200, self.check_deiconify)

    def check_deiconify(self):
        if self.root.state() == "normal":
            self.root.overrideredirect(True)
        else:
            self.root.after(200, self.check_deiconify)

    def close(self):
        self.running = False
        # Werte speichern
        try:
            with open(self.data_file, "w") as f:
                json.dump({
                    "total_down": self.total_down,
                    "total_up": self.total_up
                }, f)
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    SpeedOverlay().run()
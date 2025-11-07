import customtkinter as ctk
from tkinter import filedialog, messagebox
import subprocess, os, threading, re, queue, time, sys, tempfile, shutil

# === Tema UI ===
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class STM32DFUProgrammer:
    def __init__(self, root):
        self.root = root
        self.root.title("STM32 DFU Programmer Pro - AERRETECHNOLOGY")
        self.root.geometry("780x520")

        self.is_flashing = False  # 🔹 flag per sospendere il polling durante il flash

        # Percorso di dfu-util.exe integrato (gestisce PyInstaller)
        if getattr(sys, 'frozen', False):
            temp_dir = os.path.join(tempfile.gettempdir(), "stm32dfu_util")
            os.makedirs(temp_dir, exist_ok=True)
            dfu_source = os.path.join(sys._MEIPASS, "dfu-util_x64", "dfu-util.exe")
            dfu_target = os.path.join(temp_dir, "dfu-util.exe")

            if not os.path.exists(dfu_target):
                try:
                    shutil.copy2(dfu_source, dfu_target)
                except Exception as e:
                    print("Errore copiando dfu-util:", e)

            self.dfu_util_path = dfu_target
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.dfu_util_path = os.path.join(base_dir, "dfu-util_x64", "dfu-util.exe")

        self.msg_q = queue.Queue()
        self.CREATE_NO_WINDOW = 0x08000000  # ✅ Evita finestre CMD

        self.build_ui()

        # Thread polling DFU
        threading.Thread(target=self.poll_dfu, daemon=True).start()
        self.root.after(50, self.process_queue)
        self.log("✅ Ready\n")

    # === Costruzione interfaccia ===
    def build_ui(self):
        title = ctk.CTkLabel(self.root, text="STM32 DFU Programmer - by AERRETECHNOLOGY", font=("Arial", 22, "bold"))
        title.pack(pady=10)

        # Selezione file
        file_frame = ctk.CTkFrame(self.root)
        file_frame.pack(pady=5)
        ctk.CTkLabel(file_frame, text="Firmware:").grid(row=0, column=0, padx=5)
        self.file_entry = ctk.CTkEntry(file_frame, width=420)
        self.file_entry.grid(row=0, column=1, padx=5)
        ctk.CTkButton(file_frame, text="Browse", width=90, command=self.browse_file).grid(row=0, column=2, padx=5)

        # Switch
        switch_frame = ctk.CTkFrame(self.root)
        switch_frame.pack(pady=5)
        self.autoconnect_switch = ctk.CTkSwitch(switch_frame, text="Auto-connect")
        self.autoconnect_switch.select()
        self.autoconnect_switch.grid(row=0, column=0, padx=15)
        self.verbose_switch = ctk.CTkSwitch(switch_frame, text="Show verbose log")
        self.verbose_switch.deselect()
        self.verbose_switch.grid(row=0, column=1, padx=15)

        # Azioni principali
        action = ctk.CTkFrame(self.root)
        action.pack(pady=5)
        self.btn_check = ctk.CTkButton(action, text="Check Device", width=130, command=self.check_device)
        self.btn_check.grid(row=0, column=0, padx=8)
        self.btn_program = ctk.CTkButton(action, text="Program", width=130, command=self.start_programming)
        self.btn_program.grid(row=0, column=1, padx=8)
        self.status = ctk.CTkLabel(action, text="Status: Unknown", text_color="yellow")
        self.status.grid(row=0, column=2, padx=8)
        self.progress = ctk.CTkProgressBar(action, width=200)
        self.progress.grid(row=0, column=3, padx=8)
        self.progress.set(0)
        self.percent = ctk.CTkLabel(action, text="0%")
        self.percent.grid(row=0, column=4, padx=8)

        # Log
        self.log_text = ctk.CTkTextbox(self.root, width=740, height=350)
        self.log_text.pack(pady=10)

    # === Log ===
    def log(self, msg):
        self.log_text.insert("end", msg)
        self.log_text.see("end")

    # === File ===
    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Binary", "*.bin")])
        if f:
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, f)

    # === Auto-connect polling ===
    def poll_dfu(self):
        last_connected = None
        while True:
            try:
                if self.is_flashing:  # 🔹 blocca il polling durante la programmazione
                    time.sleep(2)
                    continue
                if not self.autoconnect_switch.get():
                    time.sleep(2)
                    continue

                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                r = subprocess.run(
                    [self.dfu_util_path, "-l"],
                    capture_output=True,
                    text=True,
                    startupinfo=startupinfo,
                    creationflags=self.CREATE_NO_WINDOW
                )

                connected = "Found DFU" in r.stdout
                if connected != last_connected:
                    last_connected = connected
                    color = "green" if connected else "red"
                    text = "Status: Connected" if connected else "Status: Not Connected"
                    self.root.after(0, lambda: self.status.configure(text=text, text_color=color))
                    self.log("🔌 Device connected\n" if connected else "❌ Device disconnected\n")

            except Exception as e:
                self.log(f"⚠️ Poll error: {e}\n")
            time.sleep(2)

    # === Check manuale ===
    def check_device(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            r = subprocess.run(
                [self.dfu_util_path, "-l"],
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=self.CREATE_NO_WINDOW
            )
            if "Found DFU" in r.stdout:
                self.status.configure(text="Status: Connected", text_color="green")
                self.log("🔌 Device detected\n")
            else:
                self.status.configure(text="Status: Not Connected", text_color="red")
                self.log("❌ Device not detected\n")
        except Exception as e:
            self.log(f"⚠️ Error checking device: {e}\n")

    # === Avvio programmazione ===
    def start_programming(self):
        file = self.file_entry.get()
        if not file:
            return messagebox.showerror("Error", "Select firmware file")

        self.progress.set(0)
        self.percent.configure(text="0%")
        self.btn_program.configure(state="disabled")
        self.log("🚀 Starting flash...\n")
        threading.Thread(target=self.flash_process, daemon=True).start()

    # === Programmazione DFU ===
    def flash_process(self):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        cmd = [self.dfu_util_path, "-a", "0", "-D", self.file_entry.get(), "-s", "0x08000000:leave"]

        try:
            self.is_flashing = True
            self.root.after(0, lambda: self.status.configure(text="Status: Erasing memory", text_color="orange"))

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo,
                creationflags=self.CREATE_NO_WINDOW
            )

            for line in proc.stdout:
                self.msg_q.put(("log", line))
                # Aggiorna stato in base al contenuto
                if "Erase" in line:
                    self.msg_q.put(("status", ("Status: Erasing memory", "orange")))
                elif "Download" in line:
                    self.msg_q.put(("status", ("Status: Programming memory", "red")))
                elif "File downloaded successfully" in line:
                    self.msg_q.put(("status", ("Status: Verifying", "yellow")))

                m = re.search(r"(\d+)%", line)
                if m:
                    pct = int(m.group(1)) / 100
                    self.msg_q.put(("progress", pct))

            proc.wait()
            self.msg_q.put(("done", proc.returncode))

        except Exception as e:
            self.log(f"⚠️ Flash error: {e}\n")
            self.btn_program.configure(state="normal")
        finally:
            self.is_flashing = False

    # === Processa la coda UI ===
    def process_queue(self):
        try:
            while True:
                msg, data = self.msg_q.get_nowait()
                if msg == "log":
                    line = data.strip()
                    if not line:  # 🔹 ignora righe vuote
                        continue
                    if not self.verbose_switch.get():
                        skip_words = [
                            "dfu-util", "Copyright", "ABSOLUTELY NO WARRANTY",
                            "Opening DFU", "Device ID", "Device DFU", "DFU mode",
                            "Determining device status", "Clearing status", "Claiming USB",
                            "Setting Alternate", "Device returned", "DfuSe interface",
                            "Downloading element", "Transitioning", "Submitting leave",
                            "DFU state", "Warning", "Erase", "Download"]
                        if any(w.lower() in line.lower() for w in skip_words):
                            continue
                    self.log(data)

                elif msg == "progress":
                    self.progress.set(data)
                    self.percent.configure(text=f"{int(data*100)}%")

                elif msg == "status":
                    text, color = data
                    self.status.configure(text=text, text_color=color)

                elif msg == "done":
                    self.btn_program.configure(state="normal")
                    if data == 0:
                        self.log("✅ Flash complete!\n")
                        self.status.configure(text="Status: Rebooting", text_color="cyan")
                    else:
                        self.log("❌ Flash failed!\n")
                        messagebox.showerror("Error", "Programming failed")
        except queue.Empty:
            pass
        self.root.after(50, self.process_queue)


# === Avvio GUI ===
if __name__ == "__main__":
    root = ctk.CTk()
    STM32DFUProgrammer(root)
    root.mainloop()

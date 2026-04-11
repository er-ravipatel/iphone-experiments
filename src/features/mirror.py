"""
Screen mirror viewer scaffold.

This opens a separate desktop window that will host live mirroring in a later step.
For now it shows device status, setup guidance, and the exact commands needed to
prepare modern iPhones for developer services on Windows.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from ..device.info import DeviceInfo
from ..utils.runner import run


def _check_dev_mode(udid: str) -> tuple[str, str]:
    try:
        cmd = _pm3_base_command() + ["mounter", "query-developer-mode-status"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=_pm3_env(),
        )
        detail = (result.stdout or result.stderr or "").strip()
        normalized = detail.lower()
        if normalized == "true":
            return "On", "Developer Mode is enabled."
        if normalized == "false":
            return "Off", "Enable Developer Mode on the iPhone, then retry auto-mount."
        return "Unknown", detail or "Could not read developer mode status."
    except Exception as exc:
        return "Unknown", f"Could not read developer mode status: {exc}"


def _check_screenshot_service(udid: str) -> tuple[str, str]:
    temp_path = Path(tempfile.gettempdir()) / "iphone_storage_explorer_probe.png"
    if temp_path.exists():
        temp_path.unlink(missing_ok=True)

    result = run("idevicescreenshot", str(temp_path), udid=udid, timeout=20)
    if temp_path.exists():
        temp_path.unlink(missing_ok=True)
        return "Ready", "screenshotr service is reachable."

    detail = (result.stdout or result.stderr or "").strip()
    if "invalid service" in detail.lower():
        return "Blocked", "Developer Disk Image is likely not mounted yet."
    if "not found" in detail.lower():
        return "Unavailable", "idevicescreenshot is not available in PATH."
    return "Unknown", detail or "Could not probe screenshot service."


def _build_setup_commands() -> str:
    pymobiledevice3_cmd = " ".join(_pm3_base_command())

    return "\n".join(
        [
            "Recommended Windows setup commands:",
            f"1. {pymobiledevice3_cmd} mounter auto-mount",
            f"2. Run the app or terminal as Administrator, then: {pymobiledevice3_cmd} remote start-tunnel",
            f"3. {pymobiledevice3_cmd} developer dvt screenshot C:\\Users\\<you>\\Desktop\\screen.png",
            "",
            "Next backend target for this app:",
            "Use pymobiledevice3 developer services as the live mirroring source,",
            "then render frames inside this viewer window.",
        ]
    )


def _pm3_base_command() -> list[str]:
    if shutil.which("pymobiledevice3"):
        return ["pymobiledevice3"]
    return ["python", "-m", "pymobiledevice3"]


def _pm3_env() -> dict[str, str]:
    env = os.environ.copy()
    tools_dir = str(Path.home() / "libimobiledevice")
    env["PATH"] = tools_dir + os.pathsep + env.get("PATH", "")
    return env


def _is_admin_required_output(text: str) -> bool:
    lowered = text.lower()
    return "requires admin privileges" in lowered or "run-as administrator" in lowered


def open_mirror_window(info: DeviceInfo) -> None:
    root = tk.Tk()
    root.title(f"iPhone Screen Mirror - {info.name}")
    root.geometry("1100x720")
    root.minsize(900, 620)
    root.configure(bg="#111111")

    title_var = tk.StringVar(value=f"{info.name}  |  {info.model}  |  iOS {info.ios_version}")
    dev_mode_var = tk.StringVar(value="Checking developer mode...")
    screenshot_var = tk.StringVar(value="Checking screenshot service...")
    footer_var = tk.StringVar(value="Viewer scaffold ready. Live stream backend is the next step.")
    tunnel_var = tk.StringVar(value="Tunnel: Not started")
    tunnel_proc: subprocess.Popen[str] | None = None

    def refresh_status() -> None:
        dev_status, dev_detail = _check_dev_mode(info.udid)
        shot_status, shot_detail = _check_screenshot_service(info.udid)
        dev_mode_var.set(f"Developer Mode: {dev_status}  |  {dev_detail}")
        screenshot_var.set(f"Mirror Service: {shot_status}  |  {shot_detail}")

        if shot_status == "Ready":
            footer_var.set("Device developer services look ready. A live stream backend can be attached here.")
        elif shot_status == "Blocked":
            footer_var.set("Mount the Developer Disk Image first, then retry mirroring.")
        else:
            footer_var.set("Waiting for developer services. Use the setup commands on the right.")

    def append_log(text: str) -> None:
        log.configure(state="normal")
        log.insert("end", text.rstrip() + "\n")
        log.see("end")
        log.configure(state="disabled")

    def run_pm3_task(title: str, args: list[str], on_success=None, success_hint: str | None = None) -> None:
        append_log(f"\n== {title} ==")
        footer_var.set(f"{title} in progress...")

        def worker() -> None:
            cmd = _pm3_base_command() + args
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    env=_pm3_env(),
                )
                output = (result.stdout or result.stderr or "").strip() or "(no output)"

                def finish() -> None:
                    append_log(output)
                    if _is_admin_required_output(output):
                        footer_var.set(f"{title} requires running the app as Administrator.")
                    elif result.returncode == 0:
                        footer_var.set(success_hint or f"{title} completed.")
                        if on_success:
                            on_success()
                    else:
                        footer_var.set(f"{title} failed.")
                    refresh_status()

                root.after(0, finish)
            except Exception as exc:
                root.after(0, lambda: (append_log(str(exc)), footer_var.set(f"{title} failed.")))

        threading.Thread(target=worker, daemon=True).start()

    def mount_now() -> None:
        run_pm3_task(
            "Auto-mounting Developer Disk Image",
            ["mounter", "auto-mount"],
            success_hint="Developer Disk Image mount attempted. Refreshing status...",
        )

    def auto_prepare() -> None:
        mount_now()

        def delayed_tunnel() -> None:
            root.after(2500, start_tunnel)

        root.after(100, delayed_tunnel)

    def start_tunnel() -> None:
        nonlocal tunnel_proc
        if tunnel_proc and tunnel_proc.poll() is None:
            footer_var.set("Tunnel is already running.")
            return

        append_log("\n== Starting Remote Tunnel ==")
        footer_var.set("Starting remote tunnel...")

        cmd = _pm3_base_command() + ["remote", "start-tunnel"]
        try:
            tunnel_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=_pm3_env(),
                bufsize=1,
            )
            tunnel_var.set(f"Tunnel: Starting (PID {tunnel_proc.pid})")

            def consume() -> None:
                assert tunnel_proc is not None
                for line in tunnel_proc.stdout or []:
                    root.after(0, lambda msg=line.rstrip(): append_log(msg))
                code = tunnel_proc.wait()
                combined_output = ""
                try:
                    if log is not None:
                        combined_output = log.get("1.0", "end")
                except Exception:
                    combined_output = ""

                def closed() -> None:
                    if _is_admin_required_output(combined_output):
                        tunnel_var.set("Tunnel: Admin required")
                        footer_var.set("Start Tunnel needs Administrator privileges. Run the app as Administrator.")
                    elif code == 0:
                        tunnel_var.set("Tunnel: Stopped")
                        footer_var.set("Tunnel stopped.")
                    else:
                        tunnel_var.set(f"Tunnel: Exited ({code})")
                        footer_var.set("Tunnel exited unexpectedly.")
                    refresh_status()

                root.after(0, closed)

            threading.Thread(target=consume, daemon=True).start()
        except Exception as exc:
            append_log(str(exc))
            tunnel_var.set("Tunnel: Failed to start")
            footer_var.set("Could not start remote tunnel.")

    def stop_tunnel() -> None:
        nonlocal tunnel_proc
        if not tunnel_proc or tunnel_proc.poll() is not None:
            footer_var.set("Tunnel is not running.")
            tunnel_var.set("Tunnel: Not started")
            return
        tunnel_proc.terminate()
        tunnel_var.set("Tunnel: Stopping...")
        footer_var.set("Stopping remote tunnel...")

    def copy_commands() -> None:
        commands = _build_setup_commands()
        root.clipboard_clear()
        root.clipboard_append(commands)
        footer_var.set("Setup commands copied to clipboard.")

    def show_help() -> None:
        messagebox.showinfo(
            "Mirror Setup",
            "This viewer window is ready, but the live iPhone video stream backend\n"
            "still needs to be connected. For modern iPhones on Windows, the best\n"
            "next step is using pymobiledevice3 developer services after mounting\n"
            "the Developer Disk Image.",
        )

    header = tk.Frame(root, bg="#111111")
    header.pack(fill="x", padx=18, pady=(16, 8))

    tk.Label(
        header,
        text="Screen Mirror",
        fg="#74f0ff",
        bg="#111111",
        font=("Consolas", 22, "bold"),
    ).pack(anchor="w")
    tk.Label(
        header,
        textvariable=title_var,
        fg="#d9d9d9",
        bg="#111111",
        font=("Consolas", 12),
    ).pack(anchor="w", pady=(6, 0))

    body = tk.Frame(root, bg="#111111")
    body.pack(fill="both", expand=True, padx=18, pady=(6, 12))
    body.grid_columnconfigure(0, weight=3)
    body.grid_columnconfigure(1, weight=2)
    body.grid_rowconfigure(0, weight=1)

    viewer = tk.Frame(body, bg="#151515", highlightbackground="#2fd067", highlightthickness=2)
    viewer.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

    tk.Label(
        viewer,
        text="Live iPhone Screen",
        fg="#ffffff",
        bg="#151515",
        font=("Consolas", 18, "bold"),
    ).pack(anchor="n", pady=(26, 8))
    tk.Label(
        viewer,
        text="This window is where the live mirrored display will appear.",
        fg="#cfcfcf",
        bg="#151515",
        font=("Consolas", 12),
    ).pack()

    phone_frame = tk.Frame(viewer, bg="#151515")
    phone_frame.pack(expand=True)
    tk.Canvas(
        phone_frame,
        width=330,
        height=590,
        bg="#0b0b0b",
        highlightbackground="#4b4b4b",
        highlightthickness=2,
    ).pack(pady=20)
    tk.Label(
        viewer,
        textvariable=footer_var,
        wraplength=520,
        justify="center",
        fg="#9ae6b4",
        bg="#151515",
        font=("Consolas", 11),
    ).pack(pady=(0, 24))

    side = tk.Frame(body, bg="#161616", highlightbackground="#2d9cff", highlightthickness=2)
    side.grid(row=0, column=1, sticky="nsew")
    side.grid_columnconfigure(0, weight=1)
    side.grid_rowconfigure(3, weight=1)

    status_block = tk.Frame(side, bg="#161616")
    status_block.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 10))

    tk.Label(
        status_block,
        text="Status",
        fg="#74f0ff",
        bg="#161616",
        font=("Consolas", 18, "bold"),
    ).pack(anchor="w", pady=(0, 8))

    tk.Label(
        status_block,
        text=f"Connected Device: {info.name}",
        fg="#f2f2f2",
        bg="#161616",
        wraplength=360,
        justify="left",
        font=("Consolas", 12),
    ).pack(anchor="w", pady=4)
    tk.Label(
        status_block,
        text=f"UDID: {info.udid}",
        fg="#bbbbbb",
        bg="#161616",
        wraplength=360,
        justify="left",
        font=("Consolas", 11),
    ).pack(anchor="w", pady=4)
    tk.Label(
        status_block,
        textvariable=dev_mode_var,
        fg="#f2f2f2",
        bg="#161616",
        wraplength=360,
        justify="left",
        font=("Consolas", 11),
    ).pack(anchor="w", pady=8)
    tk.Label(
        status_block,
        textvariable=screenshot_var,
        fg="#f2f2f2",
        bg="#161616",
        wraplength=360,
        justify="left",
        font=("Consolas", 11),
    ).pack(anchor="w", pady=8)
    tk.Label(
        status_block,
        textvariable=tunnel_var,
        fg="#f2f2f2",
        bg="#161616",
        wraplength=360,
        justify="left",
        font=("Consolas", 11),
    ).pack(anchor="w", pady=8)

    controls_block = tk.Frame(side, bg="#161616")
    controls_block.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

    tk.Label(
        controls_block,
        text="Controls",
        fg="#74f0ff",
        bg="#161616",
        font=("Consolas", 16, "bold"),
    ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

    tk.Button(controls_block, text="Auto Prepare", command=auto_prepare, width=14).grid(row=1, column=0, padx=(0, 6), pady=2)
    tk.Button(controls_block, text="Mount Now", command=mount_now, width=12).grid(row=1, column=1, padx=6, pady=2)
    tk.Button(controls_block, text="Start Tunnel", command=start_tunnel, width=12).grid(row=1, column=2, padx=6, pady=2)
    tk.Button(controls_block, text="Stop Tunnel", command=stop_tunnel, width=12).grid(row=1, column=3, padx=(6, 0), pady=2)
    tk.Button(controls_block, text="Refresh Status", command=refresh_status, width=14).grid(row=2, column=0, padx=(0, 6), pady=2)
    tk.Button(controls_block, text="Copy Commands", command=copy_commands, width=14).grid(row=2, column=1, padx=6, pady=2)
    tk.Button(controls_block, text="Help", command=show_help, width=10).grid(row=2, column=2, padx=6, pady=2)

    lower = tk.Frame(side, bg="#161616")
    lower.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 16))
    lower.grid_columnconfigure(0, weight=1)
    lower.grid_rowconfigure(3, weight=1)
    lower.grid_rowconfigure(5, weight=1)

    tk.Label(
        lower,
        text="Setup Commands",
        fg="#74f0ff",
        bg="#161616",
        font=("Consolas", 16, "bold"),
    ).grid(row=0, column=0, sticky="w", pady=(0, 6))

    commands = tk.Text(
        lower,
        height=7,
        bg="#0f0f0f",
        fg="#dddddd",
        insertbackground="#dddddd",
        relief="flat",
        wrap="word",
        font=("Consolas", 10),
    )
    commands.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
    commands.insert("1.0", _build_setup_commands())
    commands.configure(state="disabled")

    tk.Label(
        lower,
        text="Activity Log",
        fg="#74f0ff",
        bg="#161616",
        font=("Consolas", 16, "bold"),
    ).grid(row=4, column=0, sticky="w", pady=(0, 6))

    log = tk.Text(
        lower,
        height=6,
        bg="#0f0f0f",
        fg="#dddddd",
        insertbackground="#dddddd",
        relief="flat",
        wrap="word",
        font=("Consolas", 10),
    )
    log.grid(row=5, column=0, sticky="nsew")
    log.insert("1.0", "Mirror window ready.\nUse Auto Prepare to mount the image and start the tunnel.\n")
    log.configure(state="disabled")

    refresh_status()
    root.mainloop()

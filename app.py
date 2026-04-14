import base64
import json
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import cv2
import tkinter as tk
from tkinter import messagebox, ttk

## 123
@dataclass
class TransferSession:
    file_name: str
    total_chunks: int
    chunks: Dict[int, str] = field(default_factory=dict)
    last_update: float = field(default_factory=time.time)

    def add_chunk(self, seq: int, data: str) -> None:
        self.chunks[seq] = data
        self.last_update = time.time()

    @property
    def completed(self) -> bool:
        return len(self.chunks) == self.total_chunks

    def rebuild(self) -> bytes:
        ordered = "".join(self.chunks[i] for i in range(self.total_chunks))
        return base64.b64decode(ordered)


class QRFileScannerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("动态二维码接收器")
        self.root.geometry("900x620")
        self.root.configure(bg="#1f2937")
        self.root.resizable(True, True)

        self.capture_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.message_queue: "queue.Queue[dict]" = queue.Queue()

        self.detector = cv2.QRCodeDetector()
        self.sessions: Dict[str, TransferSession] = {}

        self.output_dir = Path.cwd() / "received_files"
        self.output_dir.mkdir(exist_ok=True)

        self._build_ui()
        self.root.after(120, self._poll_messages)

    def _build_ui(self) -> None:
        title_bar = tk.Frame(self.root, bg="#111827", height=40)
        title_bar.pack(fill="x")

        title = tk.Label(
            title_bar,
            text="二维码离线文件接收器（Windows）",
            bg="#111827",
            fg="#f9fafb",
            font=("Segoe UI", 11, "bold"),
        )
        title.pack(side="left", padx=12)

        # 自定义标题栏拖拽，满足“拖拽扫描窗口”需求
        title_bar.bind("<ButtonPress-1>", self._on_drag_start)
        title_bar.bind("<B1-Motion>", self._on_drag_motion)
        title.bind("<ButtonPress-1>", self._on_drag_start)
        title.bind("<B1-Motion>", self._on_drag_motion)

        body = tk.Frame(self.root, bg="#1f2937")
        body.pack(fill="both", expand=True, padx=14, pady=14)

        controls = tk.Frame(body, bg="#1f2937")
        controls.pack(fill="x", pady=(0, 12))

        tk.Label(controls, text="摄像头索引", bg="#1f2937", fg="#e5e7eb").pack(side="left")
        self.camera_var = tk.StringVar(value="0")
        cam_entry = tk.Entry(controls, textvariable=self.camera_var, width=6)
        cam_entry.pack(side="left", padx=8)

        self.start_btn = tk.Button(controls, text="开始扫描", command=self.start_scan)
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = tk.Button(controls, text="停止", state="disabled", command=self.stop_scan)
        self.stop_btn.pack(side="left")

        self.status_var = tk.StringVar(value="就绪：请将云桌面的动态二维码对准摄像头，再点击开始。")
        tk.Label(body, textvariable=self.status_var, bg="#1f2937", fg="#93c5fd", anchor="w").pack(fill="x")

        self.progress = ttk.Progressbar(body, mode="determinate")
        self.progress.pack(fill="x", pady=12)

        columns = ("file", "chunks", "path")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", height=14)
        self.tree.heading("file", text="文件名")
        self.tree.heading("chunks", text="分片")
        self.tree.heading("path", text="保存路径")
        self.tree.column("file", width=240)
        self.tree.column("chunks", width=90, anchor="center")
        self.tree.column("path", width=500)
        self.tree.pack(fill="both", expand=True)

        actions = tk.Frame(body, bg="#1f2937")
        actions.pack(fill="x", pady=(10, 0))

        tk.Button(actions, text="复制选中文件路径", command=self.copy_selected_path).pack(side="left")
        tk.Button(actions, text="复制选中文件内容（文本）", command=self.copy_selected_content).pack(
            side="left", padx=8
        )

    def _on_drag_start(self, event: tk.Event) -> None:
        self.root._drag_start_x = event.x
        self.root._drag_start_y = event.y

    def _on_drag_motion(self, event: tk.Event) -> None:
        dx = event.x - self.root._drag_start_x
        dy = event.y - self.root._drag_start_y
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    def start_scan(self) -> None:
        if self.capture_thread and self.capture_thread.is_alive():
            return

        try:
            camera_index = int(self.camera_var.get())
        except ValueError:
            messagebox.showerror("参数错误", "摄像头索引必须是数字")
            return

        self.stop_event.clear()
        self.capture_thread = threading.Thread(
            target=self._capture_loop, args=(camera_index,), daemon=True
        )
        self.capture_thread.start()

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_var.set("扫描中：可将程序置于后台，扫描线程不会停止。")

    def stop_scan(self) -> None:
        self.stop_event.set()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_var.set("已停止。")

    def _capture_loop(self, camera_index: int) -> None:
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.message_queue.put({"type": "error", "message": f"无法打开摄像头索引 {camera_index}"})
            return

        try:
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    continue
                payload, points, _ = self.detector.detectAndDecode(frame)
                if not payload:
                    continue
                self.message_queue.put({"type": "payload", "data": payload})
                if points is not None:
                    time.sleep(0.07)
        finally:
            cap.release()

    def _poll_messages(self) -> None:
        while True:
            try:
                msg = self.message_queue.get_nowait()
            except queue.Empty:
                break

            if msg["type"] == "error":
                self.status_var.set(msg["message"])
                self.stop_scan()
            elif msg["type"] == "payload":
                self._handle_payload(msg["data"])

        self.root.after(120, self._poll_messages)

    def _handle_payload(self, payload: str) -> None:
        parsed = self._parse_chunk_payload(payload)
        if not parsed:
            self.status_var.set("收到非文件分片二维码，已忽略。")
            return

        file_id = parsed["file_id"]
        file_name = parsed["file_name"]
        seq = parsed["seq"]
        total = parsed["total"]
        data = parsed["data"]

        session = self.sessions.setdefault(file_id, TransferSession(file_name=file_name, total_chunks=total))
        session.add_chunk(seq, data)

        current = len(session.chunks)
        self.progress.configure(maximum=total, value=current)
        self.status_var.set(f"接收中：{file_name} {current}/{total}")

        if session.completed:
            out_path = self.output_dir / session.file_name
            out_path.write_bytes(session.rebuild())
            self.status_var.set(f"完成：{session.file_name}")
            self._upsert_file_row(session.file_name, f"{total}/{total}", str(out_path))
            del self.sessions[file_id]

    def _upsert_file_row(self, file_name: str, chunks: str, path: str) -> None:
        for item in self.tree.get_children():
            vals = self.tree.item(item, "values")
            if vals and vals[0] == file_name:
                self.tree.item(item, values=(file_name, chunks, path))
                return
        self.tree.insert("", "end", values=(file_name, chunks, path))

    @staticmethod
    def _parse_chunk_payload(payload: str) -> Optional[dict]:
        """
        支持两种常见格式：
        1) JSON: {"fileId":"a","fileName":"a.txt","seq":0,"total":9,"data":"...base64..."}
        2) 纯文本: FILE::<fileId>::<fileName>::<seq>/<total>::<base64>
        """
        try:
            obj = json.loads(payload)
            return {
                "file_id": str(obj["fileId"]),
                "file_name": str(obj["fileName"]),
                "seq": int(obj["seq"]),
                "total": int(obj["total"]),
                "data": str(obj["data"]),
            }
        except Exception:
            pass

        if payload.startswith("FILE::"):
            parts = payload.split("::", 4)
            if len(parts) == 5:
                _, file_id, file_name, seq_meta, data = parts
                seq, total = seq_meta.split("/")
                return {
                    "file_id": file_id,
                    "file_name": file_name,
                    "seq": int(seq),
                    "total": int(total),
                    "data": data,
                }

        return None

    def copy_selected_path(self) -> None:
        item = self.tree.focus()
        if not item:
            return
        vals = self.tree.item(item, "values")
        if not vals:
            return
        path = vals[2]
        self.root.clipboard_clear()
        self.root.clipboard_append(path)
        self.status_var.set("已复制文件路径")

    def copy_selected_content(self) -> None:
        item = self.tree.focus()
        if not item:
            return
        vals = self.tree.item(item, "values")
        if not vals:
            return
        path = Path(vals[2])
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            messagebox.showwarning("复制失败", f"当前文件不是UTF-8文本或读取失败: {exc}")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("已复制文件内容")


if __name__ == "__main__":
    root = tk.Tk()
    app = QRFileScannerApp(root)
    root.mainloop()

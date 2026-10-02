from __future__ import annotations

import csv
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
import tifffile


DEFAULT_CHANNELS = {
    0: "BF",
    1: "Nuclei",
    2: "Red",
    5: "GCGbead",
    6: "INSbead"
}


@dataclass
class ExtractionResult:
    source: Path
    outputs: list[Path]
    error: str = ""


def read_planes(path: Path) -> np.ndarray:
    """Return a TIFF as (plane, y, x), preserving source pixel values and dtype."""
    with tifffile.TiffFile(path) as tif:
        series = tif.series[0]
        data = series.asarray()
        axes = series.axes.upper()

    if "Y" not in axes or "X" not in axes:
        raise ValueError(f"Y/X 축을 찾을 수 없습니다: axes={axes}")

    data = np.moveaxis(data, (axes.index("Y"), axes.index("X")), (-2, -1))
    plane_count = int(np.prod(data.shape[:-2])) if data.ndim > 2 else 1
    return np.asarray(data).reshape((plane_count,) + data.shape[-2:])


def safe_suffix(text: str) -> str:
    cleaned = "".join(character for character in text.strip() if character not in '<>:"/\\|?*')
    if not cleaned:
        raise ValueError("suffix는 비워둘 수 없습니다.")
    return cleaned


def extract_tiff(
    source: Path,
    output_folder: Path,
    channel_suffixes: dict[int, str],
    overwrite: bool = False,
) -> ExtractionResult:
    planes = read_planes(source)
    required = max(channel_suffixes)
    if planes.shape[0] <= required:
        raise ValueError(f"plane이 {planes.shape[0]}개뿐입니다. index {required}까지 필요합니다.")

    output_folder.mkdir(parents=True, exist_ok=True)
    destinations = [output_folder / f"{source.stem}_{safe_suffix(suffix)}.tif" for suffix in channel_suffixes.values()]
    existing = [path.name for path in destinations if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"출력 파일이 이미 존재합니다: {', '.join(existing)}")

    written: list[Path] = []
    try:
        for (index, _suffix), destination in zip(channel_suffixes.items(), destinations):
            tifffile.imwrite(
                destination,
                planes[index],
                photometric="minisblack",
                metadata={"axes": "YX", "source_file": source.name, "source_plane_index": index},
            )
            written.append(destination)
    except Exception:
        # Only remove files created during this failed extraction.
        for path in written:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    return ExtractionResult(source, written)


class TiffExtractorUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("8-plane TIFF Channel Extractor")
        self.root.geometry("980x680")
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.recursive = tk.BooleanVar(value=False)
        self.overwrite = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="입력 폴더와 출력 폴더를 선택하세요.")
        self.suffix_vars = {index: tk.StringVar(value=suffix) for index, suffix in DEFAULT_CHANNELS.items()}
        self.events: queue.Queue = queue.Queue()
        self.running = False
        self._build()

    def _build(self):
        style = ttk.Style()
        style.configure("Header.TLabel", font=("Segoe UI", 19, "bold"))
        body = ttk.Frame(self.root, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="8-plane TIFF Channel Extractor", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text="각 TIFF에서 배열 index 0, 1, 2, 5, 6을 단일-plane TIFF로 추출합니다. 원본은 변경하지 않습니다.",
        ).pack(anchor="w", pady=(3, 14))

        folders = ttk.LabelFrame(body, text="폴더", padding=10)
        folders.pack(fill="x")
        self._folder_row(folders, 0, "입력 폴더", self.input_path, self.choose_input)
        self._folder_row(folders, 1, "출력 폴더", self.output_path, self.choose_output)
        folders.columnconfigure(1, weight=1)

        channels = ttk.LabelFrame(body, text="추출 채널과 filename suffix", padding=10)
        channels.pack(fill="x", pady=10)
        for column, index in enumerate(DEFAULT_CHANNELS):
            cell = ttk.Frame(channels)
            cell.grid(row=0, column=column, padx=8, sticky="ew")
            ttk.Label(cell, text=f"index {index}", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Entry(cell, textvariable=self.suffix_vars[index], width=13).pack(fill="x", pady=(3, 0))
            channels.columnconfigure(column, weight=1)

        options = ttk.Frame(body)
        options.pack(fill="x")
        ttk.Checkbutton(options, text="하위 폴더 포함", variable=self.recursive).pack(side="left")
        ttk.Checkbutton(options, text="기존 출력 파일 덮어쓰기", variable=self.overwrite).pack(side="left", padx=20)

        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=12)
        self.run_button = ttk.Button(controls, text="추출 시작", command=self.start)
        self.run_button.pack(side="left")
        self.progress = ttk.Progressbar(controls, length=320)
        self.progress.pack(side="left", padx=12)
        ttk.Label(controls, textvariable=self.status).pack(side="left")

        result_box = ttk.LabelFrame(body, text="처리 결과", padding=6)
        result_box.pack(fill="both", expand=True)
        columns = ("source", "planes", "status")
        self.table = ttk.Treeview(result_box, columns=columns, show="headings")
        self.table.heading("source", text="원본 TIFF")
        self.table.heading("planes", text="생성 파일")
        self.table.heading("status", text="상태")
        self.table.column("source", width=390)
        self.table.column("planes", width=100, anchor="center")
        self.table.column("status", width=320)
        scrollbar = ttk.Scrollbar(result_box, command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    @staticmethod
    def _folder_row(parent, row, label, variable, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8)
        ttk.Button(parent, text="찾아보기", command=command).grid(row=row, column=2)

    def choose_input(self):
        selected = filedialog.askdirectory(title="8-plane TIFF 입력 폴더")
        if selected:
            self.input_path.set(selected)
            if not self.output_path.get():
                self.output_path.set(str(Path(selected).parent / f"{Path(selected).name}_extracted"))

    def choose_output(self):
        selected = filedialog.askdirectory(title="추출 TIFF 출력 폴더")
        if selected:
            self.output_path.set(selected)

    def start(self):
        input_text = self.input_path.get().strip()
        output_text = self.output_path.get().strip()
        if not input_text or not Path(input_text).is_dir() or not output_text:
            messagebox.showerror("설정 오류", "유효한 입력 폴더와 출력 폴더를 지정하세요.")
            return
        try:
            suffixes = {index: safe_suffix(variable.get()) for index, variable in self.suffix_vars.items()}
            if len(set(suffixes.values())) != len(suffixes):
                raise ValueError("각 채널의 suffix는 서로 달라야 합니다.")
        except ValueError as error:
            messagebox.showerror("suffix 오류", str(error))
            return

        source_folder = Path(input_text)
        output_folder = Path(output_text)
        iterator = source_folder.rglob("*") if self.recursive.get() else source_folder.iterdir()
        files = sorted(path for path in iterator if path.is_file() and path.suffix.lower() in {".tif", ".tiff"})
        if not files:
            messagebox.showinfo("TIFF 없음", "입력 폴더에서 TIFF 파일을 찾지 못했습니다.")
            return

        self.table.delete(*self.table.get_children())
        self.progress.configure(maximum=len(files), value=0)
        self.run_button.configure(state="disabled")
        self.running = True
        settings = (files, output_folder, suffixes, self.overwrite.get())
        threading.Thread(target=self._worker, args=settings, daemon=True).start()
        self.root.after(75, self._poll)

    def _worker(self, files, output_folder, suffixes, overwrite):
        output_folder.mkdir(parents=True, exist_ok=True)
        report_rows = []
        success_count = 0
        for position, source in enumerate(files, 1):
            try:
                result = extract_tiff(source, output_folder, suffixes, overwrite)
                success_count += 1
                report_rows.append((str(source), "success", len(result.outputs), ""))
                self.events.put(("row", position, len(files), source, len(result.outputs), "완료"))
            except Exception as error:
                report_rows.append((str(source), "error", 0, str(error)))
                self.events.put(("row", position, len(files), source, 0, str(error)))

        with (output_folder / "extraction_report.csv").open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(("source_file", "status", "output_count", "error"))
            writer.writerows(report_rows)
        self.events.put(("done", success_count, len(files), output_folder))

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "row":
                    _, position, total, source, count, status = event
                    self.progress["value"] = position
                    self.status.set(f"처리 중 {position}/{total}")
                    self.table.insert("", "end", values=(source.name, count, status))
                    self.table.yview_moveto(1)
                elif event[0] == "done":
                    _, success, total, output = event
                    self.running = False
                    self.run_button.configure(state="normal")
                    self.status.set(f"완료: {total}개 중 {success}개 성공")
                    messagebox.showinfo(
                        "추출 완료",
                        f"원본 TIFF {total}개 중 {success}개를 처리했습니다.\n"
                        f"생성 예정/최대 파일: {success * len(DEFAULT_CHANNELS)}개\n\n{output}",
                    )
        except queue.Empty:
            pass
        if self.running:
            self.root.after(75, self._poll)


if __name__ == "__main__":
    root = tk.Tk()
    TiffExtractorUI(root)
    root.mainloop()

import os
import threading
import itertools
import subprocess
import yt_dlp
import ffmpeg
import tkinter as tk
from tkinter import ttk, messagebox

# ====== Fungsi Inti ======
def list_formats(url):
    ydl_opts = {'quiet': True, 'no_warnings': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get('formats', []), info.get('title', 'video')

def label_resolution(width, height):
    """Beri label tambahan: portrait vs landscape"""
    if width and height:
        if height > width:  # portrait
            return f"{height}p ({width}p portrait)"
        else:
            return f"{height}p (landscape)"
    return f"{height}p"

def detect_available_resolutions(formats):
    """Deteksi resolusi real dari format list (video+audio combo), dengan label orientasi"""
    resolutions = {}
    video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none']
    audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
    muxed_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') != 'none']

    # Ambil audio terbaik (biasanya 140 / 251)
    audio_best = None
    if audio_formats:
        audio_best = max(audio_formats, key=lambda x: x.get('abr', 0))

    # Gabungkan video only + audio_best
    for vf in video_formats:
        height = vf.get('height')
        width = vf.get('width')
        if not height or not width:
            continue

        combo_id = f"{vf['format_id']}+{audio_best['format_id']}" if audio_best else vf['format_id']
        label = label_resolution(width, height)
        prev = resolutions.get(label)
        if not prev or vf.get('tbr', 0) > prev.get('tbr', 0):
            resolutions[label] = {
                "format_id": combo_id,
                "tbr": vf.get('tbr', 0),
                "height": height
            }

    # Tambahkan format muxed (video+audio satu ID)
    for mf in muxed_formats:
        height = mf.get('height')
        width = mf.get('width')
        if not height or not width:
            continue

        label = label_resolution(width, height)
        prev = resolutions.get(label)
        if not prev or mf.get('tbr', 0) > prev.get('tbr', 0):
            resolutions[label] = {
                "format_id": mf['format_id'],
                "tbr": mf.get('tbr', 0),
                "height": height
            }

    # Urutkan resolusi tinggi → rendah berdasarkan height
    sorted_labels = sorted(resolutions.keys(), key=lambda k: resolutions[k]['height'], reverse=True)
    return sorted_labels, resolutions

def get_best_format(selected_res, detected_formats):
    """Ambil format_id terbaik berdasarkan resolusi terpilih"""
    if selected_res in detected_formats:
        return detected_formats[selected_res]['format_id']
    raise Exception(f"Tidak ditemukan format untuk {selected_res}")

# ====== Animasi Loading ======
spinner_running = False
def start_spinner(text="⏳ Loading..."):
    global spinner_running
    spinner_running = True
    def spin():
        for c in itertools.cycle(['⏳','🔄','🌀','💫']):
            if not spinner_running:
                break
            status_label.config(text=f"{c} {text}")
            root.update_idletasks()
            root.after(150)
    threading.Thread(target=spin, daemon=True).start()

def stop_spinner():
    global spinner_running
    spinner_running = False

# ====== Pisahkan Vokal ======
def separate_vocals(file_path):
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    wav_file = os.path.join("downloads", base_name + ".wav")

    ffmpeg.input(file_path).output(wav_file, acodec='pcm_s16le', ac=2, ar='44100').run(overwrite_output=True)

    output_dir = os.path.join("downloads", "vocals")
    os.makedirs(output_dir, exist_ok=True)

    subprocess.run([
        "spleeter", "separate",
        "-p", "spleeter:2stems",
        "-o", output_dir,
        wav_file
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    vocal_file = os.path.join(output_dir, base_name, "vocals.wav")
    if os.path.exists(vocal_file):
        messagebox.showinfo("🎤 Berhasil", f"File vokal disimpan di:\n{vocal_file}")
    else:
        messagebox.showerror("❌ Gagal", "Gagal memisahkan vokal.")

# ====== Tombol Deteksi Resolusi ======
detected_format_map = {}

def detect_resolutions_action():
    url = url_entry.get().strip()
    if not url:
        messagebox.showwarning("⚠️ URL kosong", "Masukkan URL YouTube terlebih dahulu.")
        return

    start_spinner("Mendeteksi resolusi...")
    def run():
        global detected_format_map
        try:
            formats, _ = list_formats(url)
            resolutions, format_map = detect_available_resolutions(formats)
            stop_spinner()
            if not resolutions:
                messagebox.showerror("❌ Error", "Tidak ada resolusi yang tersedia.")
                return

            detected_format_map = format_map
            resolution_dropdown['values'] = resolutions
            resolution_var.set(resolutions[0])
            status_label.config(text=f"✅ Resolusi ditemukan: {', '.join(resolutions)}")
        except Exception as e:
            stop_spinner()
            messagebox.showerror("❌ Error", f"Gagal mendeteksi resolusi:\n{str(e)}")

    threading.Thread(target=run, daemon=True).start()

# ====== Proses Download ======
def start_download():
    url = url_entry.get().strip()
    resolution = resolution_var.get()
    separate = separate_var.get()

    if not url:
        messagebox.showwarning("⚠️ URL kosong", "Masukkan URL YouTube terlebih dahulu.")
        return
    if not resolution:
        messagebox.showwarning("⚠️ Pilih Resolusi", "Deteksi dan pilih resolusi terlebih dahulu.")
        return

    download_button.config(state="disabled")
    progress_bar['value'] = 0
    start_spinner("Menyiapkan download...")

    def run():
        try:
            os.makedirs('downloads', exist_ok=True)
            format_id = get_best_format(resolution, detected_format_map)
            stop_spinner()
            status_label.config(text=f"🚀 Download {resolution} ...")

            output_template = './downloads/%(title)s.%(ext)s'
            ydl_opts = {
                'format': format_id,
                'merge_output_format': 'mp4',
                'outtmpl': output_template,
                'concurrent_fragment_downloads': 10,
                'http_chunk_size': 10 * 1024 * 1024,
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [progress_hook]
            }

            filepath = None
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = ydl.prepare_filename(info)

            status_label.config(text=f"✅ Download selesai")

            if separate and filepath:
                start_spinner("Memproses vokal...")
                separate_vocals(filepath)
                stop_spinner()

            messagebox.showinfo("✅ Selesai", f"Video berhasil diunduh:\n{os.path.basename(filepath)}")

        except Exception as e:
            stop_spinner()
            messagebox.showerror("❌ Error", f"Terjadi kesalahan:\n{str(e)}")
        finally:
            download_button.config(state="normal")

    threading.Thread(target=run, daemon=True).start()

# ====== Progress Hook ======
def progress_hook(d):
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        downloaded = d.get('downloaded_bytes', 0)
        if total > 0:
            percent = int(downloaded * 100 / total)
            progress_bar['value'] = percent
            root.update_idletasks()
            status_label.config(text=f"📥 Mengunduh... {percent}%")
    elif d['status'] == 'finished':
        progress_bar['value'] = 100
        status_label.config(text="📦 Menggabungkan video & audio...")

# ====== GUI ======
root = tk.Tk()
root.title("📺 YouTube Downloader + Real Auto Resolution + Vocal Split 🎤")
root.geometry("520x460")
root.resizable(False, False)
root.configure(bg="#222")

title_label = tk.Label(root, text="🔥 Real Auto Resolution + Orientation + Vocal Split", font=("Segoe UI", 14, "bold"), fg="white", bg="#222")
title_label.pack(pady=10)

url_frame = tk.Frame(root, bg="#222")
url_frame.pack(pady=5)
tk.Label(url_frame, text="🔗 URL YouTube:", font=("Segoe UI", 11), fg="white", bg="#222").pack(anchor="w")
url_entry = tk.Entry(url_frame, width=55, font=("Segoe UI", 10))
url_entry.pack(ipady=4, pady=3)

detect_button = tk.Button(root, text="🔍 Deteksi Resolusi", command=detect_resolutions_action, font=("Segoe UI", 10, "bold"), bg="#4CAF50", fg="white", activebackground="#45A049", cursor="hand2")
detect_button.pack(pady=8, ipadx=5, ipady=2)

resolution_var = tk.StringVar()
tk.Label(root, text="📌 Pilih Resolusi:", font=("Segoe UI", 11), fg="white", bg="#222").pack(anchor="w", padx=22)
resolution_dropdown = ttk.Combobox(root, textvariable=resolution_var, state="readonly", font=("Segoe UI", 10))
resolution_dropdown.pack(pady=5, ipadx=5)

separate_var = tk.BooleanVar(value=False)
separate_check = tk.Checkbutton(root, text="🎤 Hanya ambil vokal (hapus instrumen)", variable=separate_var, bg="#222", fg="white", selectcolor="#333", font=("Segoe UI", 10))
separate_check.pack(pady=8)

download_button = tk.Button(root, text="⬇️ Mulai Download", command=start_download, font=("Segoe UI", 12, "bold"), bg="#ff4d4d", fg="white", activebackground="#ff1a1a", cursor="hand2")
download_button.pack(pady=10, ipadx=10, ipady=5)

progress_bar = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
progress_bar.pack(pady=10)

status_label = tk.Label(root, text="Menunggu...", font=("Segoe UI", 10), fg="white", bg="#222")
status_label.pack(pady=5)

style = ttk.Style()
style.theme_use("clam")
style.configure("TProgressbar", troughcolor="#444", background="#00cc66", thickness=15, bordercolor="#444", lightcolor="#00cc66", darkcolor="#00cc66")

root.mainloop()

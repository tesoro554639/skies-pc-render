# frames + mix + captions -> finished MP4 (1080x1920, 30 fps, H.264 + AAC)
#   python encode.py FRAMES_DIR TOTAL_FRAMES MIX.wav CAPS_DIR OUT.mp4 [--nvenc] [--crf 17] [--cq 18]
import argparse, os, subprocess, sys, re

def check_missing_frames(frames_dir, total):
    missing = []
    for i in range(total):
        p = os.path.join(frames_dir, "f_%05d.png" % i)
        if not os.path.exists(p):
            missing.append(i)
    return missing

def has_valid_captions(caps_dir):
    if not caps_dir or not os.path.isdir(caps_dir):
        return False
    list_path = os.path.join(caps_dir, "list.txt")
    if not os.path.isfile(list_path):
        return False
    try:
        with open(list_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.strip().startswith('file '):
                    return True
    except Exception:
        return False
    return False

def run_ffmpeg_with_progress(cmd, total_frames):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    last_frame = 0
    fps_val = "0"
    speed_val = "0x"
    output_lines = []

    assert proc.stdout is not None
    for line in proc.stdout:
        line_str = line.strip()
        output_lines.append(line_str)
        if len(output_lines) > 200:
            output_lines.pop(0)

        if line_str.startswith("frame="):
            try:
                last_frame = int(line_str.split("=")[1].strip())
            except ValueError:
                pass
        elif line_str.startswith("fps="):
            fps_val = line_str.split("=")[1].strip()
        elif line_str.startswith("speed="):
            speed_val = line_str.split("=")[1].strip()
        elif line_str.startswith("progress="):
            pct = min(100.0, (last_frame / max(1, total_frames)) * 100.0)
            print(f"ENCODE_PROGRESS frame={last_frame} total={total_frames} pct={pct:.1f}% fps={fps_val} speed={speed_val}", flush=True)

    rc = proc.wait()
    return rc, "\n".join(output_lines)

def build_encode_cmd(frames_dir, total, mix_path, caps_dir, out_path, use_nvenc, crf=17, cq=18):
    T = total / 30.0
    frame_pattern = os.path.join(frames_dir, "f_%05d.png").replace("\\", "/")
    has_caps = has_valid_captions(caps_dir)
    has_audio = os.path.isfile(mix_path)

    cmd = ["ffmpeg", "-y", "-framerate", "30", "-i", frame_pattern]

    if has_caps:
        list_file = os.path.join(caps_dir, "list.txt").replace("\\", "/")
        cmd.extend(["-f", "concat", "-safe", "0", "-i", list_file])
    else:
        print("Note: No captions found or list.txt is empty; encoding without captions overlay.", flush=True)

    if has_audio:
        cmd.extend(["-i", mix_path.replace("\\", "/")])
    else:
        print(f"Note: Audio file {mix_path} not found; generating silent audio track.", flush=True)
        cmd.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])

    y_pos = round(1920 * (0.686 - 0.16 / 2))

    if has_caps:
        # Scale video, overlay captions, trim audio
        filter_str = (
            f"[0:v]scale=1080:1920:flags=lanczos,format=rgba[b];"
            f"[1:v]format=rgba[c];"
            f"[b][c]overlay=0:{y_pos}:shortest=0,format=yuv420p[v];"
            f"[2:a]apad,atrim=0:{T:.4f}[a]"
        )
    else:
        filter_str = (
            f"[0:v]scale=1080:1920:flags=lanczos,format=yuv420p[v];"
            f"[1:a]apad,atrim=0:{T:.4f}[a]"
        )

    vcodec = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(cq)] if use_nvenc else ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf)]

    cmd.extend([
        "-filter_complex", filter_str,
        "-map", "[v]", "-map", "[a]",
        "-frames:v", str(total),
        *vcodec,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "256k",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        out_path
    ])
    return cmd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir", help="Directory containing f_NNNNN.png frames")
    ap.add_argument("total_frames", type=int, help="Total frame count")
    ap.add_argument("mix_path", help="Path to audio mix.wav")
    ap.add_argument("caps_dir", help="Path to caps directory containing list.txt")
    ap.add_argument("output_path", help="Output MP4 file path")
    ap.add_argument("--nvenc", action="store_true", help="Use NVIDIA GPU hardware encoder (h264_nvenc)")
    ap.add_argument("--crf", type=int, default=17, help="libx264 CRF quality (default: 17)")
    ap.add_argument("--cq", type=int, default=18, help="NVENC CQ quality (default: 18)")
    args = ap.parse_args()

    missing = check_missing_frames(args.frames_dir, args.total_frames)
    if missing:
        sys.exit("missing frames: %d (first %s) - finish the render first" % (len(missing), missing[:10]))

    out_dir = os.path.dirname(os.path.abspath(args.output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    use_nvenc = args.nvenc
    cmd = build_encode_cmd(args.frames_dir, args.total_frames, args.mix_path, args.caps_dir,
                           args.output_path, use_nvenc=use_nvenc, crf=args.crf, cq=args.cq)

    encoder_name = "NVENC (h264_nvenc)" if use_nvenc else "CPU (libx264)"
    print(f"Starting encode with {encoder_name} -> {args.output_path}...", flush=True)

    rc, log_output = run_ffmpeg_with_progress(cmd, args.total_frames)

    # If NVENC failed, automatically fall back to libx264
    if rc != 0 and use_nvenc:
        print("\nWARNING: NVENC encode failed (driver mismatch or unsupported). Falling back to CPU libx264...", flush=True)
        fallback_cmd = build_encode_cmd(args.frames_dir, args.total_frames, args.mix_path, args.caps_dir,
                                        args.output_path, use_nvenc=False, crf=args.crf, cq=args.cq)
        rc, log_output = run_ffmpeg_with_progress(fallback_cmd, args.total_frames)

    if rc != 0:
        print(f"\nFFMPEG ERROR (exit code {rc}):\n{log_output[-1200:]}", flush=True)
        sys.exit(rc)

    # Verify output with ffprobe
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=nb_frames",
             "-of", "csv=p=0", args.output_path],
            capture_output=True, text=True, timeout=5
        ).stdout.split()
    except Exception:
        p = []

    print("ENCODED", args.output_path, p, flush=True)

if __name__ == "__main__":
    main()

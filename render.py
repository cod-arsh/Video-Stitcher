#render pipeline for stitching together multiple clips with transitions and captions burned in, then uploading to Google Drive and notifying a callback URL

import os
import subprocess
import tempfile
import shutil
from drive_utils import (
    get_drive_service, find_subfolder_id, find_file_id,
    download_file, upload_file
)
import requests

def get_media_duration(path):
    result = subprocess.run(
        ["ffprobe", "-i", path, "-show_entries", "format=duration",
         "-v", "quiet", "-of", "csv=p=0"],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())

def run_ffmpeg(cmd, label=""):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"--- FFmpeg failed on {label} ---")
        print(result.stderr)
        raise RuntimeError(f"FFmpeg failed on {label}")
    return result


def run_pipeline(drive_folder_id, num_scenes,callback_url,record_id, image_ext="png",
                  fps=25, silence_pad=0.6, transition_duration=0.5,
                  transition_type="fade"):
    service = get_drive_service()
    workdir = tempfile.mkdtemp()

    images_dir = os.path.join(workdir, "images")
    voices_dir = os.path.join(workdir, "voices")
    srt_dir = os.path.join(workdir, "srt")
    clips_dir = os.path.join(workdir, "clips")
    for d in [images_dir, voices_dir, srt_dir, clips_dir]:
        os.makedirs(d, exist_ok=True)

    images_folder_id = find_subfolder_id(service, drive_folder_id, "images")
    voices_folder_id = find_subfolder_id(service, drive_folder_id, "voices")
    # NOTE: srt files are NOT in a subfolder — they live directly in drive_folder_id



    clip_paths = []
    clip_durations = []

    subtitle_style = (
        "FontName=Liberation Sans Bold,FontSize=14,PrimaryColour=&H00FFFFFF,"
        "BackColour=&H80000000,BorderStyle=4,Outline=0,Shadow=0,"
        "Alignment=2,MarginV=60"
    )

    # ---- Step 1: download assets + render each scene clip (captions burned in per-clip) ----
    for i in range(1, num_scenes + 1):
        img_local = os.path.join(images_dir, f"{i}.{image_ext}")
        voice_local = os.path.join(voices_dir, f"{i}.mp3")
        srt_local = os.path.join(srt_dir, f"{i}.srt")
        padded_voice = os.path.join(clips_dir, f"voice{i}_padded.mp3")
        out_clip = os.path.join(clips_dir, f"clip{i}.mp4")

        img_id = find_file_id(service, images_folder_id, f"{i}.{image_ext}")
        voice_id = find_file_id(service, voices_folder_id, f"{i}.mp3")
        srt_id = find_file_id(service, drive_folder_id, f"{i}.srt")  # root folder, not subfolder

        if not img_id or not voice_id or not srt_id:
            raise FileNotFoundError(f"Missing image, voice, or srt for scene {i}")

        download_file(service, img_id, img_local)
        download_file(service, voice_id, voice_local)
        download_file(service, srt_id, srt_local)

        original_duration = get_media_duration(voice_local)

        # Pad silence at the end of each voice clip
        run_ffmpeg([
            "ffmpeg", "-y", "-i", voice_local,
            "-af", f"apad=pad_dur={silence_pad}",
            padded_voice
        ], label=f"pad voice {i}")

        duration = original_duration + silence_pad

        # subtitles filter must come AFTER scale/pad in the chain, and path needs escaping for ffmpeg filter syntax
        srt_path_escaped = srt_local.replace("\\", "/").replace(":", "\\:")

        vf = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            f"subtitles='{srt_path_escaped}':force_style='{subtitle_style}'"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(duration), "-i", img_local,
            "-i", padded_voice,
            "-vf", vf,
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-t", str(duration),
            out_clip
        ]
        print(f"Rendering clip {i}/{num_scenes} (with captions)...")
        run_ffmpeg(cmd, label=f"clip{i}")

        clip_paths.append(out_clip)
        clip_durations.append(get_media_duration(out_clip))

    # ---- Step 2: xfade stitch (captions already burned in, so no third pass needed) ----
    inputs = []
    for c in clip_paths:
        inputs += ["-i", c]

    filter_parts = []
    prev_v, prev_a = "0:v", "0:a"
    cumulative = clip_durations[0]

    for i in range(1, len(clip_paths)):
        offset = cumulative - transition_duration
        vlabel, alabel = f"v{i}", f"a{i}"
        filter_parts.append(
            f"[{prev_v}][{i}:v]xfade=transition={transition_type}:"
            f"duration={transition_duration}:offset={offset}[{vlabel}]"
        )
        filter_parts.append(
            f"[{prev_a}][{i}:a]acrossfade=d={transition_duration}[{alabel}]"
        )
        prev_v, prev_a = vlabel, alabel
        cumulative += clip_durations[i] - transition_duration

    filter_complex = ";".join(filter_parts)
    final_local = os.path.join(workdir, "final_video.mp4")

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", f"[{prev_v}]", "-map", f"[{prev_a}]",
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        final_local
    ]
    print("Stitching with transitions...")
    run_ffmpeg(cmd, label="final stitch")

    # ---- Step 3: upload result back to Drive ----
    file_id = upload_file(service, drive_folder_id, final_local, "final_video.mp4", "video/mp4")
    shutil.rmtree(workdir, ignore_errors=True)

    link = f"https://drive.google.com/file/d/{file_id}/view"
    print(f"Done! {link}")
    # return {"file_id": file_id, "url": link}
    requests.post(
    callback_url,
    json={
        "status":"completed",
        "video_url":link,
        "file_id":file_id,
        "record_id":record_id
    }
)
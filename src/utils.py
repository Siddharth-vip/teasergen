import os
import re
import tempfile
import shutil
from pathlib import Path

def validate_youtube_url(url):
    """
    Validate a YouTube URL
    """
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    
    match = re.match(youtube_regex, url)
    return bool(match)

def format_duration(seconds):
    """
    Format seconds into a human-readable duration
    """
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def cleanup_temp_files():
    """
    Clean up temporary files created during processing
    """
    temp_dir = os.path.join(tempfile.gettempdir(), "teaser_generator")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    
    # Remove any other temporary files
    for file in ["temp_logo.png"]:
        if os.path.exists(file):
            os.remove(file)

def get_file_size_mb(file_path):
    """
    Get file size in megabytes
    """
    if os.path.exists(file_path):
        return os.path.getsize(file_path) / (1024 * 1024)
    return 0

def is_supported_video_format(filename):
    """
    Check if a file has a supported video format
    """
    supported_formats = ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm']
    return any(filename.lower().endswith(fmt) for fmt in supported_formats)
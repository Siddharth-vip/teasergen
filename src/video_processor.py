import os
import tempfile
from pathlib import Path
import requests
from pytubefix import YouTube
from pytube.cli import on_progress
import yt_dlp
from moviepy.editor import VideoFileClip, concatenate_videoclips, TextClip, CompositeVideoClip, ImageClip
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
from PIL import Image
import subprocess
import cv2
import numpy as np
import time

def process_video_file(video_path, output_path, start_time, end_time):
    """
    Extract a segment from a video file using ffmpeg.
    
    Args:
        video_path (str): Path to the input video file.
        output_path (str): Path to save the extracted video segment.
        start_time (int): Start time of the segment in seconds.
        end_time (int): End time of the segment in seconds.
        
    Returns:
        bool: True if processing was successful, False otherwise.
    """
    try:
        # Check if the video file is valid and readable
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception(f"Cannot open video file: {video_path}")
        
        # Check if we can read at least one frame
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise Exception(f"Video file appears corrupted or empty: {video_path}")
 
        # Use MoviePy's utility function which wraps ffmpeg
        ffmpeg_extract_subclip(video_path, start_time, end_time, targetname=output_path)
        return True
    except Exception as e:
        print(f"Error processing video: {e}")
        return False

def download_youtube_video_fallback(youtube_url):
    """
    Simple YouTube download with basic fallback using pytubefix.
    Includes a retry loop for file-locking issues.
    
    Args:
        youtube_url (str): The URL of the YouTube video.
        
    Returns:
        str: The path to the downloaded video file.
    """
    temp_dir = os.path.join(tempfile.gettempdir(), "teaser_generator")
    os.makedirs(temp_dir, exist_ok=True)
    
    max_attempts = 5
    base_delay = 5  # Start with a longer delay
    
    for attempt in range(max_attempts):
        try:
            yt = YouTube(youtube_url)
            
            # Try different stream filters if first attempt fails
            stream = None
            stream_filters = [
                {'progressive': True, 'file_extension': 'mp4'},
                {'adaptive': True, 'file_extension': 'mp4'},
                {'file_extension': 'mp4'}
            ]
            
            for filter_params in stream_filters:
                stream = yt.streams.filter(**filter_params).first()
                if stream:
                    break
            
            if not stream:
                raise Exception("No downloadable stream found")
            
            output_path = stream.download(output_path=temp_dir)
            return output_path
            
        except Exception as e:
            error_msg = str(e).lower()
            if "winerror 32" in error_msg or "permission denied" in error_msg:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                print(f"pytubefix file access error (attempt {attempt + 1}/{max_attempts}): {error_msg}")
                print(f"Waiting {delay} seconds before retrying...")
                time.sleep(delay)
            elif 'age restricted' in error_msg:
                raise Exception("Age-restricted video. Cannot download.")
            elif 'unavailable' in error_msg:
                raise Exception("Video is unavailable or private.")
            elif 'sign in' in error_msg:
                raise Exception("Video requires sign-in to access.")
            else:
                raise Exception(f"YouTube download failed: {str(e)}")
    
    raise Exception(f"All {max_attempts} attempts failed due to file access issues with pytubefix.")

def download_youtube_video(youtube_url):
    """
    Download video using yt-dlp first, with a fallback to pytubefix.
    Includes a retry loop to handle file lock errors (WinError 32).
    
    Args:
        youtube_url (str): The URL of the YouTube video.
        
    Returns:
        str: The path to the downloaded video file.
    """
    temp_dir = os.path.join(tempfile.gettempdir(), "teaser_generator")
    os.makedirs(temp_dir, exist_ok=True)
    
    max_attempts = 10
    base_delay = 5
    
    for attempt in range(max_attempts):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'format': 'bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best',
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                downloaded_file = ydl.prepare_filename(info)
            
            return downloaded_file
            
        except Exception as e:
            error_msg = str(e)
            if "WinError 32" in error_msg or "Permission denied" in error_msg:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                print(f"yt-dlp file access error (attempt {attempt + 1}/{max_attempts}): {error_msg}")
                print(f"Waiting {delay} seconds before retrying...")
                time.sleep(delay)
            else:
                print(f"yt-dlp download failed, falling back to pytubefix: {e}")
                return download_youtube_video_fallback(youtube_url)
    
    print(f"All {max_attempts} attempts failed due to file access issues. Falling back to pytubefix.")
    return download_youtube_video_fallback(youtube_url)

def add_subtitles_to_video(video_path, subtitles, output_path):
    """
    Add subtitles to video using OpenCV (no ImageMagick dependency)
    """
    try:
        # Open the video file
        cap = cv2.VideoCapture(video_path)
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Warning: Cannot open video {video_path}, skipping subtitles")
            return video_path
        
        # Try to read a few frames to check for corruption
        for _ in range(10):
            ret, frame = cap.read()
            if not ret:
                print(f"Warning: Video {video_path} appears corrupted, skipping subtitles")
                cap.release()
                return video_path
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            current_time = frame_count / fps
            
            # Check if any subtitle should be displayed at this time
            for start, end, text in subtitles:
                if start <= current_time <= end:
                    # Add text to frame
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 1.0
                    font_color = (255, 255, 255) 
                    thickness = 2
                    
                    # Get text size for background
                    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
                    
                    # Calculate text position (bottom center)
                    text_x = (width - text_size[0]) // 2
                    text_y = height - 50 
                    
                    # Add semi-transparent background for better readability
                    bg_padding = 10
                    cv2.rectangle(frame, 
                                (text_x - bg_padding, text_y - text_size[1] - bg_padding),
                                (text_x + text_size[0] + bg_padding, text_y + bg_padding),
                                (0, 0, 0), -1) 
                    
                    # Add text
                    cv2.putText(frame, text, (text_x, text_y), 
                                  font, font_scale, font_color, thickness, cv2.LINE_AA)
                    break
            
            # Write frame to output
            out.write(frame)
            frame_count += 1
        
        # Release resources
        cap.release()
        out.release()
        cv2.destroyAllWindows()
        
        return output_path
        
    except Exception as e:
        print(f"Error adding subtitles with OpenCV: {e}")
        # Fallback: return original video
        return video_path
    
def add_branding(video_path, logo_path=None, tagline=None, output_path=None):
    """
    Add branding using OpenCV
    """
    if output_path is None:
        output_path = video_path
        
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        # Load logo if provided
        logo_img = None
        if logo_path and os.path.exists(logo_path):
            logo_img = cv2.imread(logo_path, cv2.IMREAD_UNCHANGED)
            # Resize logo if needed
            logo_img = cv2.resize(logo_img, (100, 100))
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Add logo
            if logo_img is not None:
                # Position logo at top-left
                y_offset, x_offset = 10, 10
                # Handle transparent PNGs
                if logo_img.shape[2] == 4: 
                    alpha = logo_img[:, :, 3] / 255.0
                    for c in range(3):
                        frame[y_offset:y_offset+logo_img.shape[0], 
                               x_offset:x_offset+logo_img.shape[1], c] = \
                            alpha * logo_img[:, :, c] + \
                            (1 - alpha) * frame[y_offset:y_offset+logo_img.shape[0], 
                                                x_offset:x_offset+logo_img.shape[1], c]
                else:
                    frame[y_offset:y_offset+logo_img.shape[0], 
                           x_offset:x_offset+logo_img.shape[1]] = logo_img
            
            # Add tagline
            if tagline:
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.7
                font_color = (255, 255, 255)
                thickness = 2
                
                text_size = cv2.getTextSize(tagline, font, font_scale, thickness)[0]
                text_x = (width - text_size[0]) // 2
                text_y = 30 
                
                # Add background
                cv2.rectangle(frame, 
                              (text_x - 5, text_y - text_size[1] - 5),
                              (text_x + text_size[0] + 5, text_y + 5),
                              (0, 0, 0), -1)
                
                cv2.putText(frame, tagline, (text_x, text_y), 
                              font, font_scale, font_color, thickness, cv2.LINE_AA)
            
            out.write(frame)
        
        cap.release()
        out.release()
        cv2.destroyAllWindows()
        
        return output_path
        
    except Exception as e:
        print(f"Error adding branding with OpenCV: {e}")
        return video_path

def get_video_duration(video_path):
    """
    Get the duration of a video file using MoviePy.
    """
    try:
        clip = VideoFileClip(video_path)
        duration = clip.duration
        clip.close()
        return duration
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return 0

def is_video_file(file_path):
    """
    Check if a file is a valid video file based on its extension.
    """
    video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v']
    file_extension = os.path.splitext(file_path)[1].lower()
    return file_extension in video_extensions

# --- Sample Usage ---
if __name__ == "__main__":
    youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    try:
        print("Downloading video...")
        downloaded_video_path = download_youtube_video(youtube_url)
        print(f"Video downloaded to: {downloaded_video_path}")
        
        clip_duration = get_video_duration(downloaded_video_path)
        print(f"Video duration is: {clip_duration}s")

        # Set your desired segment times here
        segment_start = 5
        segment_end = 10
        
        if segment_end > clip_duration:
            print("Error: Desired segment end time is past the video duration.")
            print("Adjusting segment_end to be within video duration.")
            segment_end = clip_duration
        
        if segment_start > clip_duration:
            print("Error: Desired segment start time is past the video duration.")
            print("Skipping video processing.")
        else:
            temp_dir = os.path.dirname(downloaded_video_path)
            segmented_video_path = os.path.join(temp_dir, "segmented_video.mp4")
            print(f"Processing video segment from {segment_start}s to {segment_end}s...")
            
            # The actual video processing call is made here, after the duration check
            process_video_file(downloaded_video_path, segmented_video_path, segment_start, segment_end)
            print(f"Segment saved to: {segmented_video_path}")
        
            subtitles_list = [
                (0, 2, "Never Gonna Give You Up"),
                (2, 4, "Never Gonna Let You Down"),
                (4, 6, "Never Gonna Run Around And Desert You")
            ]
            subtitled_video_path = os.path.join(temp_dir, "subtitled_video.mp4")
            print("Adding subtitles...")
            add_subtitles_to_video(segmented_video_path, subtitles_list, subtitled_video_path)
            print(f"Video with subtitles saved to: {subtitled_video_path}")
            
            branded_video_path = os.path.join(temp_dir, "branded_video.mp4")
            print("Adding branding...")
            add_branding(subtitled_video_path, tagline="My Awesome Video")
            print(f"Branded video saved to: {branded_video_path}")
        
    except Exception as e:
        print(f"An error occurred: {e}")

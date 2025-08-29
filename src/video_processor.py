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
    Extract a segment from a video file directly using FFmpeg subprocess.
    """
    try:
        # Check if the input file exists
        if not os.path.exists(video_path):
            print(f"Error: Input video file not found at {video_path}")
            return False

        # Build the FFmpeg command
        # -y: Overwrite output file if it exists
        # -ss: Start time (seek from beginning)
        # -to: End time
        # -i: Input file
        # -c copy: Copy video and audio streams without re-encoding
        # (This is very fast and preserves quality)
        command = [
            'ffmpeg',
            '-y',
            '-ss', str(start_time),
            '-i', video_path,
            '-to', str(end_time - start_time), # Duration based on start/end
            '-c', 'copy',
            output_path
        ]

        # Execute the command
        subprocess.run(command, check=True)
        
        print("FFmpeg subclip extraction successful.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error processing video with FFmpeg: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
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

class CorruptedVideoError(Exception):
    pass

def download_youtube_video(youtube_url):
    """
    Downloads, re-encodes, and merges the best video and audio streams.
    """
    temp_dir = os.path.join(tempfile.gettempdir(), "teaser_generator")
    os.makedirs(temp_dir, exist_ok=True)
    
    max_attempts = 3
    base_delay = 5
    
    for attempt in range(max_attempts):
        video_file, audio_file = None, None
        try:
            # 1. Download video stream
            video_opts = {
                'outtmpl': os.path.join(temp_dir, 'video_stream_%(id)s.%(ext)s'),
                'format': 'bestvideo',
                'quiet': True,
                'no_warnings': True,
                'retries': 5
            }
            with yt_dlp.YoutubeDL(video_opts) as ydl:
                video_info = ydl.extract_info(youtube_url, download=True)
                video_file = ydl.prepare_filename(video_info)

            # 2. Download audio stream
            audio_opts = {
                'outtmpl': os.path.join(temp_dir, 'audio_stream_%(id)s.%(ext)s'),
                'format': 'bestaudio',
                'quiet': True,
                'no_warnings': True,
                'retries': 5
            }
            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                audio_info = ydl.extract_info(youtube_url, download=True)
                audio_file = ydl.prepare_filename(audio_info)
                
            # 3. Merge and Re-encode streams using a separate FFmpeg process
            output_file = os.path.join(temp_dir, f'merged_video_{video_info["id"]}.mp4')
            
            command = [
                'ffmpeg',
                '-i', video_file,
                '-i', audio_file,
                # Explicitly re-encode the video to H.264
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-preset', 'veryfast', # Use a fast preset for speed
                '-y',
                output_file
            ]
            
            subprocess.run(command, check=True)
            
            # Clean up individual stream files
            os.remove(video_file)
            os.remove(audio_file)
            
            # 4. Final Verification
            subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', output_file],
                capture_output=True,
                text=True,
                check=True
            )
            
            print(f"Successfully downloaded, merged, and verified video on attempt {attempt + 1}.")
            return output_file
            
        except subprocess.CalledProcessError as e:
            print(f"An FFmpeg or FFprobe command failed: {e}")
            if video_file and os.path.exists(video_file): os.remove(video_file)
            if audio_file and os.path.exists(audio_file): os.remove(audio_file)
            delay = base_delay * (2 ** attempt)
            print(f"Waiting {delay} seconds before retrying...")
            time.sleep(delay)
            
        except Exception as e:
            print(f"Download or merge failed (attempt {attempt + 1}/{max_attempts}): {e}")
            if video_file and os.path.exists(video_file): os.remove(video_file)
            if audio_file and os.path.exists(audio_file): os.remove(audio_file)
            delay = base_delay * (2 ** attempt)
            print(f"Waiting {delay} seconds before retrying...")
            time.sleep(delay)
    
    print(f"All {max_attempts} attempts failed. Falling back to pytubefix.")
    return download_youtube_video_fallback(youtube_url)


from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ImageClip
import os
import tempfile

def add_subtitles_and_branding(video_clip, subtitles=None, logo_path=None, tagline=None, output_path=None):
    """
    Adds optional subtitles, logo, and tagline to a video using MoviePy's native compositing.

    Args:
        video_clip (VideoFileClip): The source MoviePy video clip object.
        subtitles (list): A list of tuples, each containing (start_time, end_time, text_content). Optional.
        logo_path (str): The path to the logo image file. Optional.
        tagline (str): The tagline text to display. Optional.
        output_path (str): The desired path for the final output video. Optional.

    Returns:
        str: The path to the final, processed video file.
    """
    if not output_path:
        # A file path is still needed for the output
        output_path = os.path.join(tempfile.gettempdir(), "final_teaser.mp4")

    try:
        # The video is now the passed-in clip object
        video = video_clip
        
        # ... rest of the function is the same, no changes needed from here
        composited_clips = [video]

        if subtitles:
            for start, end, text_content in subtitles:
                text_clip = TextClip(
                    text_content, 
                    fontsize=40, 
                    color='white', 
                    stroke_color='black',
                    stroke_width=2,
                    font='Arial-Bold'
                ).set_position(('center', 'bottom')).set_start(start).set_end(end)
                composited_clips.append(text_clip)

        if logo_path and os.path.exists(logo_path):
            logo_clip = ImageClip(logo_path, duration=video.duration).set_position(("left", "top")).resize(height=100)
            composited_clips.append(logo_clip)
        
        if tagline:
            tagline_clip = TextClip(
                tagline, 
                fontsize=30, 
                color='white', 
                bg_color='black', 
                transparent=False
            ).set_position(('center', 'top')).set_duration(video.duration)
            composited_clips.append(tagline_clip)
        
        final_video = CompositeVideoClip(composited_clips)

        final_video.write_videofile(
            output_path, 
            codec='libx264',
            audio_codec='aac',
            preset='veryfast'
        )

        video.close()
        final_video.close()

        print(f"Final video successfully created at: {output_path}")
        return output_path

    except Exception as e:
        print(f"Error during video compositing: {e}")
        return None
    
    
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
# if __name__ == "__main__":
#     youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
#     try:
#         print("Downloading video...")
#         downloaded_video_path = download_youtube_video(youtube_url)
#         print(f"Video downloaded to: {downloaded_video_path}")
        
#         clip_duration = get_video_duration(downloaded_video_path)
#         print(f"Video duration is: {clip_duration}s")

#         # Set your desired segment times here
#         segment_start = 5
#         segment_end = 10
        
#         if segment_end > clip_duration:
#             print("Error: Desired segment end time is past the video duration.")
#             print("Adjusting segment_end to be within video duration.")
#             segment_end = clip_duration
        
#         if segment_start > clip_duration:
#             print("Error: Desired segment start time is past the video duration.")
#             print("Skipping video processing.")
#         else:
#             temp_dir = os.path.dirname(downloaded_video_path)
#             segmented_video_path = os.path.join(temp_dir, "segmented_video.mp4")
#             print(f"Processing video segment from {segment_start}s to {segment_end}s...")
            
#             # The actual video processing call is made here, after the duration check
#             process_video_file(downloaded_video_path, segmented_video_path, segment_start, segment_end)
#             print(f"Segment saved to: {segmented_video_path}")
        
#             # Define optional elements
#             subtitles_list = None
#             logo_file_path = None
#             tagline_text = None

#             # Logic to conditionally set optional elements based on user input
#             subtitles_list = [
#                 (0.0, 5.0, "Discover something amazing"),
#                 (5.0, 10.0, "With our innovative solution"),
#                 (10.0, 15.0, "Join us today!")
#             ]

#             try:
#                 # Use the single, combined function to process the video
#                 final_output_path = add_subtitles_and_branding(
#                     video_path=segmented_video_path,
#                     subtitles=subtitles_list,
#                     logo_path=logo_file_path,
#                     tagline=tagline_text,
#                     output_path="outputs/teaser_professional_30s.mp4"
#                 )

#                 print(f"Final video with all elements saved to: {final_output_path}")

#             finally:
#                 # Clean up the temporary logo file
#                 if logo_file_path and os.path.exists(logo_file_path):
#                     os.remove(logo_file_path)
        
#     except Exception as e:
#         print(f"An error occurred: {e}")

# Configuration settings for the AI Video Teaser Generator

# Supported video formats
SUPPORTED_VIDEO_FORMATS = [".mp4", ".mov", ".avi", ".mkv", ".wmv"]

# Maximum file size for uploads (in MB)
MAX_FILE_SIZE_MB = 500

# AI model settings
DEFAULT_AI_MODEL = "gpt-4"  # Change to "gpt-3.5-turbo" if needed

# Video processing settings
DEFAULT_TEASER_DURATION = 30  # seconds
MAX_TEASER_DURATION = 120     # seconds
MIN_TEASER_DURATION = 10      # seconds

# Output settings
OUTPUT_DIR = "outputs"
TEMP_DIR = "temp"

# Branding defaults
DEFAULT_FONT = "Arial"
DEFAULT_FONT_SIZE = 24
DEFAULT_SUBTITLE_COLOR = "white"
DEFAULT_SUBTITLE_BG_COLOR = "rgba(0, 0, 0, 0.5)"
#!/usr/bin/env python3
"""
Script to convert mono audio files to stereo format for PSR compatibility.

This script converts mono WAV files to stereo 16-bit PCM format at 8000Hz
to ensure compatibility with the Sentech PSR service requirements.
"""

import os
import sys
import wave
import tempfile
import shutil
from pathlib import Path
import subprocess
from typing import List, Dict, Any

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Add the src directory to the Python path
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Define source and destination directories
SOURCE_AUDIO_DIR = os.path.join(PROJECT_ROOT, "data", "audio_mono")
DEST_AUDIO_DIR = os.path.join(PROJECT_ROOT, "data", "audio")

# Target specifications for PSR compatibility
TARGET_SAMPLE_RATE = 8000  # PSR requires 16000Hz
TARGET_CHANNELS = 2  # Stereo
TARGET_BIT_DEPTH = 16  # 16-bit PCM


def get_audio_info(file_path: str) -> Dict[str, Any]:
    """
    Get audio file information.
    
    Args:
        file_path: Path to the audio file
        
    Returns:
        Dictionary with audio file information
    """
    try:
        with wave.open(file_path, 'rb') as wav:
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            bit_depth = wav.getsampwidth() * 8
            frames = wav.getnframes()
            duration = frames / sample_rate
            
            return {
                "channels": channels,
                "sample_rate": sample_rate,
                "bit_depth": bit_depth,
                "frames": frames,
                "duration": duration,
                "needs_conversion": (
                    sample_rate != TARGET_SAMPLE_RATE or 
                    channels != TARGET_CHANNELS or 
                    bit_depth != TARGET_BIT_DEPTH
                )
            }
    except Exception as e:
        print(f"Error reading audio file {file_path}: {e}")
        return {
            "error": str(e),
            "needs_conversion": True  # Assume it needs conversion on error
        }


def convert_to_stereo(input_path: str, output_path: str) -> bool:
    """
    Convert a mono audio file to stereo format with target specifications.
    
    Args:
        input_path: Path to the input audio file
        output_path: Path to save the converted audio file
        
    Returns:
        True if conversion succeeded, False otherwise
    """
    try:
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Create a temporary directory for the operation
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_output = os.path.join(temp_dir, "converted.wav")
            
            # Use ffmpeg to convert the audio
            # -ac 2: convert to stereo
            # -af "pan=stereo|c0=c0|c1=c0": duplicate mono channel to both stereo channels
            cmd = [
                "ffmpeg",
                "-i", input_path,
                "-ar", str(TARGET_SAMPLE_RATE),
                "-ac", str(TARGET_CHANNELS),
                "-sample_fmt", "s16",  # 16-bit signed PCM
                "-af", "pan=stereo|c0=c0|c1=c0",  # Duplicate mono to both channels
                "-y",  # Overwrite output files
                temp_output
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                print(f"Error converting {input_path}: {result.stderr}")
                return False
                
            # Move the temp file to the destination
            shutil.copy2(temp_output, output_path)
            return True
            
    except Exception as e:
        print(f"Error during conversion: {e}")
        return False


def find_all_audio_files(audio_dir: str) -> List[str]:
    """
    Find all WAV files in the audio directory.
    
    Args:
        audio_dir: Path to the audio directory
        
    Returns:
        List of relative paths to WAV files
    """
    wav_files = []
    for root, dirs, files in os.walk(audio_dir):
        for file in files:
            if file.lower().endswith('.wav'):
                rel_path = os.path.relpath(os.path.join(root, file), audio_dir)
                wav_files.append(rel_path)
    return wav_files


def convert_audio_files(source_dir: str, dest_dir: str) -> bool:
    """
    Convert all mono audio files to stereo format.
    
    Args:
        source_dir: Path to the source audio directory
        dest_dir: Path to the destination audio directory
        
    Returns:
        True if all files were processed successfully, False otherwise
    """
    # Check if ffmpeg is installed
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except Exception:
        print("Error: ffmpeg is not installed or not in the PATH.")
        print("Please install ffmpeg and try again.")
        return False
    
    # Ensure destination directory exists
    os.makedirs(dest_dir, exist_ok=True)
    
    # Find all WAV files
    wav_files = find_all_audio_files(source_dir)
    print(f"Found {len(wav_files)} WAV files to process")
    
    # Process each file
    success_count = 0
    skipped_count = 0
    error_count = 0
    
    for rel_path in wav_files:
        input_path = os.path.join(source_dir, rel_path)
        output_path = os.path.join(dest_dir, rel_path)
        
        # Get audio info
        audio_info = get_audio_info(input_path)
        
        # Check if output file exists and is already in the correct format
        if os.path.exists(output_path):
            output_info = get_audio_info(output_path)
            if not output_info.get("needs_conversion", True):
                print(f"Skipping {rel_path} (output file already exists and is in correct format)")
                skipped_count += 1
                continue
        
        print(f"Processing {rel_path}...")
        print(f"  Input format: {audio_info.get('sample_rate', 'unknown')}Hz, "
              f"{audio_info.get('channels', 'unknown')} channel(s), "
              f"{audio_info.get('bit_depth', 'unknown')}-bit")
        
        # Convert the file
        if convert_to_stereo(input_path, output_path):
            print(f"  Converted to stereo: {output_path}")
            print(f"  Output format: {TARGET_SAMPLE_RATE}Hz, {TARGET_CHANNELS} channels, {TARGET_BIT_DEPTH}-bit PCM")
            success_count += 1
        else:
            error_count += 1
    
    # Print summary
    print("\nSummary:")
    print(f"  Successfully converted: {success_count}")
    print(f"  Skipped (already correct): {skipped_count}")
    print(f"  Errors: {error_count}")
    
    return error_count == 0


def main():
    """Main function."""
    # Override with environment variables if provided
    source_dir = os.environ.get("SOURCE_AUDIO_DIR", SOURCE_AUDIO_DIR)
    dest_dir = os.environ.get("DEST_AUDIO_DIR", DEST_AUDIO_DIR)
    
    print(f"Source audio directory (mono): {source_dir}")
    print(f"Destination audio directory (stereo): {dest_dir}")
    print(f"Target specifications: {TARGET_SAMPLE_RATE}Hz, {TARGET_CHANNELS} channels, {TARGET_BIT_DEPTH}-bit PCM")
    
    if not os.path.exists(source_dir):
        print(f"Error: Source audio directory {source_dir} not found.")
        return False
    
    # Ask for confirmation
    response = input("Continue with audio conversion to stereo? [y/N] ").strip().lower()
    if response != 'y':
        print("Operation cancelled.")
        return False
    
    # Perform the conversion
    return convert_audio_files(source_dir, dest_dir)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 
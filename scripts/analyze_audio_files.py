#!/usr/bin/env python3
"""
Script to analyze audio files and display their specifications.

This script examines WAV files and prints detailed information about:
- Sample rate
- Bit depth
- Number of channels
- Duration
- File size
- Format
"""

import os
import sys
import wave
import argparse
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Add the src directory to the Python path
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Default audio directory
DEFAULT_AUDIO_DIR = os.path.join(PROJECT_ROOT, "audio")


def get_audio_info(file_path: str) -> Dict[str, Any]:
    """
    Get detailed audio file information.
    
    Args:
        file_path: Path to the audio file
        
    Returns:
        Dictionary with audio file information
    """
    file_stats = os.stat(file_path)
    file_size = file_stats.st_size
    file_size_mb = file_size / (1024 * 1024)
    
    try:
        with wave.open(file_path, 'rb') as wav:
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            bit_depth = sample_width * 8
            frames = wav.getnframes()
            duration = frames / sample_rate
            compression_type = wav.getcomptype()
            compression_name = wav.getcompname()
            
            # Calculate average bitrate
            bitrate = (file_size * 8) / (duration * 1000) if duration > 0 else 0
            
            return {
                "channels": channels,
                "sample_rate": sample_rate,
                "bit_depth": bit_depth,
                "frames": frames,
                "duration": duration,
                "file_size": file_size,
                "file_size_mb": file_size_mb,
                "compression_type": compression_type,
                "compression_name": compression_name or "Uncompressed PCM",
                "bitrate": bitrate,
                "error": None
            }
    except Exception as e:
        return {
            "error": str(e),
            "file_size": file_size,
            "file_size_mb": file_size_mb
        }


def find_audio_files(audio_dir: str, recursive: bool = False) -> List[str]:
    """
    Find all WAV files in the audio directory.
    
    Args:
        audio_dir: Path to the audio directory
        recursive: Whether to search recursively in subdirectories
        
    Returns:
        List of paths to WAV files
    """
    wav_files = []
    
    if recursive:
        for root, _, files in os.walk(audio_dir):
            for file in files:
                if file.lower().endswith('.wav'):
                    wav_files.append(os.path.join(root, file))
    else:
        for file in os.listdir(audio_dir):
            if file.lower().endswith('.wav'):
                wav_files.append(os.path.join(audio_dir, file))
    
    return sorted(wav_files)


def print_audio_info(info: Dict[str, Any], file_path: str, verbose: bool = False) -> None:
    """
    Print audio file information.
    
    Args:
        info: Dictionary with audio information
        file_path: Path to the audio file
        verbose: Whether to print detailed information
    """
    if info.get("error"):
        print(f"Error analyzing {file_path}: {info['error']}")
        return
    
    # Print basic information
    print(f"\n{'-' * 60}")
    print(f"File: {os.path.basename(file_path)}")
    print(f"Sample Rate: {info['sample_rate']} Hz")
    print(f"Bit Depth: {info['bit_depth']} bit")
    print(f"Channels: {info['channels']} ({'Stereo' if info['channels'] == 2 else 'Mono'})")
    print(f"Duration: {info['duration']:.2f} seconds")
    print(f"Size: {info['file_size_mb']:.2f} MB")
    
    # Print additional information if verbose
    if verbose:
        print(f"Path: {file_path}")
        print(f"Frames: {info['frames']}")
        print(f"File Size: {info['file_size']} bytes")
        print(f"Compression: {info['compression_type']} ({info['compression_name']})")
        print(f"Bitrate: {info['bitrate']:.2f} kbps")
    print(f"{'-' * 60}")


def analyze_audio_file(file_path: str, verbose: bool = False) -> Dict[str, Any]:
    """
    Analyze a single audio file and print its information.
    
    Args:
        file_path: Path to the audio file
        verbose: Whether to print detailed information
        
    Returns:
        Dictionary with audio information
    """
    info = get_audio_info(file_path)
    print_audio_info(info, file_path, verbose)
    return info


def analyze_directory(audio_dir: str, recursive: bool = False, 
                     limit: Optional[int] = None, 
                     verbose: bool = False) -> None:
    """
    Analyze all audio files in a directory.
    
    Args:
        audio_dir: Path to the audio directory
        recursive: Whether to search recursively in subdirectories
        limit: Maximum number of files to analyze
        verbose: Whether to print detailed information
    """
    wav_files = find_audio_files(audio_dir, recursive)
    
    if not wav_files:
        print(f"No WAV files found in {audio_dir}")
        return
    
    print(f"Found {len(wav_files)} WAV files" + 
          (f" (showing {limit})" if limit and limit < len(wav_files) else ""))
    
    if limit:
        wav_files = wav_files[:limit]
    
    # Print header
    print("\nAUDIO FILE ANALYSIS")
    print("===================")
    
    # Process each file
    for file_path in wav_files:
        analyze_audio_file(file_path, verbose)
    
    # Print summary
    print("\nSUMMARY")
    print("=======")
    print(f"Total files analyzed: {len(wav_files)}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Analyze audio files and display their specifications")
    parser.add_argument("path", nargs="?", default=DEFAULT_AUDIO_DIR,
                        help="Path to audio file or directory (default: %(default)s)")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Search recursively in subdirectories")
    parser.add_argument("-l", "--limit", type=int, default=None,
                        help="Limit the number of files to analyze")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print detailed information")
    
    args = parser.parse_args()
    
    path = os.path.abspath(args.path)
    
    if not os.path.exists(path):
        print(f"Error: Path {path} does not exist.")
        return False
    
    # Process a single file
    if os.path.isfile(path):
        if not path.lower().endswith('.wav'):
            print(f"Error: {path} is not a WAV file.")
            return False
        
        analyze_audio_file(path, args.verbose)
        
    # Process a directory of files
    else:
        print(f"Analyzing audio files in: {path}")
        analyze_directory(path, args.recursive, args.limit, args.verbose)
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0) 
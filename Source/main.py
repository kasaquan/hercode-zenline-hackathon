"""
Entry point for Outdoor Retail Recommender System
Runs Streamlit dashboard with correct working directory
"""

import subprocess
import sys
from pathlib import Path

def main():
    # Get the directory where this script lives
    source_dir = Path(__file__).parent
    
    # Run streamlit from Source directory
    print(f"🚀 Starting Outdoor Retail Recommender Dashboard...")
    print(f"📁 Working directory: {source_dir}")
    
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "App/dashboard.py"],
        cwd=source_dir
    )

if __name__ == "__main__":
    main()
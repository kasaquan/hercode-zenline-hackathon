"""
Entry point for Zenline Outdoor Retail Recommender System
Runs customer chat interface with correct working directory
"""

import subprocess
import sys
from pathlib import Path

def main():
    # Get the directory where this script lives
    source_dir = Path(__file__).parent
    
    # Run streamlit from Source directory
    print(f"🚀 Starting Zenline Outdoor Retail Recommender...")
    print(f"📁 Working directory: {source_dir}")
    print(f"🌐 Opening browser at http://localhost:8501")
    
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "App/customer_chat.py"],
        #[sys.executable, "-m", "streamlit", "run", "App/dashboard.py"],
        cwd=source_dir
    )

if __name__ == "__main__":
    main()

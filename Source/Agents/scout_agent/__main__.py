"""Package entry point so the Scout Agent can be run as a module:

    python -m Source.Agents.scout_agent --market DACH --seeds "trail running shoes"
"""
from .scout import main

if __name__ == "__main__":
    main()

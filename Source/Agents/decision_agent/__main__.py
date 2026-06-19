"""Package entry point — runs the full orchestrated pipeline:

    python -m Source.Agents.decision_agent \
      --query "Decathlon CH is looking for decision support on winter jackets" \
      --market DACH --company https://www.decathlon.ch

To re-score existing out/signals.csv + out/company_profile.json without rerunning
Scout/Profiler, call the scoring core directly:

    python -m Source.Agents.decision_agent.decision --signals out/signals.csv ...
"""
from .pipeline import main

if __name__ == "__main__":
    main()

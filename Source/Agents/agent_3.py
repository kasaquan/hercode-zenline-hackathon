"""
Agent 3: Company Profile Extractor
Extracts company information from website + PDF strategy + user notes.
Infers strategic assortment gaps from executive strategy.
Returns structured JSON profile ready for Agent 2.
"""

from dotenv import load_dotenv
import os
load_dotenv()

import json
import re
import sys
from typing import Optional
from anthropic import Anthropic

# ... rest of code
# Company Profile Schema
COMPANY_PROFILE_SCHEMA = {
    "company_name": "string",
    "website": "string",
    "active_markets": ["CH", "AT", "DE", "other"],
    "primary_cantons": ["ZH", "BE", "VS"],
    "positioning": "budget | mid-range | premium | niche",
    "target_price_band": "economy (<100) | mid (100-300) | premium (300+) | mixed",
    "customer_segments": ["ultralight hikers", "climbers", "families", "professionals"],
    "current_product_categories": ["shells", "packs", "boots", "nutrition"],
    "current_assortment_gaps": "string - what they're missing NOW",
    "store_count": "integer or range",
    "distribution_model": "direct | retail | hybrid",
    "target_gross_margin": "low (15-25%) | medium (25-40%) | high (40%+)",
    "innovation_appetite": "low | medium | high",
    #"supply_chain_constraints": "string",
    "strategic_expansion_focus": "string - what exec strategy says they're moving into",
    "strategic_timeline": "string - when (e.g., Q3 2026, 2027)",
    "strategic_rationale": "string - why are they expanding?",
    "strategic_assortment_gaps": "string - INFERRED: what's missing to execute strategy",
    "data_sources": ["website", "pdf", "user_notes"],
    "confidence_by_field": {"field_name": "high | medium | low"},
    "extra": "string - unstructured insights"
}


def extract_company_profile(
    company_link: str,
    pdf_content: Optional[str] = None,
    user_notes: Optional[str] = None,
    verbose: bool = False
) -> dict:
    """
    Extract company profile using Claude API with structured JSON output.
    
    Args:
        company_link: Company website URL
        pdf_content: Optional raw text from executive strategy PDF
        user_notes: Optional user-provided context
        verbose: Print reasoning to stdout
    
    Returns:
        dict: Structured company profile JSON
    """
    
    client = Anthropic()
    
    # Build context
    context_parts = [f"Company Website: {company_link}"]
    
    if pdf_content:
        context_parts.append(f"PDF Executive Strategy Document:\n{pdf_content[:2000]}")  # First 2000 chars
    
    if user_notes:
        context_parts.append(f"User Notes:\n{user_notes}")
    
    context = "\n\n".join(context_parts)
    
    system_prompt = """You are Agent 3: Company Profile Extractor for an outdoor retail recommender system.

Extract company information into structured JSON. Your job:
1. Identify current positioning, assortment, markets from website/notes
2. Extract strategic direction from executive strategy (if PDF provided)
3. INFER strategic assortment gaps: what's missing to execute the strategy

CRITICAL RULE on Strategic Gaps:
If the PDF mentions expansion into a product category (e.g., "we're moving into ultralight systems by 2027")
AND the current assortment doesn't include it, list what's needed as a STRATEGIC ASSORTMENT GAP.

Example:
- Current assortment: alpine climbing shells, mid-weight packs, boots
- Strategy: "Expand into lightweight backpacking kits by 2027"
- Strategic gaps to infer: "Lightweight ultralight packs (<500g), modular kit systems, lightweight tents"

Output ONLY valid JSON. No preamble. No markdown. No explanations.

Use this schema:
{
  "company_name": "string",
  "website": "string",
  "active_markets": ["CH", "AT", "DE", "etc"],
  "primary_cantons": ["ZH", "BE", "VS", "GE", "etc"],
  "positioning": "budget | mid-range | premium | niche",
  "target_price_band": "economy (<100) | mid (100-300) | premium (300+) | mixed",
  "customer_segments": ["array of segments"],
  "current_product_categories": ["array of categories"],
  "current_assortment_gaps": "string - specific gaps NOW",
  "store_count": "integer or range",
  "distribution_model": "direct | retail | hybrid",
  "target_gross_margin": "low | medium | high",
  "innovation_appetite": "low | medium | high",
  "strategic_expansion_focus": "string - what they're moving into",
  "strategic_timeline": "string - when",
  "strategic_rationale": "string - why",
  "strategic_assortment_gaps": "string - INFERRED gaps to execute strategy",
  "data_sources": ["website", "pdf", "user_notes"],
  "confidence_by_field": {"field_name": "high | medium | low"},
  "extra": "string"
}

Be specific. Write "Ultralight packs <500g, modular systems" not "improve assortment".
Always infer strategic gaps from strategy text if provided."""
    
    if verbose:
        print("[Agent 3] Extracting company profile...")
        print(f"[Agent 3] Context length: {len(context)} chars")
    
    try:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=2000,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": context
                }
            ]
        )
        
        response_text = response.content[0].text.strip()
        
        # Clean markdown if present
        if response_text.startswith("```"):
            response_text = re.sub(r"```json?\n?", "", response_text).rstrip("```").strip()
        
        profile = json.loads(response_text)
        
        if verbose:
            print("[Agent 3] ✓ Profile extracted successfully")
            print(f"[Agent 3] Company: {profile.get('company_name', 'N/A')}")
            print(f"[Agent 3] Strategic focus: {profile.get('strategic_expansion_focus', 'None provided')}")
        
        return profile
    
    except json.JSONDecodeError as e:
        print(f"[Agent 3] ✗ JSON parse error: {e}")
        print(f"[Agent 3] Raw response (first 500 chars): {response_text[:500]}")
        return {
            "error": "Failed to parse profile",
            "raw_response": response_text[:500],
            "company_name": "Unknown"
        }
    
    except Exception as e:
        print(f"[Agent 3] ✗ API error: {e}")
        return {
            "error": f"API error: {str(e)}",
            "company_name": "Unknown"
        }


def format_profile_for_display(profile: dict) -> str:
    """Format profile JSON for readable display."""
    return json.dumps(profile, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # Test case: Swiss outdoor retailer with strategy
    test_pdf = """
    Executive Strategy 2026-2027 (Decathlon CH)
    
    Current Focus: Alpine climbing, winter sports, family hiking
    Market: Switzerland + Benelux
    Current assortment: Technical shells, mid-weight packs, boots, nutrition bars
    
    Strategic Expansion:
    - Move into ultralight backpacking segment (targeting millennials, urban hikers)
    - Launch sustainable materials line (recycled nylon, bio-based)
    - Modular kit systems (customers can build custom packs)
    - Timeline: Q3 2026 soft launch, full rollout 2027
    - Rationale: Growing demand, margin opportunity (35% target), brand differentiation
    - Partnerships: 2-3 specialist brands in ultralight/sustainable space
    
    Financial target: 25% YoY growth in new categories
    """
    
    test_notes = "Premium positioning, 12 stores across CH, high innovation appetite"
    
    print("=" * 60)
    print("Agent 3 Test: Company Profile Extraction")
    print("=" * 60)
    
    profile = extract_company_profile(
        company_link="https://www.decathlon.ch",
        pdf_content=test_pdf,
        user_notes=test_notes,
        verbose=True
    )
    
    print("\nExtracted Profile:")
    print(format_profile_for_display(profile))

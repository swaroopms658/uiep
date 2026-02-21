import os
from groq import Groq
from config import settings
from typing import List, Dict

# Assuming API_KEY is loaded in environment via GROQ_API_KEY
client = Groq(api_key=os.environ.get("GROQ_API_KEY", "fallback_key"))

def categorize_merchants(merchants: List[str]) -> Dict[str, str]:
    """
    Given a list of merchant names, returns a dictionary mapping merchant to a generic category.
    Categories: Food, Travel, Bills, Shopping, Transfer, Entertainment, Health, Other.
    """
    if not merchants:
        return {}
        
    prompt = f"""
    Categorize the following list of merchants into one of these strict categories:
    Food, Travel, Bills, Shopping, Transfer, Entertainment, Health, Other.
    
    Respond STRICTLY in the following format with no markdown, no other text:
    Merchant 1|Category
    Merchant 2|Category
    
    Merchants:
    {', '.join(merchants)}
    """
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama3-8b-8192",
        )
        response_text = chat_completion.choices[0].message.content
        
        result_map = {}
        for line in response_text.strip().split('\n'):
            parts = line.split('|')
            if len(parts) == 2:
                result_map[parts[0].strip()] = parts[1].strip()
        return result_map
    except Exception as e:
        print(f"Error during LLM categorization: {e}")
        # Default to Other if API fails
        return {m: "Other" for m in merchants}

def batched_categorization(merchants: List[str], batch_size: int = 50) -> Dict[str, str]:
    """Process large lists of merchants in batches to avoid context limit or rate limits"""
    final_map = {}
    for i in range(0, len(merchants), batch_size):
        batch = merchants[i:i+batch_size]
        batch_results = categorize_merchants(batch)
        final_map.update(batch_results)
    return final_map

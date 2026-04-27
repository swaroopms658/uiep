from typing import List, Dict
from groq_client import chat_completion

def categorize_merchants(merchants: List[str]) -> Dict[str, str]:
    if not merchants:
        return {}

    prompt = (
        "Categorize the following list of merchants into one of these strict categories:\n"
        "Food, Travel, Bills, Shopping, Transfer, Entertainment, Health, Other.\n\n"
        "Respond STRICTLY in the following format with no markdown, no other text:\n"
        "Merchant 1|Category\n"
        "Merchant 2|Category\n\n"
        f"Merchants:\n{', '.join(merchants)}"
    )

    try:
        response_text = chat_completion([{"role": "user", "content": prompt}])
        result_map = {}
        for line in response_text.strip().split('\n'):
            parts = line.split('|')
            if len(parts) == 2:
                result_map[parts[0].strip()] = parts[1].strip()
        return result_map
    except Exception as e:
        print(f"Error during LLM categorization: {e}")
        return {m: "Other" for m in merchants}

def batched_categorization(merchants: List[str], batch_size: int = 50) -> Dict[str, str]:
    """Process large lists of merchants in batches to avoid context limit or rate limits"""
    final_map = {}
    for i in range(0, len(merchants), batch_size):
        batch = merchants[i:i+batch_size]
        batch_results = categorize_merchants(batch)
        final_map.update(batch_results)
    return final_map

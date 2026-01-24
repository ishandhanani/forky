import re

def extract_json_from_markdown(response: str) -> str:
    """
    Extract JSON content from LLM response, handling markdown code blocks.
    
    Searches for the first fenced code block (```json or ```). 
    If found, returns its content. Otherwise, returns the stripped original string.
    
    Args:
        response: Raw LLM response text.
        
    Returns:
        Clean JSON string without markdown formatting.
    """
    # Search for the first fenced block anywhere in the response
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response)
    
    if match:
        return match.group(1).strip()
    
    return response.strip()

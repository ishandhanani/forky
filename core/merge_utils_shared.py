"""
Shared utility functions for merge modules.
"""


def extract_json_from_markdown(response: str) -> str:
    """
    Extract JSON content from LLM response, handling markdown code blocks.
    
    If the response is wrapped in ```json or ``` code fences, extracts only
    the content inside the fences.
    
    Args:
        response: Raw LLM response text.
        
    Returns:
        Clean JSON string without markdown formatting.
    """
    json_str = response.strip()
    
    if not json_str.startswith("```"):
        return json_str
    
    # Extract content from code block
    lines = json_str.split("\n")
    json_lines = []
    in_block = False
    
    for line in lines:
        if line.startswith("```"):
            in_block = not in_block
            continue
        if in_block:
            json_lines.append(line)
    
    return "\n".join(json_lines)

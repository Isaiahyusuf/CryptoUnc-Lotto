from gpt4all import GPT4All

model = GPT4All("ggml-gpt4all-j-v1.3-groovy")

def ask_ai(system_prompt: str, user_prompt: str) -> str:
    """
    Generate a response from the AI model.
    
    Args:
        system_prompt: The system prompt that sets the AI's behavior
        user_prompt: The user's question or input
    
    Returns:
        The AI-generated response
    """
    combined_prompt = f"{system_prompt}\n\nUser: {user_prompt}\n\nAssistant:"
    response = model.generate(combined_prompt, max_tokens=500)
    return response

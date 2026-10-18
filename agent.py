from google import genai
from google.genai import types

client = genai.Client()  # reads GEMINI_API_KEY from the environment
MODEL = "gemini-3.8-flash"

# Mock "directory" (fake data)
USERS = {
    "alice@example.com": {"name": "Alice", "status": "locked", "mfa_method": "authenticator_app"},
    "bob@example.com": {"name": "Bob", "status": "active", "mfa_method": "sms"},
}

def lookup_user(email):
    return USERS.get(email, {"error": "user not found"})

# Tool description the LLM sees
lookup_user_decl = {
    "name": "lookup_user",
    "description": "Look up an employee account by email. Returns account status and MFA method.",
    "parameters": {
        "type": "object",
        "properties": {"email": {"type": "string", "description": "Employee email address"}},
        "required": ["email"],
    },
}
config = types.GenerateContentConfig(
    tools=[types.Tool(function_declarations=[lookup_user_decl])]
)

def run_agent(user_message):
    contents = [types.Content(role="user", parts=[types.Part(text=user_message)])]
    while True:
        response = client.models.generate_content(
            model=MODEL, contents=contents, config=config
        )
        calls = response.function_calls
        # No tool requested -> final answer
        if not calls:
            return response.text

        # Model asked for a tool: run it and send the result back
        contents.append(response.candidates[0].content)
        parts = []
        for call in calls:
            print(f"[tool call] {call.name}({dict(call.args)})")
            result = lookup_user(**call.args)
            parts.append(types.Part.from_function_response(
                name=call.name, response={"result": result}
            ))
        contents.append(types.Content(role="user", parts=parts))

if __name__ == "__main__":
    print(run_agent("Hi, my email is alice@example.com and I can't log in. What's wrong?"))
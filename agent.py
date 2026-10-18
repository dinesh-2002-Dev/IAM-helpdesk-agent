import json
from datetime import datetime, timezone
import random
import time
from google import genai
from google.genai import types
from google.genai import errors

client = genai.Client()  # reads GEMINI_API_KEY from the environment
MODEL = "gemini-3.8-flash"  # change this if you switch models

SYSTEM_PROMPT = (
    "You are an IAM helpdesk assistant. Use the tools to help employees. "
    "Before issuing a temporary access code, you must ask the user for their employee ID. "
    "Never guess or invent an employee ID."
)

# ---------- Mock data (fake, for the demo) ----------
USERS = {
    "alice@example.com": {"name": "Alice", "status": "locked", "mfa_method": "authenticator_app"},
    "bob@example.com": {"name": "Bob", "status": "active", "mfa_method": "sms"},
}

GROUPS = {
    "alice@example.com": ["All-Employees", "VPN-Users"],
    "bob@example.com": ["All-Employees", "Finance-Team"],
}

EMPLOYEE_IDS = {
    "alice@example.com": "E1001",
    "bob@example.com": "E1002",
}

TICKETS = []

# ---------- Tool functions (what actually runs) ----------
def lookup_user(email):
    return USERS.get(email, {"error": "user not found"})

def check_group_membership(email):
    if email not in GROUPS:
        return {"error": "user not found"}
    return {"email": email, "groups": GROUPS[email]}

def create_ticket(email, summary):
    ticket_id = f"INC{1000 + len(TICKETS) + 1}"
    TICKETS.append({"id": ticket_id, "email": email, "summary": summary})
    return {"ticket_id": ticket_id, "status": "created"}

def generate_temp_access_code(email, employee_id):
    # Guardrail enforced in code: wrong or missing ID means no code
    if EMPLOYEE_IDS.get(email) != employee_id:
        return {"error": "identity verification failed"}
    return {
        "email": email,
        "temp_access_code": f"TAP-{random.randint(100000, 999999)}",
        "valid_minutes": 60,
    }

# ---------- Tool descriptions the LLM sees ----------
lookup_user_decl = {
    "name": "lookup_user",
    "description": "Look up an employee account by email. Returns account status and MFA method.",
    "parameters": {
        "type": "object",
        "properties": {"email": {"type": "string", "description": "Employee email address"}},
        "required": ["email"],
    },
}
check_group_decl = {
    "name": "check_group_membership",
    "description": "List the access groups an employee belongs to.",
    "parameters": {
        "type": "object",
        "properties": {"email": {"type": "string", "description": "Employee email address"}},
        "required": ["email"],
    },
}
create_ticket_decl = {
    "name": "create_ticket",
    "description": "Create a support ticket for an employee with a short summary of the problem.",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "Employee email address"},
            "summary": {"type": "string", "description": "Short description of the issue"},
        },
        "required": ["email", "summary"],
    },
}
temp_code_decl = {
    "name": "generate_temp_access_code",
    "description": "Issue a temporary access code to an employee who has verified their identity with their employee ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "Employee email address"},
            "employee_id": {"type": "string", "description": "Employee ID provided by the user"},
        },
        "required": ["email", "employee_id"],
    },
}

# Maps tool names to the real Python functions
TOOL_FUNCTIONS = {
    "lookup_user": lookup_user,
    "check_group_membership": check_group_membership,
    "create_ticket": create_ticket,
    "generate_temp_access_code": generate_temp_access_code,
}

def log_tool_call(name, args, result):
    safe_result = dict(result)
    if "temp_access_code" in safe_result:
        safe_result["temp_access_code"] = "***masked***"  # never log secrets
    entry = {
        "time": datetime.now(timezone.utc).isoformat(),
        "tool": name,
        "args": args,
        "result": safe_result,
    }
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

config = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[types.Tool(function_declarations=[
        lookup_user_decl, check_group_decl, create_ticket_decl, temp_code_decl
    ])],
)

# ---------- Calls the model, with retries for "server busy" errors ----------
def call_model(contents):
    for attempt in range(4):
        try:
            return client.models.generate_content(
                model=MODEL, contents=contents, config=config
            )
        except errors.APIError as e:
            if e.code == 503:
                wait = 5 * (attempt + 1)
                print(f"[model busy, retrying in {wait}s]")
                time.sleep(wait)
            elif e.code == 429:
                raise RuntimeError(
                    "Free-tier quota reached for this model. "
                    "Wait for the reset or switch to another model."
                )
            else:
                raise
    raise RuntimeError("The model is still unavailable. Please try again later.")

# ---------- The agent loop ----------
def run_agent(user_message, contents):
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
    while True:
        response = call_model(contents)
        contents.append(response.candidates[0].content)
        calls = response.function_calls
        # No tool requested -> final answer
        if not calls:
            return response.text

        # Model asked for tools: run them and send the results back
        parts = []
        for call in calls:
            print(f"[tool call] {call.name}({dict(call.args)})")
            result = TOOL_FUNCTIONS[call.name](**call.args)
            log_tool_call(call.name, dict(call.args), result)
            parts.append(types.Part.from_function_response(
                name=call.name, response={"result": result}
            ))
        contents.append(types.Content(role="user", parts=parts))

if __name__ == "__main__":
    print("IAM Helpdesk Agent (type 'quit' to exit)")
    history = []  # keeps the conversation so the agent remembers earlier messages
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue
        try:
            print("\nAgent:", run_agent(user_input, history))
        except RuntimeError as e:
            print("\n[error]", e)
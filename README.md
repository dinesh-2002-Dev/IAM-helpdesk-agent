# IAM Helpdesk AI Agent

A command-line AI agent that handles common identity and access management (IAM) helpdesk requests using LLM **function calling**. Employees describe a problem in plain English, and the agent decides which tools to call, runs them, and replies with the result.

> **Note:** This is a learning/portfolio project. All users, groups, employee IDs and tickets are **mock data**. It is not connected to any real directory or ticketing system.

## What it does

The agent can use four tools:

| Tool | Purpose |
|------|---------|
| `lookup_user` | Returns account status (e.g. locked) and MFA method |
| `check_group_membership` | Lists the access groups a user belongs to |
| `create_ticket` | Opens a support ticket with a short summary |
| `generate_temp_access_code` | Issues a temporary access code, **only after identity verification** |

## Example

```
You: I'm alice@example.com. I can't log in. Which groups am I in, and please open a ticket for me.
[tool call] check_group_membership({'email': 'alice@example.com'})
[tool call] create_ticket({'summary': 'User unable to log in', 'email': 'alice@example.com'})
[tool call] lookup_user({'email': 'alice@example.com'})

Agent: Your account is currently locked. You are in the groups All-Employees and VPN-Users.
A support ticket (INC1001) has been opened on your behalf.
```

## How it works

1. The user's message and the tool descriptions are sent to the model (Google Gemini API).
2. If the model decides a tool is needed, it replies with a tool name and arguments instead of a final answer.
3. The program runs the matching Python function and sends the result back to the model.
4. Steps 2-3 repeat until the model produces a final answer.

The conversation history is kept during a session, so the agent remembers earlier messages.

## Design decisions

- **Security checks live in code, not in the prompt.** `generate_temp_access_code` compares the supplied employee ID with the record for that email and refuses on any mismatch. A model can be talked into things, but this check cannot be argued with.
- **Audit logging.** Every tool call is appended to `audit.log` (time, tool, arguments, result). Temporary access codes are masked in the log so secrets are never written to disk.
- **Resilience.** Temporary "model busy" errors (503) are retried automatically, and quota errors (429) show a clear message instead of crashing.

## Setup

Requirements: Python 3.10+ and a free Gemini API key from [Google AI Studio](https://aistudio.google.com).

```powershell
git clone https://github.com/dinesh-2002-Dev/IAM-helpdesk-agent.git
cd IAM-helpdesk-agent
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
$env:GEMINI_API_KEY="your-key-here"
python agent.py
```

On macOS/Linux, activate with `source venv/bin/activate` and set the key with `export GEMINI_API_KEY="your-key-here"`.

Mock test accounts: `alice@example.com` (employee ID `E1001`, account locked) and `bob@example.com` (employee ID `E1002`, account active).

Model names change over time. If you get a "model not found" error, update the `MODEL` value at the top of `agent.py` to a currently available model.

## Limitations

- Mock data only; tickets and codes are stored in memory and reset when the program stops.
- Command-line interface only.
- The free Gemini tier has a small daily request limit, which restricts how much you can test per day.

## Possible improvements

- Containerize with Docker and run automated tests in GitHub Actions
- Track evaluation results for tool-call accuracy
- Move the model and secrets to a managed cloud service with managed identities

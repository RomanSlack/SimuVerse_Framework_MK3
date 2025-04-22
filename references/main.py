import os
import uvicorn
import json
import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError("Please set the OPENAI_API_KEY environment variable.")

app = FastAPI()

# In-memory session storage per agent.
sessions: Dict[str, List[Dict[str, str]]] = {}

# Simple logging system.
logs: Dict[str, List[Dict[str, Any]]] = {}
logs_file = "agent_logs.json"

def save_logs():
    with open(logs_file, "w") as f:
        json.dump(logs, f, indent=2)

def log_event(agent_id: str, event_type: str, details: Dict[str, Any]):
    if agent_id not in logs:
        logs[agent_id] = []
    logs[agent_id].append({
        "timestamp": datetime.datetime.now().isoformat(),
        "type": event_type,
        "details": details
    })
    save_logs()

# ----------------------------------------------------------------------------
# Session creation.
# Inject the system prompt (with task) only when the session is new.
# ----------------------------------------------------------------------------
def get_or_create_session(agent_id: str, system_prompt: str, task: str) -> List[Dict[str, str]]:
    if agent_id not in sessions:
        full_prompt = system_prompt
        if task.strip():
            full_prompt += "\nCurrent Task: " + task
        sessions[agent_id] = [{"role": "system", "content": full_prompt}]
    return sessions[agent_id]

# ----------------------------------------------------------------------------
# Build the LLM prompt from the conversation.
# Forwarded conversation messages (marked with "[Conversation") are grouped.
# ----------------------------------------------------------------------------
def build_prompt(conversation: List[Dict[str, str]]) -> str:
    # Identify conversation messages
    convo_msgs = [msg["content"] for msg in conversation if msg["content"].startswith("[Conversation")]
    normal_msgs = [f"{msg['role'].capitalize()}: {msg['content']}" for msg in conversation if not msg["content"].startswith("[Conversation")]
    prompt_lines = []
    
    # Check if we're in a conversation
    in_conversation = any(msg["content"].startswith("[CONVERSE mode with") for msg in conversation if msg["role"] == "user")
    
    if convo_msgs:
        prompt_lines.append("Conversation History:")
        prompt_lines.extend(convo_msgs)
    
    prompt_lines.extend(normal_msgs)
    prompt_lines.append("Assistant:")
    
    if in_conversation:
        # Modify the reminder to encourage information sharing in conversations
        prompt_lines.append("Remember: You are in a conversation. Share specific information you know that might help the other agent. "
                        "Be direct and to the point. End your answer with CONVERSE: (with no extra text).")
    else:
        prompt_lines.append("Remember: Provide at least one sentence of reasoning and end your answer with MOVE:, NOTHING:, or CONVERSE: (with no extra text).")
    
    return "\n".join(prompt_lines)

# ----------------------------------------------------------------------------
# OpenAI ChatGPT Wrapper – using the gpt-4o-mini-2024-07-18 model.
# ----------------------------------------------------------------------------
class OpenAIChatGPT:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini-2024-07-18"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model
    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": prompt}],
            temperature=1.0
        )
        return response.choices[0].message.content

# ----------------------------------------------------------------------------
# Request and Response Models.
# ----------------------------------------------------------------------------
class GenerateRequest(BaseModel):
    agent_id: str
    user_input: str
    system_prompt: str   # Full instructions (only on first request)
    task: str            # Current Task for the agent

class GenerateResponse(BaseModel):
    agent_id: str
    text: str           # Full AI response.
    action: str         # "move", "nothing", "converse", or "none"
    location: str       # For MOVE: valid location or agent name; for CONVERSE: target agent’s name.

# ----------------------------------------------------------------------------
# /generate endpoint.
# ----------------------------------------------------------------------------
@app.post("/generate", response_model=GenerateResponse)
def generate_response(data: GenerateRequest):
    # Check if this is the end of a conversation (when rounds left = 0)
    if data.user_input.startswith("[CONVERSE mode with") and "rounds left: 0]" in data.user_input:
        # Extract the agent name from the input
        target_agent = data.user_input.split("with ")[1].split(",")[0]
        
        # Log the conversation end event
        log_event(data.agent_id, "conversation_end", {
            "with_agent": target_agent,
            "message": f"Conversation with {target_agent} has ended."
        })
        
        # Also send this notification to the other agent - they should know it ended too
        # Only if the other agent exists in sessions
        if target_agent in sessions:
            log_event(target_agent, "conversation_end", {
                "with_agent": data.agent_id,
                "message": f"Conversation with {data.agent_id} has ended."
            })
    
    log_event(data.agent_id, "user_input", {
        "input": data.user_input,
        "system_prompt": data.system_prompt,
        "task": data.task
    })
    
    # Create or retrieve session. The system prompt (with task) is added only the first time.
    conversation = get_or_create_session(data.agent_id, data.system_prompt, data.task)
    conversation.append({"role": "user", "content": data.user_input})
    
    prompt = build_prompt(conversation)
    log_event(data.agent_id, "prompt_built", {"prompt": prompt})
    
    llm = OpenAIChatGPT(api_key=OPENAI_API_KEY)
    assistant_text = llm.generate(prompt)
    
    # Validate the response: at least one reasoning line and proper final command.
    lines = assistant_text.strip().split("\n")
    if len(lines) < 2:
        assistant_text = ("Your response is invalid. You must provide at least one sentence of reasoning.\n"
                          "NOTHING: do nothing")
        log_event(data.agent_id, "validation_failure", {"reason": "Not enough lines", "response": assistant_text})
    else:
        final_line = lines[-1].strip().lower()
        valid_starts = ["move:", "nothing:", "converse:"]
        if not any(final_line.startswith(x) for x in valid_starts):
            assistant_text = ("Your final line did not start with MOVE:, NOTHING:, or CONVERSE:. Invalid response.\n"
                              "NOTHING: do nothing")
            log_event(data.agent_id, "validation_failure", {"reason": "Bad final line", "response": assistant_text})
    
    conversation.append({"role": "assistant", "content": assistant_text})
    
    # Parse final command.
    action = "none"
    location = ""
    for line in assistant_text.splitlines():
        l = line.strip().lower()
        if l.startswith("move:"):
            action = "move"
            location = line.split(":", 1)[1].strip()
            break
        elif l.startswith("nothing:"):
            action = "nothing"
            break
        elif l.startswith("converse:"):
            action = "converse"
            location = line.split(":", 1)[1].strip()
            break
    
    # If CONVERSE, forward the entire assistant response (marked as conversation) to the target agent.
    if action == "converse" and location:
        get_or_create_session(location, "", "")
        
        # Extract just the actual message content (without the action line)
        message_lines = assistant_text.strip().split('\n')
        # Remove the last line (which contains CONVERSE: action)
        actual_message = '\n'.join(message_lines[:-1]).strip()
        
        # Create a more structured conversation prompt that encourages
        # sharing specific information rather than just reasoning
        if data.user_input.startswith("[CONVERSE mode with"):
            # This is a continuation of an existing conversation
            # Format that encourages direct information exchange
            fwd_text = f"[Conversation from {data.agent_id}]: {actual_message}"
        else:
            # This is the start of a new conversation
            # Let's explicitly tell them to share specific information they know
            fwd_text = f"[Conversation from {data.agent_id}]: {actual_message}\n\nWhen responding, share any specific information you have about the situation that might be helpful."
        
        sessions[location].append({"role": "user", "content": fwd_text})
        
        # Log only the actual conversation content, not reasoning or commands
        log_event(data.agent_id, "conversation_message", {
            "to": location,
            "from": data.agent_id,
            "message": actual_message,
            "timestamp": datetime.datetime.now().isoformat()
        })
    
    log_event(data.agent_id, "response", {"assistant_text": assistant_text, "action": action, "location": location})
    
    return GenerateResponse(
        agent_id=data.agent_id,
        text=assistant_text,
        action=action,
        location=location.lower()
    )

# ----------------------------------------------------------------------------
# /reset endpoint to clear sessions and logs.
# ----------------------------------------------------------------------------
@app.post("/reset")
def reset_system():
    global sessions, logs
    sessions = {}
    logs = {}
    with open(logs_file, "w") as f:
        json.dump(logs, f)
    return {"status": "ok", "message": "All sessions & logs cleared."}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=3000)

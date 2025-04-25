# Agent Priming System

The Agent Priming System is a feature that introduces agents to their roles, personalities, and tasks before the simulation begins. This gives agents context about who they are and what they're supposed to do before they start making decisions.

## How Priming Works

1. **Initial Registration**: When an agent is registered, a primer message can be sent to it immediately.

2. **Manual Priming**: All agents can be primed at once using the `/agents/prime` endpoint.

3. **Automatic Priming**: When the simulation starts (Shift+X is pressed for the first time), any unprimed agents will automatically be primed.

## The Primer Message

The primer message includes:

```
SIMULATION INITIALIZATION

You are [agent_id], an autonomous agent in a Mars colony simulation.

YOUR IDENTITY:
[personality description]

YOUR CURRENT TASK:
[task description]

YOUR LOCATION:
You are currently at [location].

INITIALIZATION INSTRUCTIONS:
1. Take a moment to understand your identity and task.
2. You'll soon receive environmental information and will be asked to make decisions.
3. For now, acknowledge this initialization and express your readiness to begin.
4. Do NOT take any actions yet - just acknowledge receipt of this information.
```

## Priming vs. Regular Simulation Cycles

- **Priming**: Happens once at the beginning, gives identity and purpose
- **Simulation Cycles**: Happen repeatedly, provide environmental updates and request decisions

## Benefits of Priming

1. **Consistent Agent Behavior**: Ensures agents understand their role from the start
2. **Reduced Confusion**: Agents know what they're supposed to do before making decisions
3. **More Realistic Interactions**: Agents can act according to their established personalities
4. **Smoother Simulation Start**: Prevents agents from being confused in their first decision cycle

## Implementation Details

- Agent sessions track whether an agent has been primed with the `is_primed` flag
- Priming only happens once per agent (unless forced with `force=true`)
- Primer responses are logged and can be reviewed in the agent logs
# Agent - LangGraph Multi-Agent System

Intelligent task decomposition and planning system using LangGraph workflow.

**Tech Stack**: LangGraph + LangChain + OpenAI GPT-4o

---

## Overview

The agent system decomposes natural language instructions into executable robot action plans through a multi-agent workflow with human-in-the-loop capability.

### Workflow

```
START
  ↓
task_analyzer ←──────────┐
  ├─ [ask clarification]  │
  │    ↓                  │
  │  human_query          │
  │    ↓──────────────────┘
  ├─ [explore scene]
  │    ↓
  │  scene_explorer ←─────┐
  │    ↓                  │
  │  scene_query          │
  │    ↓──────────────────┘
  └─ [proceed to planning]
       ↓
     task_planner ←────────┐
       ├─ [call planner]   │
       │    ↓              │
       │  pddl_plan         │
       │    ↓──────────────┘
       └─ [execute]
            ↓
          robot_executor
            ↓
           END
```

---

## Components

### Nodes

#### 1. **task_analyzer**
Analyzes user instructions and decides next action.

**Decisions:**
- `human_query` - Ask user for clarification
- `explore_scene` - Search for objects in environment
- `proceed_to_planning` - Ready for planning

**Tools:** `human_query`

**File:** `nodes/task_analyzer.py`

#### 2. **scene_explorer**
Explores the environment using ontology server tools.

**Decisions:**
- Use scene_query tools to gather information
- Return to task_analyzer when done

**Tools:** `scene_query` (semantic_search, get_object_info, filter_objects, find_path)

**File:** `nodes/scene_explorer.py`

#### 3. **task_planner**
Generates PDDL goals and validates plans.

**Decisions:**
- `call_pddl_plan` - Generate PDDL goal and call planner
- `proceed_to_execution` - Validate plan and proceed

**Tools:** `pddl_plan`

**File:** `nodes/task_planner.py`

#### 4. **robot_executor**
Simulates robot action execution.

**File:** `nodes/robot_executor.py`

### Tools

#### 1. **human_query**
Interactive clarification with user using `interrupt()`.

**Usage:**
```python
human_query(question="What color apple do you want?")
# Pauses execution, waits for user input
```

**File:** `tools/human_query.py`

#### 2. **scene_query**
Query ontology server for environment information.

**Available tools:**
- `semantic_search(query, top_k)` - Natural language search
- `get_object_info(object_ids)` - Get object details
- `filter_objects(class_name, in_space, ...)` - Filter by criteria
- `find_path(from_id, to_id)` - Find shortest path

**File:** `tools/scene_query.py`

#### 3. **pddl_plan**
Generate PDDL problem and run Fast Downward planner.

**Usage:**
```python
pddl_plan(goal_formula="(and (isON tv_52))")
# Returns: SUCCESS with plan or PLANNING FAILED with logs
```

**File:** `tools/pddl_plan.py`

---

## State Management

### OverallState

```python
class OverallState(TypedDict):
    # Core LangGraph message management
    messages: Annotated[List, add_messages]

    # User input
    user_instruction: str

    # System workflow management
    system_status: SystemStatus  # PLANNING, EXECUTING, COMPLETED, FAILED

    # Agent routing
    current_agent: Optional[str]
    next_agent: Optional[str]
    next_agent_context: Optional[str]

    # Task execution results
    execution_plan: Annotated[List[str], operator.add]
    discovered_objects: Annotated[List[Dict], operator.add]

    # Robot execution state
    execution_status: ExecutionStatus
    simulation_results: Annotated[List[Dict], operator.add]
```

**File:** `state.py`

---

## Configuration

All agents use GPT-4o with temperature 0.0 for deterministic behavior.

**File:** `config.py`

```python
class Configuration(BaseModel):
    task_analyzer_model: str = "gpt-4o"
    scene_explorer_model: str = "gpt-4o"
    task_planner_model: str = "gpt-4o"
    robot_executor_model: str = "gpt-4o"
    temperature: float = 0.0
```

---

## Prompts

Each agent has specialized system prompts with clear decision criteria.

**File:** `prompts.py`

### task_analyzer_prompt
- Explains 3 action options
- Decision criteria for each
- Examples

### scene_explorer_prompt
- Tool descriptions and usage
- Exploration workflow
- When to return

### task_planner_prompt
- PDDL goal predicates reference
- Goal formula examples
- Planning workflow

### robot_executor_prompt
- Execution simulation instructions

---

## Usage

### Running the System

```bash
# Start LangGraph dev server
langgraph dev

# Opens Studio UI at:
# https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

### Example Interaction

**Input:**
```json
{
  "user_instruction": "Turn on the TV"
}
```

**Workflow:**
1. `task_analyzer`: Needs to find TV → route to scene_explorer
2. `scene_explorer`: Use semantic_search("TV") → finds "tv_52"
3. `task_analyzer`: Ready to plan → route to task_planner
4. `task_planner`: Generate goal `(isON tv_52)` → call pddl_plan
5. `pddl_plan`: Returns 13-step plan
6. `task_planner`: Validate → route to robot_executor
7. `robot_executor`: Simulate execution

**Output:**
```json
{
  "execution_plan": [
    "move robot1 living_room_23 opening_6",
    "move robot1 opening_6 corridor_16",
    ...
    "power-on robot1 tv_52"
  ],
  "simulation_results": [...]
}
```

---

## Extending the System

### Adding a New Node

1. Create node file in `nodes/`:
```python
def my_node(state: OverallState, config: RunnableConfig) -> dict:
    # Node logic
    return {
        "messages": [...],
        "next_agent": "next_node_name"
    }
```

2. Add to workflow in `graph.py`:
```python
workflow.add_node("my_node", my_node)
workflow.add_edge("previous_node", "my_node")
```

### Adding a New Tool

1. Create tool in `tools/`:
```python
@tool
def my_tool(param: str) -> str:
    """Tool description."""
    # Tool logic
    return result
```

2. Create ToolNode in `graph.py`:
```python
workflow.add_node("my_tool_node", ToolNode([my_tool]))
```

3. Bind to agent:
```python
llm = llm.bind_tools([my_tool])
```

### Customizing Prompts

Edit prompts in `prompts.py` to change agent behavior:
- Add new decision criteria
- Include domain-specific examples
- Adjust tone and style

---

## Development

### Testing Individual Nodes

```python
from agent.nodes.task_analyzer import task_analyzer
from agent.state import OverallState

state = OverallState(
    user_instruction="Test instruction",
    messages=[]
)

result = task_analyzer(state, {})
print(result)
```

### Debugging

1. **LangGraph Studio** - Visual debugging in UI
2. **Message History** - Check `state["messages"]` for conversation flow
3. **Print Statements** - Add logging in nodes for debugging

### Common Issues

**Tool not found:**
- Verify tool is imported in `graph.py`
- Check tool name in agent's `tool_calls`

**Routing error:**
- Check routing function return type matches edge definition
- Verify `next_agent` value is valid node name

**State not updating:**
- Ensure return dict has correct keys
- Check if using `Annotated` fields correctly

---

## File Structure

```
agent/
├── nodes/
│   ├── task_analyzer.py    # Analyzes task and routes
│   ├── scene_explorer.py   # Explores environment
│   ├── task_planner.py     # Generates PDDL goals
│   └── robot_executor.py   # Executes plans
│
├── tools/
│   ├── human_query.py      # Human-in-the-loop
│   ├── scene_query.py      # Ontology server queries
│   └── pddl_plan.py        # PDDL planning
│
├── graph.py                # Workflow definition
├── state.py                # State management
├── config.py               # Configuration
├── prompts.py              # System prompts
├── main.py                 # Entry point
├── app.py                  # FastAPI app (for future frontend)
└── README.md               # This file
```

---

## Resources

- [LangGraph Documentation](https://python.langchain.com/docs/langgraph)
- [LangGraph How-tos](https://langchain-ai.github.io/langgraph/how-tos/)
- [Human-in-the-loop](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/)

---

## License

This is part of the OntoPlan project.

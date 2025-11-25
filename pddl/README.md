# PDDL - Automated Planning System

Automated PDDL problem generation from knowledge graph and optimal plan solving with Fast Downward.

**Tech Stack**: Fast Downward + Neo4j + Python

---

## Overview

The PDDL module automatically:
1. Extracts objects from PDDL goal formula
2. Queries Neo4j for object states and relationships
3. Generates complete PDDL problem file
4. Runs Fast Downward planner
5. Returns optimal action sequence

---

## Quick Start

### Prerequisites

```bash
# Install Fast Downward
git clone https://github.com/aibasel/downward.git fast-downward
cd fast-downward
./build.py
cd ..
```

### Run Planner

```bash
# Edit config.yaml with your goal
python run_pddl.py
```

---

## Configuration

### config.yaml

```yaml
# Task identification
task: "test"
domain: "robot"

# PDDL goal formula
goal: |
  (isON tv_52)

# Additional objects (optional)
additional_artifacts: []
additional_locations: []

# Planner configuration
planner:
  solver: "lazy_wastar"  # Options: lazy_wastar, astar, lama
  heuristic: "ff"        # Options: ff, hmax, cea
  weight: 2              # Weight for weighted A* (lazy_wastar only)
```

---

## PDDL Goal Predicates

### Object Location States

```lisp
; Object is in a space
(isInSpace <artifact> <location>)
; Example: (isInSpace cup_12 kitchen_5)

; Object is inside container
(isInsideOf <artifact> <container>)
; Example: (isInsideOf apple_8 fridge_20)

; Object is on top of surface
(isOntopOf <artifact> <surface>)
; Example: (isOntopOf book_3 table_15)
```

### Robot & Manipulation States

```lisp
; Robot is holding object with hand
(isHeldBy <artifact> <hand>)
; Example: (isHeldBy cup_12 left_hand)

; Robot is next to object (can manipulate)
(isAdjacentTo <robot> <artifact>)
; Example: (isAdjacentTo robot1 door_7)
```

### Object States

```lisp
; Object is powered on
(isON <artifact>)
; Example: (isON tv_25)

; Object/door is open
(isOpen <artifact>)
; Example: (isOpen cabinet_10)
```

### Combining Conditions

```lisp
; Use (and ...) for multiple conditions
(and
  (isON tv_52)
  (robotIsInSpace robot1 living_room_21)
)
```

---

## Usage Examples

### Example 1: Turn on TV

**config.yaml:**
```yaml
goal: |
  (isON tv_52)
```

**Generated Plan:**
```
move robot1 living_room_23 opening_6
move robot1 opening_6 corridor_16
move robot1 corridor_16 door_8
open-door robot1 door_8
move robot1 door_8 dining_room_18
...
move robot1 opening_9 living_room_21
access robot1 tv_52 living_room_21
power-on robot1 tv_52
; cost = 20 (13 steps)
```

### Example 2: Bring Object

**config.yaml:**
```yaml
goal: |
  (isHeldBy apple_8 left_hand)
```

### Example 3: Complex Task

**config.yaml:**
```yaml
goal: |
  (and
    (isInsideOf apple_8 refrigerator_58)
    (isOpen refrigerator_58)
    (robotIsInSpace robot1 kitchen_5)
  )
```

---

## How It Works

### 1. Goal Parsing
```python
extract_object_ids_from_goal(goal_formula, driver)
# Extracts: ["apple_8", "refrigerator_58", "kitchen_5"]
```

### 2. Type Classification
```python
classify_objects_by_domain_type(object_ids, types_map, parser)
# Artifacts: ["apple_8", "refrigerator_58"]
# Locations: ["kitchen_5"]
```

### 3. Context Expansion
- Get artifact locations from Neo4j
- Expand location graph with shortest paths
- Include robot, hands, and all required objects

### 4. PDDL Problem Generation
```python
writer.write_problem(
    problem_path,
    types_map,         # Object type definitions
    topology,          # Location connections and distances
    robot_info,        # Robot and hands
    artifact_locs,     # Object spatial states
    affordances_map,   # Object capabilities
    goal_formula       # Goal condition
)
```

### 5. Fast Downward Execution
```bash
python fast-downward.py \
  domain.pddl \
  problem/task_abc123.pddl \
  --search "lazy_wastar([ff()], w=2)"
```

---

## Domain Definition

### Types Hierarchy

```
Location
  ├─ Space (rooms, corridors)
  ├─ Door
  ├─ Stairs
  └─ Opening

Robot
Hand
Artifact (movable objects)
```

### Actions

**Movement:**
- `move` - Move between locations
- `open-door` / `close-door` - Door control

**Manipulation:**
- `access` - Approach object
- `pick-one-hand` / `pick-two-hands` - Grasp object
- `place-to-location-*` - Place on floor
- `place-in-*` - Place in container
- `place-on-*` - Place on surface

**Object Control:**
- `open` / `close` - Open/close containers
- `power-on` / `power-off` - Power control

See `domain.pddl` for complete definitions.

---

## Project Structure

```
pddl/
├── domain.pddl          # PDDL domain definition
├── config.yaml          # Task configuration
├── run_pddl.py          # Main execution script
│
├── scripts/
│   ├── pddl_parser.py      # Parse domain types
│   ├── pddl_generator.py   # Extract from Neo4j
│   ├── pddl_writer.py      # Write problem file
│   └── pddl_goal_utils.py  # Goal utilities
│
├── problem/             # Generated problems (gitignored)
├── solution/            # Generated solutions (gitignored)
└── fast-downward/       # Fast Downward planner (gitignored)
```

---

## Advanced Usage

### Custom Planner Configuration

**A* with landmark-cut heuristic:**
```yaml
planner:
  solver: "astar"
  heuristic: "lmcut"
```

**LAMA planner:**
```yaml
planner:
  solver: "lama"
```

### Adding Extra Objects

If goal doesn't reference all needed objects:

```yaml
additional_artifacts:
  - table_10    # Include table even if not in goal
  - chair_5

additional_locations:
  - hallway_3   # Include hallway for path planning
```

### Debugging

**Problem file location:**
```
pddl/problem/task_<hash>.pddl
```

**Solution file location:**
```
pddl/solution/task_<hash>.plan
```

**Check generated problem:**
```bash
cat problem/task_abc123.pddl
```

---

## Troubleshooting

**"Undefined object" error:**
- Object ID in goal doesn't exist in Neo4j
- Check ontology server has loaded the object
- Verify object ID spelling

**"No solution found":**
- Goal might be impossible given current state
- Check if objects are accessible (not blocked)
- Review domain.pddl preconditions

**Fast Downward not found:**
- Install in `fast-downward/` directory
- Run `./build.py` after cloning
- Check path in run_pddl.py (line 188)

**Neo4j connection error:**
- Verify Neo4j is running
- Check credentials match ontology_server/config.yaml
- Ensure ontology data is loaded

---

## API Usage

### From Python

```python
from pddl_plan import pddl_plan

result = pddl_plan(goal_formula="(isON tv_52)")

if "SUCCESS" in result:
    print("Plan generated!")
    print(result)
else:
    print("Planning failed:")
    print(result)
```

### From LangGraph Agent

The agent's `task_planner` node uses `pddl_plan` tool automatically:

```python
# In agent/tools/pddl_plan.py
@tool
def pddl_plan(goal_formula: str) -> str:
    # Generates problem and returns solution
    ...
```

---

## Performance Tips

1. **Minimize object scope:** Only include necessary objects in goal
2. **Use specific goals:** More specific goals = faster planning
3. **Simplify topology:** Fewer locations = faster search
4. **Choose right solver:**
   - `lazy_wastar` - Fast, good quality (default)
   - `astar` with `lmcut` - Optimal, slower
   - `lama` - Very fast, satisficing

---

## Resources

- [Fast Downward Documentation](http://www.fast-downward.org/)
- [PDDL Reference](https://planning.wiki/)
- [Search Algorithms](http://www.fast-downward.org/Doc/SearchAlgorithm)

---

## License

Part of the OntoPlan project.

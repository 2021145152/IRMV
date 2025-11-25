"""LLM Prompts for PDDL Planning System."""

scenario_generator_prompt = """You are a scenario generation agent for robot task planning using PDDL (Planning Domain Definition Language).

Your role is to analyze the environment (TTL ontology data) and generate a realistic, achievable goal formula that a robot could accomplish.

## ENVIRONMENT DATA

You will receive a summary of the environment containing:
- Available artifacts (objects) with their categories, locations, and affordances
- Available locations (spaces, rooms, doors)
- Robot capabilities

## PDDL GOAL PREDICATES

Based on the PDDL domain, you can use these predicates for goal formulas:

**Object Location States:**
- `(isInSpace <artifact> <location>)` - Object is located in a space
  Example: (isInSpace cup_12 kitchen_5)

- `(isInsideOf <artifact> <container>)` - Object is inside a container
  Example: (isInsideOf apple_8 fridge_20)

- `(isOntopOf <artifact> <surface>)` - Object is on top of another object
  Example: (isOntopOf book_3 table_15)

**Robot & Manipulation States:**
- `(isHeldBy <artifact> <hand>)` - Object is held by robot's hand
  Example: (isHeldBy cup_12 left_hand)

- `(robotIsInSpace <robot> <location>)` - Robot is in a location
  Example: (robotIsInSpace robot1 kitchen_5)

- `(isAdjacentTo <robot> <artifact>)` - Robot is next to an object (can manipulate)
  Example: (isAdjacentTo robot1 door_7)

**Object States:**
- `(isON <artifact>)` - Object is powered on
  Example: (isON tv_25)

- `(isOpen <artifact>)` - Object is open (for containers/doors)
  Example: (isOpen cabinet_10)

- `(isOpenDoor <door>)` - Door is open
  Example: (isOpenDoor door_7)

## GOAL FORMULA FORMAT

Use `(and ...)` to combine multiple conditions:
```
(and
  (isInSpace cup_12 kitchen_5)
  (isOntopOf cup_12 table_15)
)
```

Simple single predicate goals:
```
(isON tv_25)
```

## YOUR TASK

1. **Analyze the environment data** to understand:
   - What artifacts exist and where they are
   - What affordances artifacts have (what actions are possible)
   - What locations are available
   - Spatial relationships between objects and locations

2. **Generate a COMPLEX, REALISTIC scenario** that:
   - Uses actual object IDs from the environment
   - Is achievable given the artifacts' affordances and locations
   - Represents a meaningful multi-step task requiring several actions
   - Combines multiple conditions using `(and ...)` or `(or ...)`

3. **Create complex goal formulas** that typically include:
   - **Object state changes**: (isON ...), (isOpen ...), (isHeldBy ...)
   - **Spatial relationships**: (isInSpace ...), (isInsideOf ...), (isOntopOf ...)
   - **Robot positioning**: (robotIsInSpace ...), (isAdjacentTo ...)
   - **Multiple conditions**: Use `(and ...)` to combine 3-5 different conditions

4. **Output ONLY the PDDL goal formula** in this format:
   - No explanations, no markdown
   - Just the PDDL expression with multiple conditions

## TASK DIVERSITY EXAMPLES

Generate DIVERSE robot task scenarios. You can create tasks of varying complexity:

**Simple Tasks (5 conditions) - ALLOWED:**
- `(and (isHeldBy apple_8 left_hand) (robotIsInSpace robot1 kitchen_13) (isOpen refrigerator_9) (isON tv_52) (isAdjacentTo robot1 tv_52))`
  - Robot picks up apple, moves to kitchen, opens fridge, turns on TV, positions (5 conditions)

- `(and (isInSpace cake_1 kitchen_13) (isOntopOf cake_1 table_15) (robotIsInSpace robot1 kitchen_13) (isOpen door_10) (isON oven_2))`
  - Robot moves cake to kitchen, places on table, opens door, turns on oven (5 conditions)

**Medium Tasks (7 conditions) - RECOMMENDED:**
- `(and (isHeldBy book_12 left_hand) (robotIsInSpace robot1 bedroom_5) (isOntopOf book_12 bed_39) (isOpen door_10) (isON tv_52) (isAdjacentTo robot1 tv_52) (isOpen window_5))`
  - Robot picks up book, moves to bedroom, places on bed, opens door, turns on TV, positions, opens window (7 conditions)

- `(and (isHeldBy cup_12 left_hand) (robotIsInSpace robot1 kitchen_13) (isInsideOf cup_12 refrigerator_9) (isOpen refrigerator_9) (isON oven_2) (isOpen oven_2) (isAdjacentTo robot1 oven_2))`
  - Robot picks up cup, moves to kitchen, places in fridge, opens fridge, turns on oven, opens oven, positions (7 conditions)

**Complex Tasks (9 conditions) - OPTIONAL:**
- `(and (isHeldBy book_12 left_hand) (robotIsInSpace robot1 bedroom_5) (isOntopOf book_12 bed_39) (isOpen door_10) (isON tv_52) (isAdjacentTo robot1 tv_52) (isOpen window_5) (isHeldBy cup_12 right_hand) (isInSpace cup_12 kitchen_13))`
  - Robot picks up book, moves to bedroom, places on bed, opens door, turns on TV, positions, opens window, picks up cup, moves cup to kitchen (9 conditions)

**Specialized Tasks - ENCOURAGED:**
- Key-Safe operations: `(and (isLocked safe_121) (isInsideOf apple_202 safe_121))` - Lock safe with object inside
- Container operations: `(and (isOpen refrigerator_9) (isInsideOf apple_8 refrigerator_9))` - Open container and place object
- Multi-object: `(and (isHeldBy cup_12 left_hand) (isHeldBy bottle_11 right_hand))` - Hold multiple objects

**Invalid goals (avoid):**
- `(isInSpace tv_44 bedroom_5)` - TV doesn't have Pickup affordance (can't be moved)
- `(isON cup_12)` - Cup doesn't have Power affordance
- Goals using objects that don't exist in the environment

## LOGICAL CONSISTENCY REQUIREMENTS

**CRITICAL: Avoid logical contradictions!**

### 1. Mutually Exclusive Predicates for Same Object

**CRITICAL: Each artifact can have ONLY ONE state predicate at a time!**

For the SAME artifact, the following predicates are **MUTUALLY EXCLUSIVE** (cannot be used together):
- `(isHeldBy <artifact> <hand>)` is EXCLUSIVE with:
  - `(isInSpace <artifact> <location>)` - Cannot be in a space if held
  - `(isInsideOf <artifact> <container>)` - Cannot be inside container if held
  - `(isOntopOf <artifact> <surface>)` - Cannot be on top if held

- `(isInSpace <artifact> <location>)` is EXCLUSIVE with:
  - `(isInsideOf <artifact> <container>)` - Cannot be in a space AND inside container
  - `(isOntopOf <artifact> <surface>)` - Cannot be in a space AND on top of surface
  - `(isHeldBy <artifact> <hand>)` - Cannot be in a space if held

- `(isInsideOf <artifact> <container>)` is EXCLUSIVE with:
  - `(isInSpace <artifact> <location>)` - Cannot be inside container AND in a space
  - `(isOntopOf <artifact> <surface>)` - Cannot be inside container AND on top of surface
  - `(isHeldBy <artifact> <hand>)` - Cannot be inside container if held

- `(isOntopOf <artifact> <surface>)` is EXCLUSIVE with:
  - `(isInSpace <artifact> <location>)` - Cannot be on top AND in a space
  - `(isInsideOf <artifact> <container>)` - Cannot be on top AND inside container
  - `(isHeldBy <artifact> <hand>)` - Cannot be on top if held

**Rule: Each artifact ID should appear in ONLY ONE of these predicates: isHeldBy, isInSpace, isInsideOf, isOntopOf**

**Valid combinations (different artifacts):**
- `(and (isHeldBy cup_12 left_hand) (robotIsInSpace robot1 kitchen_13))` ✓
  - Different objects: cup_12 held + robot location
  
- `(and (isOpen refrigerator_9) (isInsideOf apple_8 refrigerator_9))` ✓
  - Different objects: refrigerator_9 open + apple_8 inside

**Valid combinations (same artifact, compatible predicates):**
- `(and (isON tv_52) (isOpen tv_52))` ✓
  - Same artifact, but isON and isOpen are compatible (TV can be on and open)
  
- `(and (isHeldBy apple_8 left_hand) (isON apple_8))` ✓
  - Same artifact, but isHeldBy and isON are compatible (can hold powered-on object)

**Invalid combinations (SAME artifact, mutually exclusive):**
- `(and (isHeldBy cup_12 left_hand) (isInSpace cup_12 kitchen_13))` ✗
  - SAME artifact cup_12: Cannot be held AND in a space simultaneously
  
- `(and (isHeldBy bottle_11 left_hand) (isInsideOf bottle_11 refrigerator_9))` ✗
  - SAME artifact bottle_11: Cannot be held AND inside container simultaneously

- `(and (isInSpace apple_8 kitchen_13) (isInsideOf apple_8 refrigerator_9))` ✗
  - SAME artifact apple_8: Cannot be in a space AND inside container simultaneously

- `(and (isInSpace book_12 bedroom_5) (isOntopOf book_12 bed_39))` ✗
  - SAME artifact book_12: Cannot be in a space AND on top of surface simultaneously

**CRITICAL RULE: When generating goal formulas, ensure each artifact ID appears in EXACTLY ONE spatial/manipulation predicate (isHeldBy, isInSpace, isInsideOf, isOntopOf). NEVER use the same artifact ID in multiple state predicates. Use DIFFERENT artifacts for different predicates to avoid logical contradictions.**

**Example of CORRECT goal (different artifacts):**
- `(and (isHeldBy apple_1 left_hand) (isInSpace apple_2 kitchen_1) (isInsideOf apple_3 refrigerator_1))` ✓
  - Different artifacts: apple_1 held, apple_2 in space, apple_3 in container

**Example of INCORRECT goal (same artifact):**
- `(and (isHeldBy apple_1 left_hand) (isInSpace apple_1 kitchen_1) (isInsideOf apple_1 refrigerator_1))` ✗
  - SAME artifact apple_1 in multiple predicates - THIS WILL CAUSE VALIDATION ERROR

### 2. Robot Location Contradictions

**CRITICAL: Robot can only be in ONE location at a time!**

- `(robotIsInSpace robot1 <location1>)` and `(robotIsInSpace robot1 <location2>)` are **MUTUALLY EXCLUSIVE**
- The robot **CANNOT** be in two different locations simultaneously

**Invalid combinations (DO NOT USE):**
- `(and (robotIsInSpace robot1 kitchen_13) (robotIsInSpace robot1 dining_room_11))` ✗
  - Robot cannot be in two spaces at once
  
- `(and (robotIsInSpace robot1 bedroom_5) (robotIsInSpace robot1 living_room_14))` ✗
  - Robot cannot be in two spaces at once

**Valid usage:**
- `(and (robotIsInSpace robot1 kitchen_13) (isON oven_2) (isOpen refrigerator_9))` ✓
  - Robot in one location + other conditions (different objects/predicates)
  
- `(and (robotIsInSpace robot1 kitchen_13) (isAdjacentTo robot1 oven_2))` ✓
  - Robot in one location + adjacent to object in same location (compatible)

**Note:** If you need the robot to visit multiple locations, use sequential goals or intermediate states, NOT simultaneous location requirements.

## OBJECT AVAILABILITY REQUIREMENTS

**CRITICAL: Only use objects with known initial locations!**

Before using an artifact in `(isHeldBy ...)`, `(isInSpace ...)`, or `(isInsideOf ...)`, **MUST verify**:
- The artifact has a location specified in the environment data (e.g., "in kitchen_13")
- Objects without location information (location: None) **CANNOT be picked up or moved**

**Valid usage:**
- If artifact shows "in kitchen_13" → Can use in goal formula ✓
- If artifact shows "in bedroom_5" → Can use in goal formula ✓

**Invalid usage:**
- If artifact has NO location (location: None or missing) → **DO NOT use in (isHeldBy ...)** ✗
- If artifact location is unknown → **DO NOT use in spatial predicates** ✗

**Example check:**
- Environment shows: `bottle_11 (bottle) in kitchen_13 [affords: ...]` → Can use ✓
- Environment shows: `bottle_11 (bottle) [affords: ...]` (no location) → **DO NOT use** ✗

## AFFORDANCE REQUIREMENTS FOR SPATIAL PREDICATES

**CRITICAL: Check affordances for container operations!**

**For `(isInsideOf <artifact> <container>)`:**
- The **container** MUST have `Affordance_PlaceIn` affordance
- The artifact can have `Affordance_PlaceIn` but it's the container that matters
- Example: `(isInsideOf apple_8 refrigerator_9)` requires `refrigerator_9` to have `Affordance_PlaceIn`

**For `(isOntopOf <artifact> <surface>)`:**
- The **surface** MUST have `Affordance_PlaceOn` affordance
- Example: `(isOntopOf book_3 table_15)` requires `table_15` to have `Affordance_PlaceOn`

**Valid examples:**
- Container has `Affordance_PlaceIn`: `refrigerator_9 [affords: Affordance_PlaceIn, ...]` → Can use in `(isInsideOf ...)` ✓
- Surface has `Affordance_PlaceOn`: `table_15 [affords: Affordance_PlaceOn, ...]` → Can use in `(isOntopOf ...)` ✓

**Invalid examples:**
- Container lacks `Affordance_PlaceIn`: `refrigerator_9 [affords: Affordance_Open, Affordance_PickupTwoHands]` → **DO NOT use in `(isInsideOf ...)`** ✗
- Surface lacks `Affordance_PlaceOn`: `bed_39 [affords: Affordance_Sit, ...]` → **DO NOT use in `(isOntopOf ...)`** ✗ (unless it has PlaceOn)

## REQUIREMENTS

- **VARY task complexity**: Generate simple (5 conditions), medium (7 conditions), and complex (9 conditions) tasks for diversity
- **VARY task types**: Include manipulation (pick/place), navigation (robot movement), control (power/open), and key-safe operations
- **MUST use `(and ...)` to combine multiple conditions** (for tasks with 2+ conditions)
- **MUST use actual object IDs from the environment data provided**
- **MUST verify objects have known initial locations** before using in spatial/manipulation predicates
- **MUST check container affordances** for `(isInsideOf ...)` and `(isOntopOf ...)` predicates
- **MUST ensure all conditions are achievable** (check affordances AND initial locations AND container affordances)
- **MUST ensure logical consistency** (no mutually exclusive predicates for same object, no multiple robot locations)
- **MUST ensure containers are open** when placing objects inside (isOpen required for isInsideOf)
- **MUST create realistic and achievable task scenarios**
- **DO NOT use objects that don't exist in the environment**
- **DO NOT use objects without known initial locations** in `(isHeldBy ...)`, `(isInSpace ...)`, `(isInsideOf ...)`
- **DO NOT combine mutually exclusive predicates for the same artifact**
- **DO NOT require robot to be in multiple locations simultaneously** (e.g., `(and (robotIsInSpace robot1 kitchen_13) (robotIsInSpace robot1 dining_room_11))`)
- **DO NOT place objects inside closed containers** (container must be open: `(isOpen container_id)`)

Remember: Generate DIVERSE, LOGICALLY CONSISTENT, and ACHIEVABLE scenarios. Vary complexity and task types. Check object locations and affordances before using them. Only output the PDDL goal formula, nothing else.
"""

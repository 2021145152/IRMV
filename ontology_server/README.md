# Robot Ontology Server

Real-time ontology management system with automated reasoning, knowledge graph storage, and PDDL planning integration.

**Tech Stack**: FastAPI + owlready2 + HermiT reasoner + Neo4j + Fast Downward

## Features

✅ Real-time OWL ontology management with automatic reasoning
✅ TTL-based instance loading (static topology + dynamic objects)
✅ Neo4j knowledge graph synchronization
✅ Semantic search with OpenAI embeddings
✅ SPARQL & Cypher query support
✅ Automated PDDL problem generation from Neo4j
✅ REST API with automatic documentation

---

## Quick Start

### Prerequisites

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Fast Downward (for PDDL planning)
cd ../pddl  # From ontology_server directory
git clone https://github.com/aibasel/downward.git fast-downward
cd fast-downward
./build.py
cd ../../ontology_server  # Return to ontology_server

# Start Neo4j (Docker)
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest
```

### Setup Environment

Create `.env` file:

```env
OPENAI_API_KEY=your_api_key_here
```

Copy and edit `config.yaml`:

```bash
cp config.example.yaml config.yaml
```

Edit the following in `config.yaml`:

```yaml
neo4j:
  uri: "bolt://localhost:7687"
  user: "neo4j"
  password: "your_password_here"

embedding:
  model: "text-embedding-3-small"  # Recommended for most use cases
  # dimensions: 512  # Optional - defaults to recommended value per model

active_env: "Darden"
```

### Start Server & Load Data

**Option 1: One-step startup (Recommended)**
```bash
./start.sh
```

This will automatically:
1. Start the ontology server
2. Load static data (buildings, rooms, connections)
3. Load dynamic data (furniture, artifacts, robot)

**Option 2: Manual step-by-step**
```bash
# 1. Start server (in separate terminal)
python cli/run_server.py

# 2. Load static topology
python cli/load_static.py

# 3. Load dynamic objects
python cli/load_dynamic.py
```

Server runs at http://localhost:8000 (API docs at http://localhost:8000/docs)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              OntologyManager (FastAPI)                   │
│                http://localhost:8000                     │
├─────────────────────────────────────────────────────────┤
│ • Load TTL instances from file                           │
│ • Add/update/delete individuals via API                  │
│ • Run HermiT reasoner for inference                      │
│ • Sync to Neo4j knowledge graph                          │
│ • Generate embeddings for semantic search               │
└─────────────────────────────────────────────────────────┘
                          ↓
        ┌─────────────────┴─────────────────┐
        ↓                                     ↓
┌───────────────┐                    ┌──────────────┐
│   owlready2   │                    │    Neo4j     │
│  + HermiT     │                    │  Graph DB    │
├───────────────┤                    ├──────────────┤
│ • OWL schema  │                    │ • Individuals│
│ • Individuals │                    │ • Properties │
│ • Inference   │                    │ • Hierarchy  │
│ • Validation  │                    │ • Embeddings │
└───────────────┘                    └──────────────┘
```

---

## Project Structure

```
ontology_server/
├── cli/                          # Command-line tools
│   ├── run_server.py            # Start FastAPI server
│   ├── load_static.py           # Load static TTL instances
│   ├── load_dynamic.py          # Load dynamic TTL instances
│   └── query_tools.py           # Graph query tools CLI (for testing)
│
├── core/                         # Core ontology management
│   ├── ontology.py              # OntologyManager (main logic)
│   ├── api.py                   # FastAPI routes
│   ├── models.py                # Pydantic models
│   ├── config.py                # Configuration loader
│   ├── env.py                   # Environment manager
│   └── embedding.py             # OpenAI embedding integration
│
├── tools/                        # Graph query tools for LLM integration
│   ├── graph_tools.py           # GraphTools: get_object_info, filter_objects, find_path
│   ├── semantic_tool.py         # SemanticTool: semantic_search
│   ├── queries/                 # Cypher query files
│   │   ├── get_object_info.cypher
│   │   └── find_path.cypher
│   └── config.yaml              # Query tool test configuration
│
├── data/
│   ├── robot.owx                # OWL ontology schema
│   └── envs/                    # Environment data
│       └── Darden/
│           ├── static.ttl      # Static topology (rooms, doors, etc.)
│           └── dynamic.ttl     # Dynamic objects (furniture, robot, etc.)
│
├── start.sh                      # One-step startup script
├── config.yaml                   # Main configuration
├── config.example.yaml           # Configuration template
├── requirements.txt
├── .env                         # Environment variables (gitignored)
└── README.md
```

---

## Usage

### 1. REST API

The server provides a REST API for ontology management:

```python
import requests

BASE_URL = "http://localhost:8000"

# Add individual
response = requests.post(f"{BASE_URL}/individuals", json={
    "id": "new_chair",
    "class": "Chair",
    "data_properties": {"x": 1.5, "y": 2.3},
    "object_properties": {"objectIsInSpace": "living_room"}
})

# Update individual
response = requests.put(f"{BASE_URL}/individuals/new_chair", json={
    "data_properties": {"x": 2.0, "y": 3.0}
})

# Delete individual
response = requests.delete(f"{BASE_URL}/individuals/new_chair")

# Get status
status = requests.get(f"{BASE_URL}/status").json()
print(f"Total individuals: {status['total_individuals']}")
```

**API Endpoints:**
- `POST /individuals` - Add new individual
- `PUT /individuals/{id}` - Update individual
- `DELETE /individuals/{id}` - Delete individual
- `POST /load_ttl` - Load instances from TTL file
- `POST /sync` - Manually trigger reasoning + Neo4j sync
- `GET /status` - Get ontology status

Interactive API docs: http://localhost:8000/docs

### 2. TTL Instance Files

Instances are stored in Turtle (TTL) format:

**Static Topology** (`static.ttl`):
```turtle
@prefix : <http://www.semanticweb.org/ontologies/robot#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

:living_room rdf:type :Room ;
    :x "0.0"^^xsd:float ;
    :y "0.0"^^xsd:float ;
    :roomIsInStorey :floor_1 .

:door_1 rdf:type :Door ;
    :x "5.0"^^xsd:float ;
    :y "0.0"^^xsd:float ;
    :isOpenDoor "true"^^xsd:boolean ;
    :isDoorOf :living_room ;
    :isDoorOf :kitchen .
```

**Dynamic Objects** (`dynamic.ttl`):
```turtle
:chair_1 rdf:type :Artifact ;
    rdfs:comment "Comfortable armchair" ;
    :x "1.5"^^xsd:float ;
    :y "2.3"^^xsd:float ;
    :objectIsInSpace :living_room ;
    :affords :Affordance_Sit ;
    :affords :Affordance_PlaceOn .

:robot1 rdf:type :Robot ;
    rdfs:comment "Main service robot" ;
    :robotIsInSpace :living_room ;
    :hasHand :left_hand ;
    :hasHand :right_hand .
```

### 3. Graph Query Tools

Query the knowledge graph using specialized tools (designed for LLM integration):

```bash
# Edit tools/config.yaml to configure queries, then run:
python cli/query_tools.py

# Or specify a tool directly:
python cli/query_tools.py get_object_info    # Get detailed object information
python cli/query_tools.py filter_objects     # Filter objects by criteria
python cli/query_tools.py find_path          # Find shortest path
python cli/query_tools.py semantic_search    # Natural language search
```

**Available Tools:**

1. **get_object_info** - Get complete information about object(s)
2. **filter_objects** - Filter by class, relationships, and data properties
3. **find_path** - Find shortest path between locations using Dijkstra
4. **semantic_search** - Search using natural language queries

Edit `tools/config.yaml` to test different queries. See `tools/graph_tools.py` and `tools/semantic_tool.py` for Python API usage.

### 4. PDDL Planning

Automatically generate PDDL problem from Neo4j and solve:

```bash
# From ontology_server directory
cd ../pddl  # Navigate to pddl directory

# Generate problem + solve with Fast Downward
python run_pddl.py

# The script will:
# 1. Parse domain types from domain.pddl
# 2. Extract objects/predicates from Neo4j based on goal (defined in config.yaml)
# 3. Generate PDDL problem file
# 4. Run Fast Downward planner
# 5. Display solution steps
```

**PDDL Configuration** (`../pddl/config.yaml`):
```yaml
task: "test"
domain: "robot"

goal: |
  (isON tv_52)

planner:
  solver: "lazy_wastar"
  heuristic: "ff"
  weight: 2
```

Note: PDDL module has been moved to project root (`../pddl` from ontology_server).
See [../pddl/README.md](../pddl/README.md) for detailed PDDL documentation.

---

## Neo4j Visualization

Open http://localhost:7474 to explore the knowledge graph.

**Useful Queries:**

```cypher
// Show spatial hierarchy
MATCH (b:Building)-[:hasDoor|hasOpening|hasStairs*1..3]->(conn)-[:isDoorOf|isOpeningOf|isStairsOf*1..3]->(space:Space)
RETURN b, conn, space

// Find objects in a specific room
MATCH (obj:Individual)-[:objectIsInSpace]->(room:Room {id: 'living_room'})
RETURN obj.id, obj.comment

// Show robot and its hands
MATCH (robot:Robot)-[:hasHand]->(hand:Hand)
RETURN robot, hand

// Find all chairs with sitting affordance
MATCH (chair:Artifact)-[:affords]->(aff:Affordance)
WHERE aff.id = 'Affordance_Sit'
RETURN chair.id, chair.comment
```

---

## Development

### Running Tests

```bash
# Test full system
./start.sh

# Test graph query tools
python cli/query_tools.py get_object_info
python cli/query_tools.py semantic_search

# Test PDDL generation
cd pddl && python run_pddl.py "robot at door_1" "test goal"
```

### Adding New Environments

1. Create new environment folder:
```bash
mkdir -p data/envs/MyEnvironment
```

2. Create `static.ttl` with building topology
3. Create `dynamic.ttl` with objects
4. Update `config.yaml`:
```yaml
active_env: "MyEnvironment"

environments:
  MyEnvironment:
    name: "MyEnvironment"
    description: "Description of the environment"
```

5. Load instances:
```bash
python cli/load_static.py
python cli/load_dynamic.py
```

---

## Dependencies

Core:
- `owlready2>=0.46` - OWL ontology management
- `fastapi>=0.104.0` - REST API framework
- `uvicorn>=0.24.0` - ASGI server
- `neo4j>=5.0.0` - Neo4j Python driver
- `pydantic>=2.0.0` - Data validation

Optional:
- `openai>=1.0.0` - Semantic search embeddings
- `numpy>=1.24.0` - Vector operations

Install all:
```bash
pip install -r requirements.txt
```

---

## License

This project is part of the Robot Ontology Demo system.

---

## Troubleshooting

**Neo4j connection error:**
- Check if Neo4j is running: `docker ps`
- Verify credentials in `config.yaml`

**Fast Downward not found:**
- Install in `pddl/fast-downward/` directory
- Follow installation instructions at https://github.com/aibasel/downward

**OpenAI API error:**
- Set `OPENAI_API_KEY` in `.env` file
- Check API quota at https://platform.openai.com/

**Reasoner timeout:**
- Large ontologies may take time to reason
- Consider splitting static/dynamic instances
- Adjust reasoner settings in `core/ontology.py`

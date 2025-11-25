# OntoPlan - World Update System

PDDL 액션 계획을 처리하고 온톨로지 TTL 파일을 증분 업데이트하는 자동화된 월드 상태 업데이트 시스템입니다.

**기술 스택**: LangGraph + owlready2 + Neo4j + Fast Downward + OpenAI

---

## 개요

이 시스템은 PDDL 액션 계획을 읽고 각 액션을 순차적으로 실행하여 다음을 통해 월드 상태를 업데이트합니다:
- TTL 파일의 증분 버전 생성 (dynamic_N.ttl, static_N.ttl)
- SPARQL UPDATE 쿼리를 통한 온톨로지 업데이트
- 각 액션의 실행 세부사항 로깅

### 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                  LangGraph World Update Agent                    │
│                      (langgraph dev)                             │
├─────────────────────────────────────────────────────────────────┤
│  plan_reader → next_action → world_update → (continue/end)      │
│       ↓              ↓              ↓                           │
│  계획 읽기      액션 추출      TTL 업데이트                      │
│  TTL_0 생성                      온톨로지 업데이트             │
│                                  실행 로깅                       │
└─────────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────────────┐
        │   Ontology Server         │
        │   (FastAPI)               │
        ├───────────────────────────┤
        │ • OWL Ontology            │
        │ • Neo4j Graph DB          │
        │ • SPARQL UPDATE           │
        │ • TTL File Management     │
        └───────────────────────────┘
```

---

## 빠른 시작

### 사전 요구사항

1. **Python 3.11+** (conda 사용 권장)
2. **Neo4j** (Docker 사용 권장)
3. **OpenAI API Key**
4. **PDDL 계획 파일** (`action/plan/solution.plan` 위치)

### 설치

```bash
# 저장소 클론
cd world_update_debug

# conda 환경 생성
conda create -n ontplan python=3.11
conda activate ontplan

# 의존성 설치
pip install -r requirements.txt
pip install -e .

# Neo4j 시작
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:latest
```

### 설정 구성

```bash
# 환경 변수 템플릿 복사 (존재하는 경우)
cp .env.example .env

# .env 파일에 API 키 입력
# OPENAI_API_KEY=sk-...
```

`ontology_server/config.yaml` 파일 복사 및 업데이트:
```bash
cp ontology_server/config.example.yaml ontology_server/config.yaml
# config.yaml 파일에 Neo4j 비밀번호 입력
```

```yaml
neo4j:
  uri: "bolt://127.0.0.1:7687"
  user: "neo4j"
  password: "your_password"

embedding:
  generate: false  # 빠른 시작을 위해 캐시된 임베딩 사용
  category:
    model: "text-embedding-3-small"
    dimensions: 256
  description:
    model: "text-embedding-3-small"
    dimensions: 512

active_env: "Darden_2"  # 활성 환경 이름
```

### PDDL 계획 준비

PDDL 계획 파일을 다음 위치에 배치하세요:
```
action/plan/solution.plan
```

계획 파일 형식 예시:
```
(move robot1 corridor_14 door_9)
(open door_9)
(move robot1 door_9 kitchen_12)
...
; cost = 8
```

### 초기 데이터 로드

```bash
cd ontology_server

# 온톨로지 서버 시작 및 데이터 로드
./start.sh

# 자동으로 수행되는 작업:
# 1. FastAPI 서버 시작 (http://localhost:8000)
# 2. 정적 토폴로지 로드 (건물, 방, 문)
# 3. 동적 객체 로드 (가구, 로봇)
# 4. 임베딩과 함께 Neo4j에 동기화
```

### World Update Agent 실행

```bash
# 프로젝트 루트에서
langgraph dev

# LangGraph Studio가 다음 주소에서 열립니다:
# https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

에이전트는 다음을 수행합니다:
1. `action/plan/solution.plan` 파일 읽기
2. 초기 TTL 파일 생성 (`action/world/dynamic_0.ttl`, `static_0.ttl`)
3. 각 액션을 순차적으로 처리
4. 각 액션에 대한 증분 TTL 버전 생성
5. 실행 세부사항을 `action/log/N.json`에 로깅

---

## 프로젝트 모듈

### 1. Agent (`/agent`)

PDDL 계획을 처리하고 환경 상태를 업데이트하는 LangGraph 기반 월드 업데이트 시스템입니다.

**워크플로우:**
```
START → plan_reader → next_action → world_update → (continue/end)
        ↓              ↓              ↓
    계획 읽기      액션 추출      TTL 업데이트
    TTL_0 생성                   온톨로지 업데이트
                                  실행 로깅
```

**주요 기능:**
- `action/plan/solution.plan`에서 PDDL 계획 읽기
- 초기 TTL 파일 생성 (버전 0)
- 액션 순차 처리
- 증분 TTL 파일 버전 관리 (dynamic_N.ttl, static_N.ttl)
- SPARQL UPDATE를 통한 온톨로지 업데이트
- `action/log/N.json`에 실행 로깅

**노드:**
- `plan_reader`: PDDL 계획 읽기 및 파싱, 초기 TTL 파일 생성
- `next_action`: 남은 액션에서 다음 액션 추출
- `world_update`: 액션 기반으로 TTL 파일 및 온톨로지 업데이트

자세한 내용은 [agent/README.md](agent/README.md)를 참조하세요.

### 2. Ontology Server (`/ontology_server`)

지식 그래프 저장소를 사용한 실시간 온톨로지 관리 시스템입니다.

**주요 기능:**
- 자동 추론을 지원하는 OWL 온톨로지 (HermiT)
- Neo4j 지식 그래프 동기화
- OpenAI 임베딩을 사용한 의미론적 검색
- 그래프 쿼리 도구 (get_object_info, filter_objects, find_path)
- 온톨로지 관리를 위한 REST API

**엔드포인트:**
- http://localhost:8000 - API 서버
- http://localhost:8000/docs - 대화형 API 문서
- http://localhost:7474 - Neo4j 브라우저

자세한 내용은 [ontology_server/README.md](ontology_server/README.md)를 참조하세요.

### 3. PDDL Planner (`/pddl`)

자동화된 PDDL 문제 생성 및 계획 시스템입니다.

**주요 기능:**
- 목표에 기반하여 Neo4j에서 계획 객체 추출
- PDDL 문제 파일 자동 생성
- Fast Downward 플래너 통합
- 최적 액션 시퀀스 반환

**사용법:**
```bash
cd pddl
python run_pddl.py
# config.yaml에서 목표를 읽고, 문제를 생성하며, Fast Downward로 해결
```

자세한 내용은 [pddl/README.md](pddl/README.md)를 참조하세요.

---

## 사용 예제

### 전체 워크플로우

```bash
# 1. PDDL 계획 파일 준비
# action/plan/solution.plan 파일 내용:
(move robot1 corridor_14 door_9)
(open door_9)
(move robot1 door_9 kitchen_12)
(pick-one-hand robot1 left_hand apple_8)
; cost = 4

# 2. 에이전트 실행
langgraph dev

# 3. 에이전트 워크플로우
plan_reader:
  - solution.plan 파일 읽기
  - 4개 액션 파싱
  - action/world/dynamic_0.ttl 생성 (ontology_server에서 복사)
  - action/world/static_0.ttl 생성 (ontology_server에서 복사)

next_action:
  - 첫 번째 액션 추출: "(move robot1 corridor_14 door_9)"
  - current_action으로 설정
  - remaining_actions 업데이트: [action2, action3, action4]

world_update:
  - move 액션 파싱 (robot1, corridor_14 → door_9)
  - 온톨로지 업데이트: robotIsInSpace(robot1, door_9)
  - action/world/dynamic_1.ttl 생성 (증분 업데이트)
  - action/world/static_1.ttl 생성 (증분 업데이트)
  - action/log/1.json에 로깅
  - "continue" 반환

next_action → world_update (각 액션마다 반복)

# 4. 출력 결과
최종 상태:
- action/world/dynamic_0.ttl (초기)
- action/world/dynamic_1.ttl (액션 1 후)
- action/world/dynamic_2.ttl (액션 2 후)
- action/world/dynamic_3.ttl (액션 3 후)
- action/world/dynamic_4.ttl (액션 4 후)
- action/log/1.json, 2.json, 3.json, 4.json (실행 로그)
```

---

## 프로젝트 구조

```
world_update_debug/
├── agent/                    # LangGraph 월드 업데이트 에이전트
│   ├── nodes/               # 에이전트 노드
│   │   ├── plan_reader.py   # PDDL 계획 읽기, 초기 TTL 생성
│   │   ├── next_action.py   # 계획에서 다음 액션 추출
│   │   └── world_update.py  # TTL 파일 및 온톨로지 업데이트
│   ├── tools/               # 도구
│   │   ├── pddl_plan.py     # PDDL 계획 도구
│   │   └── ttl_reader.py    # TTL 파일 읽기 도구
│   ├── graph.py             # 워크플로우 정의
│   ├── state.py             # 상태 관리
│   └── README.md
│
├── action/                   # 액션 실행 데이터
│   ├── plan/
│   │   └── solution.plan    # 입력 PDDL 계획 파일
│   ├── world/               # 생성된 TTL 버전 (gitignored)
│   │   ├── dynamic_0.ttl   # 초기 동적 상태
│   │   ├── dynamic_1.ttl   # 액션 1 후
│   │   └── ...
│   └── log/                 # 실행 로그 (gitignored)
│       ├── 1.json           # 액션 1 로그
│       └── ...
│
├── ontology_server/          # 온톨로지 관리 시스템
│   ├── core/                # 온톨로지 매니저, API, 모델
│   ├── tools/               # 그래프 쿼리 도구
│   ├── cli/                 # 명령줄 도구
│   ├── data/                # OWL 온톨로지 및 TTL 인스턴스
│   │   └── envs/            # 환경별 데이터
│   │       └── Darden_2/    # 활성 환경
│   │           ├── static.ttl
│   │           └── dynamic.ttl
│   ├── start.sh             # 원스텝 시작 스크립트
│   └── README.md
│
├── pddl/                     # PDDL 계획 시스템
│   ├── scripts/             # PDDL 생성 스크립트
│   ├── domain.pddl          # PDDL 도메인 정의
│   ├── run_pddl.py          # 문제 생성 + 해결
│   └── README.md
│
├── langgraph.json           # LangGraph 설정
├── setup.py                 # 패키지 설정
├── requirements.txt         # Python 의존성
└── README.md                # 이 파일
```

---

## 개발

### 개별 모듈 테스트

**Ontology Server:**
```bash
cd ontology_server
python cli/run_server.py
python cli/query_tools.py semantic_search
```

**PDDL Planner:**
```bash
cd pddl
python run_pddl.py
```

**World Update Agent:**
```bash
# action/plan/solution.plan 파일이 존재하는지 확인
langgraph dev
# Studio UI를 사용하여 워크플로우 테스트
```

### 새 기능 추가

**새 액션 타입:**
1. `agent/nodes/world_update.py`에 액션 파서 추가
2. 액션에 대한 TTL 업데이트 로직 추가
3. 필요한 경우 SPARQL UPDATE 쿼리 추가

**새 노드:**
1. `agent/nodes/`에 노드 생성
2. `agent/graph.py`의 워크플로우에 추가
3. 라우팅 로직 업데이트

**새 도구:**
1. `agent/tools/`에 도구 생성
2. 필요한 경우 그래프에 ToolNode 추가
3. 적절한 에이전트에 도구 바인딩

**새 환경:**
1. `ontology_server/data/envs/<env_name>/`에 TTL 파일 생성
2. `ontology_server/config.yaml`에서 `active_env` 업데이트
3. `load_static.py`와 `load_dynamic.py`로 로드

---

## 의존성

핵심:
- `langgraph>=1.0.3` - 다중 에이전트 워크플로우
- `langchain>=1.0.7` - LLM 통합
- `owlready2>=0.48` - OWL 온톨로지
- `neo4j>=6.0.0` - 지식 그래프
- `fastapi>=0.121.0` - REST API
- `openai>=2.0.0` - LLM 및 임베딩

전체 목록은 `requirements.txt`를 참조하세요.

---

## 문제 해결

**LangGraph dev 실패:**
- 포트 2024가 사용 가능한지 확인
- `.env` 파일에 `OPENAI_API_KEY`가 있는지 확인

**계획 파일을 찾을 수 없음:**
- `action/plan/solution.plan` 파일이 존재하는지 확인
- 파일 경로가 올바른지 확인

**Neo4j 연결 오류:**
- Neo4j가 실행 중인지 확인: `docker ps`
- `ontology_server/config.yaml`의 자격 증명 확인

**TTL 파일 생성 실패:**
- 원본 TTL 파일이 `ontology_server/data/envs/<active_env>/`에 존재하는지 확인
- `ontology_server/config.yaml`의 `active_env`가 환경 이름과 일치하는지 확인
- `action/world/` 디렉토리가 쓰기 가능한지 확인

**온톨로지 서버 오류:**
- Neo4j가 실행 중인지 확인
- OWL 파일이 `ontology_server/data/robot.owx`에 존재하는지 확인
- 온톨로지 서버가 포트 8000에서 실행 중인지 확인

**월드 업데이트 실패:**
- 액션 형식이 예상된 PDDL 구문과 일치하는지 확인
- 로봇 및 위치 ID가 온톨로지에 존재하는지 확인
- `action/log/`의 실행 로그에서 자세한 오류 메시지 확인

---

## 라이선스

이 프로젝트는 Robot Ontology Demo 시스템의 일부입니다.

---

## 인용

연구에서 이 시스템을 사용하는 경우 다음을 인용해 주세요:

```
@software{ontplan2025,
  title={OntoPlan: Ontology-based Robot Task Planning System},
  year={2025},
  author={...}
}
```

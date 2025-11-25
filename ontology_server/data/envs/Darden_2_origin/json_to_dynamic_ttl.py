# dynamic_json_to_ttl.py
import json
from pathlib import Path
from typing import List, Set


PREFIXES = """@prefix : <http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

"""

BIG_OBJECT_CLASSES = {
    "couch", "sofa", "bed", "table", "dining table", "refrigerator",
    "bench", "desk", "wardrobe", "cabinet"
}


def safe_iri(text: str) -> str:
    return text.strip().replace(" ", "_")


def escape_literal(text: str) -> str:
    return text.replace('"', '\\"')


def map_affordances(actions: List[str], cls: str) -> Set[str]:
    """
    action_affordance 리스트 + class 이름을
    Affordance_{Sit, Eat, Open, PickupOneHand, PickupTwoHands, Power, PlaceIn, PlaceOn}
    로 매핑.
    """
    affordances: Set[str] = set()
    lower_actions = [a.lower() for a in actions]
    cls_lower = cls.lower()

    # Sit
    if any(k in a for a in lower_actions for k in ["sit on", "lay on"]):
        affordances.add(":Affordance_Sit")

    # Eat
    if any("eat" in a or "drink" in a for a in lower_actions):
        affordances.add(":Affordance_Eat")

    # Open / Close
    if any("open" in a or "close" in a for a in lower_actions):
        affordances.add(":Affordance_Open")

    # Power
    if any(k in a for a in lower_actions for k in ["turn on", "turn off", "heat", "cook", "defrost", "power"]):
        affordances.add(":Affordance_Power")

    # PlaceIn (컨테이너)
    if (
        any(k in a for a in lower_actions for k in ["fill", "put in", "store", "empty", "pour in", "prepare"])
        or cls_lower in ["bowl", "cup", "sink", "handbag", "suitcase", "vase", "box"]
    ):
        affordances.add(":Affordance_PlaceIn")

    # PlaceOn (표면)
    if (
        any(k in a for a in lower_actions for k in ["set on", "step on", "tidy"])
        or any(k in a for a in lower_actions for k in ["sit on", "lay on"])
        or cls_lower in ["table", "counter", "bench", "chair", "couch", "sofa", "bed"]
    ):
        affordances.add(":Affordance_PlaceOn")

    # Pickup (한손/두손)
    pickup_related = any(
        k in a
        for a in lower_actions
        for k in ["pick up", "grab", "hold", "carry", "wear", "move"]
    )
    if pickup_related:
        if cls_lower in BIG_OBJECT_CLASSES:
            affordances.add(":Affordance_PickupTwoHands")
        else:
            affordances.add(":Affordance_PickupOneHand")

    return affordances


def build_dynamic_ttl(data: dict) -> str:
    """
    JSON → Artifact + 위치 + affordance만 포함한 dynamic TTL 문자열 생성.
    :affords가 여러 개면 줄바꿈해서 여러 줄로 출력.
    """
    output = data["output"]
    building = output["building"]
    rooms = output["room"]
    objects = output["object"]

    building_name = building["name"]

    lines = [PREFIXES]
    
    # ---------- Ontology Declaration ----------
    ontology_iri = "<http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10>"
    lines.append(
        f"{ontology_iri} rdf:type owl:Ontology ;\n"
        f"    owl:imports <../../robot.owx> .\n\n"
    )

    # room_id → space IRI 매핑 (static 쪽과 동일 규칙)
    room_iri_map = {}
    for room_id_str, room in rooms.items():
        room_id = int(room_id_str)
        category_raw = room.get("scene_category", "room")
        category_iri_part = safe_iri(category_raw)
        room_iri = f":{category_iri_part}_{room_id}"
        room_iri_map[room_id] = room_iri

    # Artifact들
    for obj_id_str, obj in sorted(objects.items(), key=lambda kv: int(kv[0])):
        obj_id = int(obj_id_str)
        cls = obj.get("class_", "object")
        actions = obj.get("action_affordance", []) or []
        parent_room = obj.get("parent_room")

        # IRI: :{class_}_{id} (예: :bicycle_1, :bench_19)
        obj_iri = f":{safe_iri(cls)}_{obj_id}"

        # description 간단히 생성
        desc_parts = [f"A {cls}"]
        mat = obj.get("material")
        if mat:
            desc_parts.append(f"made of {mat}")
        t_tex = obj.get("tactile_texture")
        if t_tex:
            desc_parts.append(f"tactile texture: {t_tex}")
        v_tex = obj.get("visual_texture")
        if v_tex:
            desc_parts.append(f"visual texture: {v_tex}")

        room_iri = room_iri_map.get(parent_room)
        if room_iri:
            desc_parts.append(f"in {room_iri.lstrip(':')}")

        desc = ", ".join(desc_parts)

        lines.append(
            f"{obj_iri} rdf:type :Artifact ;\n"
            f"    :category \"{escape_literal(cls)}\" ;\n"
            f"    :description \"{escape_literal(desc)}\" ;\n"
        )

        # 위치
        if room_iri:
            lines.append(f"    :objectIsInSpace {room_iri} ;\n")

        # affordance
        affordances = map_affordances(actions, cls)
        has_open_affordance = ":Affordance_Open" in affordances
        
        # Check for key-safe relationships
        requires_key_id = obj.get("requires_key")
        unlocks_id = obj.get("unlocks")
        
        # Build list of properties to add (in order)
        properties = []
        
        # Add affordances
        if affordances:
            aff_sorted = sorted(affordances)
            for aff in aff_sorted:
                properties.append(f"    :affords {aff}")
        
        # Add requiresKey relationship (safe -> key)
        if requires_key_id is not None:
            key_iri = f":{safe_iri('key')}_{requires_key_id}"
            properties.append(f"    :requiresKey {key_iri}")
        
        # Add unlocks relationship (key -> safe)
        if unlocks_id is not None:
            safe_iri_str = f":{safe_iri('safe')}_{unlocks_id}"
            properties.append(f"    :unlocks {safe_iri_str}")
        
        # Add isOpen if has Affordance_Open
        if has_open_affordance:
            properties.append(f"    :isOpen \"false\"^^xsd:boolean")
        
        # Write properties with semicolons (except last one uses period)
        if properties:
            for i, prop in enumerate(properties):
                if i < len(properties) - 1:
                    lines.append(f"{prop} ;\n")
                else:
                    lines.append(f"{prop} .\n")
            lines.append("\n")
        else:
            # No properties to add, close the object definition
            if lines[-1].strip().endswith(";"):
                lines[-1] = lines[-1].rsplit(";", 1)[0] + " .\n\n"
            else:
                lines.append("    .\n\n")

    # ---------- Robot and Hands ----------
    # Find first corridor or suitable space for robot initial location
    robot_location = None
    for room_id_str, room in sorted(rooms.items(), key=lambda kv: int(kv[0])):
        room_id = int(room_id_str)
        category_raw = room.get("scene_category", "room")
        if category_raw.lower() in ["corridor", "hallway", "lobby"]:
            category_iri_part = safe_iri(category_raw)
            robot_location = f":{category_iri_part}_{room_id}"
            break
    
    # If no corridor found, use first room
    if not robot_location:
        first_room_id = min(int(rid) for rid in rooms.keys())
        first_room = rooms[str(first_room_id)]
        category_raw = first_room.get("scene_category", "room")
        category_iri_part = safe_iri(category_raw)
        robot_location = f":{category_iri_part}_{first_room_id}"
    
    # Add Hand definitions
    lines.append(":left_hand rdf:type :Hand .\n\n")
    lines.append(":right_hand rdf:type :Hand .\n\n")
    
    # Add Robot definition
    lines.append(
        f":robot1 rdf:type :Robot ;\n"
        f"    :description \"Main service robot in {building_name} building\" ;\n"
        f"    :robotIsInSpace {robot_location} ;\n"
        f"    :hasHand :left_hand ;\n"
        f"    :hasHand :right_hand .\n"
    )

    return "".join(lines)


def process_json_file(json_path: Path) -> None:
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    ttl_str = build_dynamic_ttl(data)

    # Output file name: dynamic.ttl
    out_path = json_path.with_name("dynamic.ttl")
    out_path.write_text(ttl_str, encoding="utf-8")
    print(f"[OK] dynamic TTL saved to {out_path}")


def main():
    # 파이썬 파일이 있는 디렉토리 찾기
    script_dir = Path(__file__).parent
    
    # 같은 디렉토리에서 모든 JSON 파일 찾기
    json_files = list(script_dir.glob("*.json"))
    
    if not json_files:
        print(f"❌ No JSON files found in {script_dir}")
        return
    
    # 모든 JSON 파일 처리
    for json_path in sorted(json_files):
        print(f"\n📂 Processing: {json_path.name}")
        try:
            process_json_file(json_path)
        except Exception as e:
            print(f"❌ Error processing {json_path.name}: {e}")
            continue
    
    print(f"\n✅ Completed processing {len(json_files)} JSON file(s)")


if __name__ == "__main__":
    main()

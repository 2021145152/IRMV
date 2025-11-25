# static_json_to_ttl.py
import json
import argparse
import random
from pathlib import Path


PREFIXES = """@prefix : <http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

"""


def safe_iri(text: str) -> str:
    """공백 등 간단히 처리해서 Turtle IRI 로컬 이름으로 사용."""
    return text.strip().replace(" ", "_")


def escape_literal(text: str) -> str:
    return text.replace('"', '\\"')


def build_static_ttl(data: dict) -> str:
    """
    JSON (…with_connections_interactive.json)을 받아서
    Building / Storey / Space / Door / Opening 을 포함한 static TTL 문자열 생성.
    Door에는 무작위로 isOpenDoor true/false를 추가.
    """
    output = data["output"]
    building = output["building"]
    rooms = output["room"]
    connections = output.get("connections", {})

    building_name = building["name"]            # 예: "German"
    building_iri = f":{safe_iri(building_name)}"

    lines = [PREFIXES]
    
    # ---------- Ontology Declaration ----------
    ontology_iri = "<http://www.semanticweb.org/namh_woo/ontologies/2025/9/untitled-ontology-10>"
    lines.append(
        f"{ontology_iri} rdf:type owl:Ontology ;\n"
        f"    owl:imports <../../robot.owx> .\n\n"
    )

    # ---------- Building ----------
    lines.append(f"{building_iri} rdf:type :Building .\n\n")

    # ---------- Storey (Floor) ----------
    floor_numbers = sorted({str(r["floor_number"]) for r in rooms.values()})
    floor_map = {}

    for floor in floor_numbers:
        floor_iri = f":Floor_{safe_iri(floor)}"
        floor_map[floor] = floor_iri
        lines.append(
            f"{floor_iri} rdf:type :Storey ;\n"
            f"    :storeyIsInBuilding {building_iri} .\n\n"
        )

    # ---------- Space (Room) ----------
    room_iri_map = {}
    for room_id_str, room in sorted(rooms.items(), key=lambda kv: int(kv[0])):
        room_id = int(room_id_str)
        category_raw = room.get("scene_category", "room")
        category_iri_part = safe_iri(category_raw)
        room_iri = f":{category_iri_part}_{room_id}"
        room_iri_map[room_id] = room_iri

        floor = str(room.get("floor_number", "A"))
        floor_iri = floor_map.get(floor)

        desc = f"Room {room_id} ({category_raw}) in building {building_name}"
        lines.append(
            f"{room_iri} rdf:type :Space ;\n"
            f"    :category \"{escape_literal(category_raw)}\" ;\n"
            f"    :description \"{escape_literal(desc)}\" ;\n"
        )
        if floor_iri:
            lines.append(f"    :spaceIsInStorey {floor_iri} .\n\n")
        else:
            lines[-1] = lines[-1].rstrip(";\n") + " .\n\n"

    # ---------- Portal (Door / Opening) ----------
    for conn_key, conn in sorted(
        connections.items(),
        key=lambda kv: int(kv[0].split("_")[1])
    ):
        idx = int(conn_key.split("_")[1])
        ctype = conn.get("type", "")
        connected_rooms = conn.get("connected_rooms", [])

        # 연결된 방 IRI들
        space_iris = []
        for room_id in connected_rooms:
            ri = room_iri_map.get(room_id)
            if ri:
                space_iris.append(ri)

        if ctype == "Door":
            door_iri = f":door_{idx}"
            lines.append(f"{door_iri} rdf:type :Door ;\n")
            # 무작위로 true / false
            open_val = "true" if random.choice([True, False]) else "false"

            if space_iris:
                # isOpenDoor 먼저
                lines.append(
                    f"    :isOpenDoor \"{open_val}\"^^xsd:boolean ;\n"
                )
                # 연결된 Space
                for i, s in enumerate(space_iris):
                    sep = " ;" if i < len(space_iris) - 1 else " ."
                    lines.append(f"    :isDoorOf {s}{sep}\n")
            else:
                # 연결된 방이 없으면 isOpenDoor만
                lines.append(
                    f"    :isOpenDoor \"{open_val}\"^^xsd:boolean .\n"
                )

            lines.append("\n")

        elif ctype == "Opening":
            opening_iri = f":opening_{idx}"
            lines.append(f"{opening_iri} rdf:type :Opening ;\n")
            for i, s in enumerate(space_iris):
                sep = " ;" if i < len(space_iris) - 1 else " ."
                lines.append(f"    :isOpeningOf {s}{sep}\n")
            lines.append("\n")

        elif ctype == "Stairs":
            stairs_iri = f":stairs_{idx}"
            lines.append(f"{stairs_iri} rdf:type :Stairs ;\n")

            for i, s in enumerate(space_iris):
                sep = " ;" if i < len(space_iris) - 1 else " ."
                lines.append(f"    :isStairsOf {s}{sep}\n")

            lines.append("\n")

        else:
            # 나중에 Stairs 같은 타입 추가 가능
            continue

    return "".join(lines)


def process_json_file(json_path: Path) -> None:
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    ttl_str = build_static_ttl(data)

    # Output file name: static.ttl
    out_path = json_path.with_name("static.ttl")
    out_path.write_text(ttl_str, encoding="utf-8")
    print(f"[OK] static TTL saved to {out_path}")


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

#!/usr/bin/env python3
"""
각 방에 객체를 임의로 생성하는 스크립트

JSON 파일을 읽어서 각 방에 객체를 생성하고 JSON 파일을 업데이트합니다.
merged_objects_template.json을 사용하여 객체의 모든 속성을 가져옵니다.
unique_scene_categories.json의 모든 방 카테고리를 지원하며,
merged_objects_with_affordance.json의 모든 95개 객체를 적절한 방에 분류합니다.

객체 생성은 두 가지 타입으로 나뉩니다:
1. 매칭된 객체: ROOM_OBJECT_MAPPING에서 방 카테고리에 맞는 객체
2. 랜덤 객체: 모든 템플릿에서 랜덤 선택

각 타입의 개수는 독립적으로 설정할 수 있습니다.
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional


# ============================================================================
# 객체 생성 설정 (하드코딩된 값)
# ============================================================================
RECOMMENDED_ITEM_NUM = 3 # 추천 객체 개수 (방 카테고리에 맞는 객체)
RANDOM_ITEM_NUM = 2       # 랜덤 객체 개수 (모든 템플릿에서 랜덤 선택)
# ============================================================================


# 방 카테고리별 추천 객체 목록
# unique_scene_categories.json의 모든 방 카테고리를 포함합니다.
# merged_objects_with_affordance.json의 모든 95개 객체를 적절한 방에 분류했습니다.
ROOM_OBJECT_MAPPING = {
    "bedroom": [
        "bed", "pillow", "lamp", "wardrobe", "desk", "chair", "book", "phone",
        "laptop", "clock", "picture", "teddy bear", "backpack", "umbrella", "key", "safe", "cell phone"
    ],
    "bathroom": [
        "toilet", "sink", "towel", "soap", "mirror", "shower", "toothbrush",
        "cabinet", "drawer", "vase", "hair drier"
    ],
    "bathrrom": [  # 오타 정규화 (bathroom의 오타)
        "toilet", "sink", "towel", "soap", "mirror", "shower", "toothbrush",
        "cabinet", "drawer", "vase", "hair drier"
    ],
    "kitchen": [
        "refrigerator", "stove", "sink", "table", "chair", "cup", "bowl", "knife", "spoon", "plate",
        "microwave", "oven", "cabinet", "drawer", "fork", "bottle", "wine glass", "toaster", "scissors",
        "apple", "banana", "broccoli", "cabbage", "carrot", "cucumber", "lettuce", "onion",
        "orange", "pepper", "potato", "strawberry", "tomato", "watermelon", "cake", "donut", "sandwich"
    ],
    "living_room": [
        "couch", "sofa", "table", "tv", "lamp", "book", "remote", "pillow",
        "chair", "picture", "plant", "potted plant", "vase", "clock", "umbrella", "grape"
    ],
    "living_rooom": [  # 오타 정규화 (living_room의 오타)
        "couch", "sofa", "table", "tv", "lamp", "book", "remote", "pillow",
        "chair", "picture", "plant", "potted plant", "vase", "clock", "umbrella", "grape"
    ],
    "liviing_room": [  # 오타 정규화 (living_room의 오타)
        "couch", "sofa", "table", "tv", "lamp", "book", "remote", "pillow",
        "chair", "picture", "plant", "potted plant", "vase", "clock", "umbrella", "grape"
    ],
    "living-room": [  # 오타 정규화 (living_room의 오타)
        "couch", "sofa", "table", "tv", "lamp", "book", "remote", "pillow",
        "chair", "picture", "plant", "potted plant", "vase", "clock", "umbrella", "grape"
    ],
    "lving_room": [  # 오타 정규화 (living_room의 오타)
        "couch", "sofa", "table", "tv", "lamp", "book", "remote", "pillow",
        "chair", "picture", "plant", "potted plant", "vase", "clock", "umbrella", "grape"
    ],
    "dining_room": [
        "table", "chair", "plate", "cup", "bowl", "spoon", "fork", "knife",
        "dining table", "wine glass", "bottle", "vase", "picture", "lamp"
    ],
    "home_office": [
        "desk", "chair", "computer", "lamp", "book", "phone",
        "laptop", "clock", "picture", "plant", "potted plant", "cabinet", "drawer", "keyboard", "mouse",
        "cell phone", "scissors"
    ],
    "corridor": [
        "lamp", "plant", "picture", "bench", "vase", "umbrella"
    ],
    "coriidor": [  # 오타 정규화 (corridor의 오타)
        "lamp", "plant", "picture", "bench", "vase", "umbrella"
    ],
    "lobby": [
        "chair", "table", "lamp", "plant", "bench", "picture", "vase", "clock"
    ],
    "reception": [
        "chair", "table", "lamp", "plant", "bench", "picture", "vase", "clock", "desk", "phone", "cell phone"
    ],
    "staircase": [
        "lamp", "handrail", "picture"
    ],
    "staricase": [  # 오타 정규화 (staircase의 오타)
        "lamp", "handrail", "picture"
    ],
    "closet": [
        "hanger", "box", "suitcase", "backpack", "wardrobe", "cabinet", "drawer", "tie", "handbag"
    ],
    "storage_room": [
        "box", "suitcase", "cabinet", "drawer", "broom", "dustpan", "hammer", "saw",
        "bicycle", "motorcycle", "sports ball", "umbrella", "skateboard", "surfboard", "skis"
    ],
    "storage": [  # storage_room과 동일
        "box", "suitcase", "cabinet", "drawer", "broom", "dustpan", "hammer", "saw",
        "bicycle", "motorcycle", "sports ball", "umbrella", "skateboard", "surfboard", "skis"
    ],
    "utility_room": [
        "box", "suitcase", "cabinet", "drawer", "broom", "dustpan", "hammer", "saw",
        "bicycle", "motorcycle", "sports ball", "umbrella", "sink", "skateboard", "surfboard", "skis"
    ],
    "childs_room": [
        "bed", "pillow", "lamp", "wardrobe", "desk", "chair", "book", "phone",
        "laptop", "clock", "picture", "teddy bear", "backpack", "umbrella", "sports ball",
        "frisbee", "kite", "baseball bat", "baseball glove", "toy"
    ],
    "playroom": [
        "sports ball", "frisbee", "kite", "baseball bat", "baseball glove", "skateboard",
        "teddy bear", "toy", "bench", "chair", "table"
    ],
    "exercise_room": [
        "sports ball", "towel", "bottle", "mirror", "bench", "plant", "picture", "skis"
    ],
    "garage": [
        "bicycle", "motorcycle", "broom", "dustpan", "hammer", "saw", "car", "skateboard", "surfboard", "boat"
    ],
    "garagge": [  # 오타 정규화 (garage의 오타)
        "bicycle", "motorcycle", "broom", "dustpan", "hammer", "saw", "car", "skateboard", "surfboard", "boat"
    ],
    "pantry": [
        "cabinet", "drawer", "box", "bottle", "apple", "banana", "orange", "potato", "onion"
    ],
    "pantry_room": [  # pantry와 동일
        "cabinet", "drawer", "box", "bottle", "apple", "banana", "orange", "potato", "onion"
    ],
    "basement": [
        "box", "suitcase", "cabinet", "drawer", "broom", "dustpan", "hammer", "saw",
        "bicycle", "motorcycle", "sports ball", "umbrella", "boat"
    ],
    "elevator": [
        "lamp", "picture"
    ],
    "empty_room": [
        "box", "suitcase", "cabinet", "drawer"
    ],
    "sauna": [
        "towel", "bench", "bottle"
    ],
    "shower": [
        "towel", "soap", "shower", "mirror"
    ],
    "television_room": [
        "tv", "couch", "sofa", "chair", "remote", "lamp", "picture", "table"
    ],
    "televisiion_room": [  # 오타 정규화 (television_room의 오타)
        "tv", "couch", "sofa", "chair", "remote", "lamp", "picture", "table"
    ],
    "toolshed": [
        "hammer", "saw", "broom", "dustpan", "box", "cabinet", "drawer", "scissors"
    ],
    "unknown": []
}

# 전역 템플릿 딕셔너리 (로드 후 사용)
OBJECT_TEMPLATES: Dict[str, Dict] = {}


def load_object_templates(templates_path: Optional[Path] = None) -> Dict[str, Dict]:
    """
    merged_objects_template.json 파일을 로드
    
    Args:
        templates_path: 템플릿 파일 경로 (None이면 자동으로 찾기)
    
    Returns:
        템플릿 딕셔너리
    """
    global OBJECT_TEMPLATES
    
    if OBJECT_TEMPLATES:
        return OBJECT_TEMPLATES
    
    if templates_path is None:
        # 스크립트 디렉토리에서 merged_objects_template.json 찾기
        script_dir = Path(__file__).parent
        templates_path = script_dir / "merged_objects_template.json"
        
        # 없으면 상위 디렉토리에서 찾기
        if not templates_path.exists():
            templates_path = script_dir.parent / "merged_objects_template.json"
    
    if not templates_path.exists():
        raise FileNotFoundError(f"Template file not found: {templates_path}")
    
    print(f"📋 Loading object templates from: {templates_path}")
    with templates_path.open("r", encoding="utf-8") as f:
        OBJECT_TEMPLATES = json.load(f)
    
    print(f"✅ Loaded {len(OBJECT_TEMPLATES)} object templates")
    return OBJECT_TEMPLATES


def get_object_template(obj_class: str) -> Optional[Dict]:
    """
    객체 클래스에 대한 템플릿 반환
    
    Args:
        obj_class: 객체 클래스 이름
    
    Returns:
        템플릿 딕셔너리 또는 None
    """
    if not OBJECT_TEMPLATES:
        load_object_templates()
    
    # 대소문자 구분 없이 검색
    obj_class_lower = obj_class.lower()
    if obj_class_lower in OBJECT_TEMPLATES:
        return OBJECT_TEMPLATES[obj_class_lower]
    
    # 정확한 매칭이 없으면 대소문자 무시하고 찾기
    for key, value in OBJECT_TEMPLATES.items():
        if key.lower() == obj_class_lower:
            return value
    
    return None


def get_default_size(obj_class: str) -> List[float]:
    """객체 클래스에 대한 기본 크기 반환 (템플릿에서)"""
    template = get_object_template(obj_class)
    if template and "size" in template:
        return template["size"].copy()
    return [0.3, 0.3, 0.3]


def get_default_affordances(obj_class: str) -> List[str]:
    """객체 클래스에 대한 기본 affordance 반환 (템플릿에서)"""
    template = get_object_template(obj_class)
    if template and "action_affordance" in template:
        return template["action_affordance"].copy()
    return ["pick up"]


def generate_object_location(room_location: List[float], room_size: List[float], 
                             obj_size: List[float], floor_z: float) -> List[float]:
    """
    방 내에서 객체의 위치를 생성
    
    Args:
        room_location: 방의 중심 위치 [x, y, z]
        room_size: 방의 크기 [width, depth, height]
        obj_size: 객체의 크기 [width, depth, height]
        floor_z: 바닥 Z 좌표
    
    Returns:
        객체의 위치 [x, y, z]
    """
    room_w, room_d, room_h = room_size
    obj_w, obj_d, obj_h = obj_size
    
    # 방의 경계 내에서 랜덤 위치 생성 (객체 크기 고려)
    margin = 0.2  # 벽과의 최소 거리
    x_min = room_location[0] - room_w/2 + obj_w/2 + margin
    x_max = room_location[0] + room_w/2 - obj_w/2 - margin
    y_min = room_location[1] - room_d/2 + obj_d/2 + margin
    y_max = room_location[1] + room_d/2 - obj_d/2 - margin
    
    # 범위가 유효한지 확인
    if x_max < x_min:
        x = room_location[0]
    else:
        x = random.uniform(x_min, x_max)
    
    if y_max < y_min:
        y = room_location[1]
    else:
        y = random.uniform(y_min, y_max)
    
    # Z 좌표는 바닥 + 객체 높이의 절반
    z = floor_z + obj_h / 2
    
    return [x, y, z]


def create_object_from_template(obj_class: str, obj_id: int, room_id: int, 
                                 room_location: List[float], room_size: List[float], 
                                 floor_z: float) -> Optional[Dict]:
    """
    템플릿을 사용하여 객체 데이터 생성
    
    Args:
        obj_class: 객체 클래스 이름
        obj_id: 객체 ID
        room_id: 방 ID
        room_location: 방 위치
        room_size: 방 크기
        floor_z: 바닥 Z 좌표
    
    Returns:
        객체 데이터 딕셔너리 또는 None
    """
    # 템플릿 가져오기
    template = get_object_template(obj_class)
    if not template:
        return None
    
    # 객체 크기 (템플릿에서 가져오고 약간의 랜덤 변형 추가)
    obj_size = template.get("size", [0.3, 0.3, 0.3]).copy()
    obj_size = [s * random.uniform(0.9, 1.1) for s in obj_size]
    
    # 객체 위치 생성
    obj_location = generate_object_location(room_location, room_size, obj_size, floor_z)
    
    # floor_area와 volume 계산
    floor_area = obj_size[0] * obj_size[1]
    volume = obj_size[0] * obj_size[1] * obj_size[2]
    surface_coverage = template.get("surface_coverage", floor_area)
    
    # 객체 데이터 생성 (템플릿 기반)
    obj_data = {
        "id": obj_id,
        "class_": obj_class,
        "location": obj_location,
        "size": obj_size,
        "parent_room": room_id,
        "action_affordance": template.get("action_affordance", ["pick up"]).copy(),
        "material": template.get("material", None),
        "tactile_texture": template.get("tactile_texture", None),
        "visual_texture": template.get("visual_texture", None),
        "floor_area": floor_area,
        "volume": volume,
        "surface_coverage": surface_coverage
    }
    
    # 추가 속성들 (템플릿에 있는 경우)
    if "is_open" in template:
        obj_data["is_open"] = template["is_open"]
    if "is_locked" in template:
        obj_data["is_locked"] = template["is_locked"]
    if "requires_key" in template:
        obj_data["requires_key"] = template["requires_key"]
    if "unlocks" in template:
        obj_data["unlocks"] = template["unlocks"]
    if "is_on" in template:
        obj_data["is_on"] = template["is_on"]
    
    return obj_data


def generate_objects_for_room(room_id: int, room_data: Dict, existing_objects: Dict,
                              recommended_item_num: int,
                              random_item_num: int) -> List[Dict]:
    """
    특정 방에 대한 객체들을 생성 (템플릿 기반)
    1. 추천 객체: ROOM_OBJECT_MAPPING에서 방 카테고리에 맞는 객체
    2. 랜덤 객체: 모든 템플릿에서 랜덤 선택
    
    Args:
        room_id: 방 ID
        room_data: 방 데이터
        existing_objects: 기존 객체 딕셔너리 (ID 충돌 방지용)
        recommended_item_num: 추천 객체 개수 (방 카테고리에 맞는 객체)
        random_item_num: 랜덤 객체 개수 (모든 템플릿에서 랜덤 선택)
    
    Returns:
        생성된 객체 딕셔너리 리스트
    """
    scene_category = room_data.get("scene_category", "unknown").lower()
    
    # 템플릿이 로드되었는지 확인
    if not OBJECT_TEMPLATES:
        load_object_templates()
    
    # 방 카테고리에 맞는 객체 목록 가져오기 (추천 객체용)
    recommended_objects = ROOM_OBJECT_MAPPING.get(scene_category, ROOM_OBJECT_MAPPING["unknown"])
    recommended_objects = [obj for obj in recommended_objects if get_object_template(obj) is not None]
    
    # 모든 템플릿 객체 목록 가져오기 (랜덤 객체용)
    all_template_objects = list(OBJECT_TEMPLATES.keys())
    
    # 기존 객체 ID 중 최대값 찾기
    max_existing_id = 0
    if existing_objects:
        for obj_id_str in existing_objects.keys():
            try:
                obj_id = int(obj_id_str)
                max_existing_id = max(max_existing_id, obj_id)
            except (ValueError, TypeError):
                pass
    
    # 생성할 객체 개수 (명시적으로 지정)
    num_recommended = recommended_item_num if recommended_objects else 0
    num_random = random_item_num if all_template_objects else 0
    
    generated_objects = []
    room_location = room_data.get("location", [0, 0, 0])
    room_size = room_data.get("size", [1, 1, 1])
    
    # 바닥 Z 좌표 계산 (방 위치의 Z - 방 높이/2)
    floor_z = room_location[2] - room_size[2] / 2
    
    obj_counter = 0
    
    # 1. 추천 객체 생성
    if recommended_objects and num_recommended > 0:
        for i in range(num_recommended):
            obj_class = random.choice(recommended_objects)
            obj_id = max_existing_id + obj_counter + 1
            
            obj_data = create_object_from_template(
                obj_class, obj_id, room_id, room_location, room_size, floor_z
            )
            
            if obj_data:
                generated_objects.append((str(obj_id), obj_data))
                obj_counter += 1
            else:
                print(f"  ⚠️  Template not found for: {obj_class}, skipping...")
    
    # 2. 랜덤 객체 생성
    if all_template_objects and num_random > 0:
        for i in range(num_random):
            obj_class = random.choice(all_template_objects)
            obj_id = max_existing_id + obj_counter + 1
            
            obj_data = create_object_from_template(
                obj_class, obj_id, room_id, room_location, room_size, floor_z
            )
            
            if obj_data:
                generated_objects.append((str(obj_id), obj_data))
                obj_counter += 1
            else:
                print(f"  ⚠️  Template not found for: {obj_class}, skipping...")
    
    # 3. 금고-열쇠 연결 로직
    # 생성된 객체 중 safe나 key가 있는지 확인
    safes = []
    keys = []
    for obj_id_str, obj_data in generated_objects:
        obj_class = obj_data.get("class_", "").lower()
        if obj_class == "safe":
            safes.append((obj_id_str, obj_data))
        elif obj_class == "key":
            keys.append((obj_id_str, obj_data))
    
    # safe가 생성되었는데 대응하는 key가 없으면 key 생성
    for safe_id_str, safe_data in safes:
        # 이미 연결된 key가 있는지 확인 (같은 방의 생성된 key 중 unlocks가 None인 것)
        connected_key = None
        for key_id_str, key_data in keys:
            if key_data.get("unlocks") is None:
                connected_key = (key_id_str, key_data)
                break
        
        if connected_key:
            # 기존 key와 연결
            key_id_str, key_data = connected_key
            key_data["unlocks"] = int(safe_id_str)
            # safe의 requires_key와 is_locked 설정
            safe_data["requires_key"] = int(key_id_str)  # key ID 매핑
            safe_data["is_locked"] = True
            print(f"  🔗 Connected key (ID: {key_id_str}) to safe (ID: {safe_id_str})")
        else:
            # 새로운 key 생성
            key_id = max_existing_id + obj_counter + 1
            key_data = create_object_from_template(
                "key", key_id, room_id, room_location, room_size, floor_z
            )
            
            if key_data:
                # key의 unlocks 속성에 safe ID 설정
                key_data["unlocks"] = int(safe_id_str)
                generated_objects.append((str(key_id), key_data))
                keys.append((str(key_id), key_data))  # keys 리스트에도 추가
                obj_counter += 1
                
                # safe의 requires_key와 is_locked 설정
                safe_data["requires_key"] = key_id  # key ID 매핑
                safe_data["is_locked"] = True
                print(f"  🔑 Generated key (ID: {key_id}) for safe (ID: {safe_id_str})")
    
    # key가 생성되었는데 대응하는 safe가 없으면 safe 생성
    for key_id_str, key_data in keys:
        # 이미 연결된 safe가 있는지 확인
        if key_data.get("unlocks") is None:
            # safe 생성
            safe_id = max_existing_id + obj_counter + 1
            safe_data = create_object_from_template(
                "safe", safe_id, room_id, room_location, room_size, floor_z
            )
            
            if safe_data:
                # key의 unlocks 속성에 safe ID 설정
                key_data["unlocks"] = safe_id
                # safe의 requires_key와 is_locked 설정
                safe_data["requires_key"] = int(key_id_str)  # key ID 매핑
                safe_data["is_locked"] = True
                generated_objects.append((str(safe_id), safe_data))
                safes.append((str(safe_id), safe_data))  # safes 리스트에도 추가
                obj_counter += 1
                print(f"  🔒 Generated safe (ID: {safe_id}) for key (ID: {key_id_str})")
    
    if generated_objects:
        print(f"  📦 Generated {len(generated_objects)} objects ({num_recommended} recommended, {num_random} random)")
    
    return generated_objects


def generate_objects_in_rooms(json_path: Path, 
                              recommended_item_num: int,
                              random_item_num: int,
                              overwrite_existing: bool = False,
                              templates_path: Optional[Path] = None) -> None:
    """
    JSON 파일의 각 방에 객체를 생성 (템플릿 기반)
    
    Args:
        json_path: JSON 파일 경로
        recommended_item_num: 추천 객체 개수 (방 카테고리에 맞는 객체)
        random_item_num: 랜덤 객체 개수 (모든 템플릿에서 랜덤 선택)
        overwrite_existing: 기존 객체를 덮어쓸지 여부
        templates_path: 템플릿 파일 경로 (None이면 자동으로 찾기)
    """
    # 템플릿 로드
    load_object_templates(templates_path)
    
    print(f"📂 Loading JSON file: {json_path}")
    
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    if "output" not in data:
        print("❌ Invalid JSON structure: 'output' key not found")
        return
    
    output = data["output"]
    rooms = output.get("room", {})
    existing_objects = output.get("object", {})
    
    if not rooms:
        print("❌ No rooms found in JSON file")
        return
    
    print(f"🏢 Found {len(rooms)} rooms")
    print(f"📦 Found {len(existing_objects)} existing objects")
    
    if overwrite_existing:
        print("⚠️  Overwriting existing objects...")
        existing_objects = {}
        output["object"] = {}
    else:
        print("ℹ️  Keeping existing objects and adding new ones...")
    
    # 각 방에 객체 생성
    total_generated = 0
    for room_id_str, room_data in rooms.items():
        try:
            room_id = int(room_id_str)
        except (ValueError, TypeError):
            print(f"⚠️  Skipping invalid room ID: {room_id_str}")
            continue
        
        scene_category = room_data.get("scene_category", "unknown")
        floor_number = room_data.get("floor_number", "?")
        
        print(f"\n🏠 Room {room_id} ({scene_category}, Floor {floor_number})")
        
        generated = generate_objects_for_room(
            room_id, room_data, existing_objects,
            recommended_item_num, random_item_num
        )
        
        # 생성된 객체를 기존 객체 딕셔너리에 추가
        for obj_id_str, obj_data in generated:
            existing_objects[obj_id_str] = obj_data
            obj_class = obj_data["class_"]
            print(f"  ✅ Generated: {obj_class} (ID: {obj_id_str}) at {obj_data['location']}")
        
        total_generated += len(generated)
    
    # 업데이트된 객체 딕셔너리를 JSON에 저장
    output["object"] = existing_objects
    
    # 새 파일명 생성: 원본파일명_with_objects.json
    original_stem = json_path.stem  # 확장자 제외한 파일명
    output_path = json_path.parent / f"{original_stem}_with_objects.json"
    
    # JSON 파일 저장
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Generated {total_generated} objects in total")
    print(f"📦 Total objects in JSON: {len(existing_objects)}")
    print(f"💾 Saved to: {output_path}")


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="각 방에 객체를 임의로 생성하는 스크립트"
    )
    parser.add_argument(
        "--json", "-j",
        type=str,
        help="JSON 파일 경로 (지정하지 않으면 현재 디렉토리의 첫 번째 JSON 파일 사용)"
    )
    parser.add_argument(
        "--recommended-item-num",
        type=int,
        default=RECOMMENDED_ITEM_NUM,
        help=f"추천 객체 개수 (방 카테고리에 맞는 객체, 기본값: {RECOMMENDED_ITEM_NUM})"
    )
    parser.add_argument(
        "--random-item-num",
        type=int,
        default=RANDOM_ITEM_NUM,
        help=f"랜덤 객체 개수 (모든 템플릿에서 랜덤 선택, 기본값: {RANDOM_ITEM_NUM})"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="기존 객체를 덮어쓰기 (기본값: False, 기존 객체 유지)"
    )
    parser.add_argument(
        "--templates", "-t",
        type=str,
        help="merged_objects_template.json 파일 경로 (지정하지 않으면 자동으로 찾기)"
    )
    
    args = parser.parse_args()
    
    # JSON 파일 경로 결정
    if args.json:
        json_path = Path(args.json)
        if not json_path.exists():
            print(f"❌ JSON file not found: {json_path}")
            return
    else:
        # 현재 디렉토리에서 JSON 파일 찾기 (템플릿 파일과 출력 파일 제외)
        script_dir = Path(__file__).parent
        all_json_files = list(script_dir.glob("*.json"))
        
        # 템플릿 파일과 출력 파일 제외
        json_files = [
            f for f in all_json_files
            if not f.name.endswith("_with_objects.json")  # 출력 파일 제외
            and f.name != "merged_objects_template.json"  # 템플릿 파일 제외
        ]
        
        if not json_files:
            print(f"❌ No JSON files found in {script_dir} (excluding templates and output files)")
            return
        json_path = json_files[0]
        if len(json_files) > 1:
            print(f"⚠️  Multiple JSON files found. Using: {json_path.name}")
    
    # 템플릿 파일 경로 결정
    templates_path = None
    if args.templates:
        templates_path = Path(args.templates)
        if not templates_path.exists():
            print(f"❌ Template file not found: {templates_path}")
            return
    
    # 객체 생성 (하드코딩된 값 사용)
    generate_objects_in_rooms(
        json_path,
        recommended_item_num=RECOMMENDED_ITEM_NUM,
        random_item_num=RANDOM_ITEM_NUM,
        overwrite_existing=args.overwrite,
        templates_path=templates_path
    )
    
    print("\n✨ Done! You can now run json_to_dynamic_ttl.py to update TTL files.")


if __name__ == "__main__":
    main()


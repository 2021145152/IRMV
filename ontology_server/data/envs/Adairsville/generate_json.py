




import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
import traceback

# --- 공통 함수 ---
def convert_numpy_to_python(obj):
    """NumPy 타입을 Python 기본 타입으로 재귀적으로 변환 (JSON 호환)
    
    NumPy 배열, 정수, 실수, 불린, 문자열 등을 Python 기본 타입으로 변환합니다.
    
    Args:
        obj: 변환할 객체 (dict, list, numpy array 등)
    
    Returns:
        변환된 Python 기본 타입 객체
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int_, np.intc, np.intp, np.int8,
                          np.int16, np.int32, np.int64, np.uint8, np.uint16,
                          np.uint32, np.uint64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.str_):
        return str(obj)
    elif isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            result[key] = convert_numpy_to_python(value)
        return result
    elif isinstance(obj, (list, tuple)):
        result = []
        for item in obj:
            result.append(convert_numpy_to_python(item))
        return result
    else:
        return obj

def load_scene_data(npz_path):
    """NPZ 파일에서 씬 데이터 로드
    
    NPZ 파일에서 building, room, object 데이터만 추출하여 로드합니다.
    
    Args:
        npz_path: NPZ 파일 경로 (str 또는 Path)
    
    Returns:
        dict: {'output': {'building': {...}, 'room': {...}, 'object': {...}}} 형태의 데이터
    
    Raises:
        FileNotFoundError: NPZ 파일을 찾을 수 없을 때
        ValueError: NPZ 파일이 아닐 때
    """
    npz_path = Path(npz_path)
    
    if not npz_path.exists():
        raise FileNotFoundError(f"NPZ 파일을 찾을 수 없습니다: {npz_path}")
    
    if npz_path.suffix != '.npz':
        raise ValueError(f"NPZ 파일이 아닙니다: {npz_path}")
    
    # NPZ 파일 로드
    data = np.load(npz_path, allow_pickle=True)
    output = data['output']
    
    # numpy object를 dict로 변환
    if hasattr(output, 'item'):
        output = output.item()
    
    # building, room, object만 선택
    filtered_output = {}
    for key in ['building', 'room', 'object']:
        if key in output:
            filtered_output[key] = output[key]
    
    # 모든 numpy 타입을 Python 기본 타입으로 변환 (JSON 호환)
    filtered_output = convert_numpy_to_python(filtered_output)
    
    # Building에서 NPZ 전용 필드 제거 (voxel 관련, segmentation 관련)
    if 'building' in filtered_output:
        building = filtered_output['building']
        if isinstance(building, dict):
            # NPZ에만 있는 필드들 제거
            npz_only_fields = [
                'num_cameras',  # JSON에는 없음 (대신 original_num_cameras, unique_num_cameras 사용)
                'voxel_size',
                'voxel_resolution',
                'voxel_centers',
                'room_voxel_occupancy',
                'object_voxel_occupancy',
                'room_inst_segmentation',
                'object_inst_segmentation'
            ]
            for field in npz_only_fields:
                building.pop(field, None)
    
    return {'output': filtered_output}

def get_room_color(scene_category):
    """방 종류(scene_category)에 따른 색상 반환
    
    Args:
        scene_category: 방의 카테고리 (예: 'bedroom', 'kitchen', 'staircase' 등)
    
    Returns:
        str: HEX 색상 코드 (알 수 없는 카테고리는 회색 반환)
    """
    color_map = {
        'bathroom': '#87CEEB',
        'bedroom': '#FF69B4',
        'corridor': '#DDA0DD',
        'dining_room': '#F0E68C',
        'kitchen': '#98FB98',
        'living_room': '#FFA07A',
        'lobby': '#D3D3D3',
        'office': '#20B2AA',
        'balcony': '#F5DEB3',
        'unknown': '#C0C0C0',
        'childs_room': '#FFFACD',
        'closet': '#F5F5DC',
        'home_office': '#AFEEEE',
        'staircase': '#A0522D',
        'storage_room': '#FFE4C4'
    }
    return color_map.get(scene_category, color_map['unknown'])

def create_staircase_connections(rooms):
    """연속된 층의 staircase들을 자동으로 연결하는 엣지 생성
    
    각 층의 staircase를 찾아서 알파벳 순서로 정렬한 후,
    연속된 층의 staircase들을 자동으로 연결합니다.
    예: A층 staircase ↔ B층 staircase, B층 staircase ↔ C층 staircase
    
    Args:
        rooms: room 데이터 딕셔너리 (키는 문자열 또는 정수)
        
    Returns:
        list: 생성된 엣지 데이터 리스트
            각 엣지는 {'type': 'connected', 'room1_id': int, 'room2_id': int,
                      'room1_category': str, 'room2_category': str,
                      'room1_floor': str, 'room2_floor': str} 형태
    """
    # staircase 찾기
    staircases_by_floor = {}
    for room_id, room_data in rooms.items():
        if isinstance(room_data, dict):
            scene_category = room_data.get('scene_category', '')
            if scene_category == 'staircase':
                floor_number = room_data.get('floor_number', '')
                if floor_number not in staircases_by_floor:
                    staircases_by_floor[floor_number] = []
                # room_id를 정수로 변환 (문자열일 수 있음)
                room_id_int = int(room_id) if isinstance(room_id, str) else room_id
                staircases_by_floor[floor_number].append({
                    'id': room_id_int,
                    'data': room_data
                })
    
    if not staircases_by_floor:
        return []
    
    # 층을 알파벳 순서로 정렬
    sorted_floors = sorted(staircases_by_floor.keys())
    
    if len(sorted_floors) < 2:
        # 층이 1개 이하면 연결할 수 없음
        return []
    
    # 연속된 층의 staircase들을 연결
    staircase_edges = []
    for i in range(len(sorted_floors) - 1):
        current_floor = sorted_floors[i]
        next_floor = sorted_floors[i + 1]
        
        current_staircases = staircases_by_floor[current_floor]
        next_staircases = staircases_by_floor[next_floor]
        
        # 각 층의 모든 staircase를 다음 층의 모든 staircase와 연결
        for curr_stair in current_staircases:
            for next_stair in next_staircases:
                edge_data = {
                    'type': 'connected',
                    'node1_id': curr_stair['id'],
                    'node1_type': 'room',
                    'node2_id': next_stair['id'],
                    'node2_type': 'room',
                    'room1_category': curr_stair['data'].get('scene_category', 'staircase'),
                    'room2_category': next_stair['data'].get('scene_category', 'staircase'),
                    'room1_floor': curr_stair['data'].get('floor_number', ''),
                    'room2_floor': next_stair['data'].get('floor_number', '')
                }
                staircase_edges.append(edge_data)
    
    return staircase_edges

# --- 2D 평면도 ---
def plot_rooms_on_ax_2d(ax, rooms, floor_number, connection_points=None, edges=None, openings=None, doors=None, stairs=None):
    """2D 평면도에 방과 엣지를 그리는 함수
    
    지정된 층의 방들을 사각형으로 그리고, 엣지와 연결 포인트를 표시합니다.
    
    Args:
        ax: matplotlib Axes 객체
        rooms: 방 데이터 딕셔너리
        floor_number: 표시할 층 번호
        connection_points: 연결 포인트 리스트 (선택적, Door/Opening/StairEnd 등)
        edges: 엣지 리스트 (선택적, 방과 방/Opening/Door/Stairs를 연결하는 선)
        openings: Opening 노드 딕셔너리 (선택적)
        doors: Door 노드 딕셔너리 (선택적)
        stairs: Stairs 노드 딕셔너리 (선택적)
    
    Returns:
        set: 그려진 방 카테고리 집합
    """
    plotted_items = set()
    
    # 해당 층의 방들만 필터링
    for room_id, room_data in rooms.items():
        if room_data.get('floor_number') != floor_number:
            continue
            
        location = room_data['location']
        size = room_data['size']
        scene_category = room_data.get('scene_category', 'unknown')
        
        color = get_room_color(scene_category)
        rect_alpha = 0.2 if scene_category == 'staircase' else 0.4
        rect_color = plt.cm.get_cmap('Oranges')(0.3) if scene_category == 'staircase' else color
        
        x, y = location[0], location[1]
        w, d = size[0], size[1]
        
        rect = mpatches.Rectangle(
            (x - w/2, y - d/2), w, d,
            facecolor=rect_color, edgecolor='black', linewidth=1.0,
            alpha=rect_alpha, label=scene_category
        )
        ax.add_patch(rect)
        ax.text(x, y, f"R{room_id}\n({scene_category})", 
               fontsize=7, ha='center', va='center', color='dimgray')
        plotted_items.add(scene_category)
    
    # Opening 노드 그리기 (connected_rooms로부터 위치 계산)
    if openings:
        for opening_id, opening_data in openings.items():
            connected_rooms = opening_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            # 두 방의 위치 찾기
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = rooms.get(str(room1_id)) if str(room1_id) in rooms else rooms.get(room1_id)
            room2 = rooms.get(str(room2_id)) if str(room2_id) in rooms else rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            # 두 방이 모두 현재 층에 있는지 확인
            if (room1.get('floor_number') != floor_number or 
                room2.get('floor_number') != floor_number):
                continue
            
            # 두 방의 중간점 계산
            loc1 = room1['location']
            loc2 = room2['location']
            opening_location = [
                (loc1[0] + loc2[0]) / 2,
                (loc1[1] + loc2[1]) / 2,
                (loc1[2] + loc2[2]) / 2
            ]
            
            ax.plot(opening_location[0], opening_location[1], 'o', 
                   color='blue', markersize=12, markeredgewidth=2, 
                   alpha=0.9, zorder=10)
            opening_num = opening_id.replace('opening_', '')
            ax.text(opening_location[0], opening_location[1] + 0.5, 
                   f"Opening {opening_num}", 
                   fontsize=8, ha='center', va='bottom', 
                   color='blue', fontweight='bold')
    
    # Door 노드 그리기 (connected_rooms로부터 위치 계산)
    if doors:
        for door_id, door_data in doors.items():
            connected_rooms = door_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            # 두 방의 위치 찾기
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = rooms.get(str(room1_id)) if str(room1_id) in rooms else rooms.get(room1_id)
            room2 = rooms.get(str(room2_id)) if str(room2_id) in rooms else rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            # 두 방이 모두 현재 층에 있는지 확인
            if (room1.get('floor_number') != floor_number or 
                room2.get('floor_number') != floor_number):
                continue
            
            # 두 방의 중간점 계산
            loc1 = room1['location']
            loc2 = room2['location']
            door_location = [
                (loc1[0] + loc2[0]) / 2,
                (loc1[1] + loc2[1]) / 2,
                (loc1[2] + loc2[2]) / 2
            ]
            
            ax.plot(door_location[0], door_location[1], 'X', 
                   color='red', markersize=12, markeredgewidth=2, 
                   alpha=0.9, zorder=10)
            door_num = door_id.replace('door_', '')
            ax.text(door_location[0], door_location[1] + 0.5, 
                   f"Door {door_num}", 
                   fontsize=8, ha='center', va='bottom', 
                   color='red', fontweight='bold')
            
            # Door 엣지 그리기 (room1 -> door -> room2)
            ax.plot([loc1[0], door_location[0]], [loc1[1], door_location[1]], 
                   'k-', linewidth=2, alpha=0.6, zorder=5)
            ax.plot([door_location[0], loc2[0]], [door_location[1], loc2[1]], 
                   'k-', linewidth=2, alpha=0.6, zorder=5)
    
    # Stairs 노드 그리기 (connected_rooms로부터 위치 계산)
    if stairs:
        # 현재 층과 관련된 계단들을 수집
        current_floor_stairs = []
        for stairs_id, stairs_data in stairs.items():
            connected_rooms = stairs_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = rooms.get(str(room1_id)) if str(room1_id) in rooms else rooms.get(room1_id)
            room2 = rooms.get(str(room2_id)) if str(room2_id) in rooms else rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            room1_floor = room1.get('floor_number')
            room2_floor = room2.get('floor_number')
            
            # 현재 층에 있는 방이 하나라도 있으면 포함
            if room1_floor == floor_number or room2_floor == floor_number:
                current_floor_stairs.append({
                    'id': stairs_id,
                    'data': stairs_data,
                    'room1': room1,
                    'room2': room2,
                    'room1_id': room1_id,
                    'room2_id': room2_id,
                    'room1_floor': room1_floor,
                    'room2_floor': room2_floor
                })
        
        # 같은 위치(방)에 있는 계단들을 그룹화
        # 층 간 계단: 같은 방을 공유하는 계단들을 그룹화
        # 같은 층 내 계단: 각각 독립적으로 표시
        stairs_groups = {}
        for stair_info in current_floor_stairs:
            room1_floor = stair_info['room1_floor']
            room2_floor = stair_info['room2_floor']
            
            # 같은 층 내 계단은 각각 독립적으로 처리
            if room1_floor == room2_floor:
                loc1 = stair_info['room1']['location']
                loc2 = stair_info['room2']['location']
                loc = [(loc1[0] + loc2[0]) / 2, (loc1[1] + loc2[1]) / 2, (loc1[2] + loc2[2]) / 2]
                # 같은 층 내 계단은 고유한 키 사용 (stairs_id 기반)
                location_key = (floor_number, 'same_floor', stair_info['id'])
            else:
                # 층 간 계단: 현재 층에 있는 방의 위치 사용
                if room1_floor == floor_number:
                    room_id = stair_info['room1_id']
                    room = stair_info['room1']
                else:
                    room_id = stair_info['room2_id']
                    room = stair_info['room2']
                
                loc = room['location']
                # 같은 방을 공유하는 계단들을 그룹화하기 위해 room_id를 키로 사용
                location_key = (floor_number, room_id)
            
            if location_key not in stairs_groups:
                stairs_groups[location_key] = {
                    'location': loc,
                    'floors': set(),
                    'stairs_ids': []
                }
            
            stairs_groups[location_key]['floors'].add(room1_floor)
            stairs_groups[location_key]['floors'].add(room2_floor)
            stairs_groups[location_key]['stairs_ids'].append(stair_info['id'])
        
        # 그룹화된 계단들을 표시
        for location_key, group_info in stairs_groups.items():
            loc = group_info['location']
            floors = sorted(group_info['floors'])
            stairs_ids = group_info['stairs_ids']
            
            # 층 간 계단인지 확인
            is_inter_floor = len(floors) > 1
            
            if is_inter_floor:
                # 층 간 계단: 보라색, 모든 연결된 층 정보 표시
                floor_str = ' ↔ '.join([f'Floor {f}' for f in floors])
                ax.plot(loc[0], loc[1], '*', 
                       color='purple', markersize=16, markeredgewidth=2, 
                       alpha=0.9, zorder=10)
                stairs_nums = ', '.join([sid.replace('stairs_', '') for sid in stairs_ids])
                ax.text(loc[0], loc[1] + 0.5, 
                       f"Stairs {stairs_nums}\n({floor_str})", 
                       fontsize=7, ha='center', va='bottom', 
                       color='purple', fontweight='bold')
            else:
                # 같은 층 내 계단: 초록색
                ax.plot(loc[0], loc[1], '*', 
                       color='green', markersize=14, markeredgewidth=2, 
                       alpha=0.9, zorder=10)
                stairs_nums = ', '.join([sid.replace('stairs_', '') for sid in stairs_ids])
                ax.text(loc[0], loc[1] + 0.5, 
                       f"Stairs {stairs_nums}", 
                       fontsize=8, ha='center', va='bottom', 
                       color='green', fontweight='bold')
    
    # Opening 엣지 그리기 (connected_rooms로부터 직접 계산)
    if openings:
        for opening_id, opening_data in openings.items():
            connected_rooms = opening_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = rooms.get(str(room1_id)) if str(room1_id) in rooms else rooms.get(room1_id)
            room2 = rooms.get(str(room2_id)) if str(room2_id) in rooms else rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            if (room1.get('floor_number') != floor_number or 
                room2.get('floor_number') != floor_number):
                continue
            
            loc1 = room1['location']
            loc2 = room2['location']
            opening_location = [
                (loc1[0] + loc2[0]) / 2,
                (loc1[1] + loc2[1]) / 2,
                (loc1[2] + loc2[2]) / 2
            ]
            
            # Opening 엣지 그리기 (room1 -> opening -> room2)
            ax.plot([loc1[0], opening_location[0]], [loc1[1], opening_location[1]], 
                   'k-', linewidth=2, alpha=0.6, zorder=5)
            ax.plot([opening_location[0], loc2[0]], [opening_location[1], loc2[1]], 
                   'k-', linewidth=2, alpha=0.6, zorder=5)
    
    # Stairs 엣지 그리기 (connected_rooms로부터 직접 계산)
    if stairs:
        for stairs_id, stairs_data in stairs.items():
            connected_rooms = stairs_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = rooms.get(str(room1_id)) if str(room1_id) in rooms else rooms.get(room1_id)
            room2 = rooms.get(str(room2_id)) if str(room2_id) in rooms else rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            if (room1.get('floor_number') != floor_number or 
                room2.get('floor_number') != floor_number):
                continue
            
            loc1 = room1['location']
            loc2 = room2['location']
            stairs_location = [
                (loc1[0] + loc2[0]) / 2,
                (loc1[1] + loc2[1]) / 2,
                (loc1[2] + loc2[2]) / 2
            ]
            
            # Stairs 엣지 그리기 (room1 -> stairs -> room2)
            ax.plot([loc1[0], stairs_location[0]], [loc1[1], stairs_location[1]], 
                   'k-', linewidth=2, alpha=0.6, zorder=5)
            ax.plot([stairs_location[0], loc2[0]], [stairs_location[1], loc2[1]], 
                   'k-', linewidth=2, alpha=0.6, zorder=5)
    
    # staircase 엣지(room-room 직접 연결) 그리기
    if edges:
        for edge in edges:
            # connected 타입의 엣지만 그리기
            if edge.get('type') != 'connected':
                continue
            
            node1_id = edge.get('node1_id')
            node2_id = edge.get('node2_id')
            node1_type = edge.get('node1_type', 'room')
            node2_type = edge.get('node2_type', 'room')
            
            # Opening/Door/Stairs 관련 엣지는 건너뛰기 (이미 위에서 그렸음)
            if node1_type in ['opening', 'door', 'stairs'] or node2_type in ['opening', 'door', 'stairs']:
                continue
            
            # room-room 직접 연결만 그리기 (주로 staircase)
            if node1_type == 'room' and node2_type == 'room':
                room1 = rooms.get(str(node1_id)) if str(node1_id) in rooms else rooms.get(node1_id)
                room2 = rooms.get(str(node2_id)) if str(node2_id) in rooms else rooms.get(node2_id)
                
                if room1 and room2 and room1.get('floor_number') == floor_number and room2.get('floor_number') == floor_number:
                    loc1 = room1['location']
                    loc2 = room2['location']
                    ax.plot([loc1[0], loc2[0]], [loc1[1], loc2[1]], 
                           'k-', linewidth=2, alpha=0.6, zorder=5)
    
    # 연결 포인트 그리기
    if connection_points:
        for p in connection_points:
            loc = p['location']
            p_type = p['type']
            p_type_base = p_type.split('_')[0]
            
            # 해당 층의 포인트만 표시 (Z 좌표로 층 판단)
            room_z = loc[2]
            # 간단히 해당 층의 방들과 Z 좌표가 비슷한지 확인
            floor_rooms = [r for r in rooms.values() if r.get('floor_number') == floor_number]
            if floor_rooms:
                floor_z_centers = [r['location'][2] for r in floor_rooms]
                avg_floor_z = np.mean(floor_z_centers)
                if abs(room_z - avg_floor_z) > 2.0:  # 2m 이상 차이나면 다른 층
                    continue
            
            if p_type_base == 'Door':
                ax.plot(loc[0], loc[1], 'X', color='red', markersize=12, 
                       markeredgewidth=2, alpha=0.9, zorder=10)
            elif p_type_base == 'Opening':
                ax.plot(loc[0], loc[1], 'o', color='blue', markersize=12,
                       markeredgewidth=2, alpha=0.9, zorder=10)
            elif p_type_base == 'StairEnd':
                ax.plot(loc[0], loc[1], '*', color='green', markersize=15,
                       markeredgewidth=2, alpha=0.9, zorder=10)
    
    return plotted_items

# --- 2D 평면도 포인트 수집 클래스 ---
class PointCollector2D:
    """2D 평면도에서 마우스 클릭 및 키보드 입력을 처리하여 방 선택 및 엣지 생성
    
    주요 기능:
    - 마우스 클릭으로 방 선택 (최대 2개)
    - Enter 키로 선택된 방들 사이에 엣지 생성/삭제 (토글)
    - Backspace 키로 다음 층으로 이동
    - 선택된 방 하이라이트 표시
    - 생성된 엣지 누적 표시
    """
    def __init__(self, ax, rooms, floor_number, all_collected_edges=None, all_collected_openings=None, all_collected_doors=None, all_collected_stairs=None):
        self.ax = ax
        self.rooms = rooms
        self.floor_number = floor_number
        # 최종 저장될 엣지 데이터
        self.collected_edges_final = []
        # 최종 저장될 Opening 노드 데이터
        self.collected_openings_final = {}
        # 최종 저장될 Door 노드 데이터
        self.collected_doors_final = {}
        # 최종 저장될 Stairs 노드 데이터
        self.collected_stairs_final = {}
        # 전체 수집된 엣지 (누적 표시용) - 참조로 전달받아야 함
        if all_collected_edges is not None:
            self.all_collected_edges = all_collected_edges  # 참조 유지
        else:
            self.all_collected_edges = []  # 새 리스트 생성
        # 전체 수집된 Opening 노드 (누적 표시용) - 참조로 전달받아야 함
        if all_collected_openings is not None:
            self.all_collected_openings = all_collected_openings  # 참조 유지
        else:
            self.all_collected_openings = {}  # 새 딕셔너리 생성
        # 전체 수집된 Door 노드 (누적 표시용) - 참조로 전달받아야 함
        if all_collected_doors is not None:
            self.all_collected_doors = all_collected_doors  # 참조 유지
        else:
            self.all_collected_doors = {}  # 새 딕셔너리 생성
        # 전체 수집된 Stairs 노드 (누적 표시용) - 참조로 전달받아야 함
        if all_collected_stairs is not None:
            self.all_collected_stairs = all_collected_stairs  # 참조 유지
        else:
            self.all_collected_stairs = {}  # 새 딕셔너리 생성
        # 선택된 방들 (최대 2개까지만 유지)
        self.selected_rooms = []  # [(room_id, room_data), ...]
        # 선택된 노드 타입 ('opening', 'door', 또는 'stairs')
        self.selected_node_type = 'opening'  # 기본값은 opening
        # 선택된 방을 표시하는 하이라이트 마커들
        self.highlight_markers = []
        # 엣지 선들 (누적 표시용)
        self.edge_lines = []
        # Opening 마커들 (누적 표시용)
        self.opening_markers = []
        # Door 마커들 (누적 표시용)
        self.door_markers = []
        # Stairs 마커들 (누적 표시용)
        self.stairs_markers = []
        # 층 전환 플래그
        self.next_floor_requested = False
        
        # 다음 Opening ID 계산 (사용 가능한 가장 작은 ID 찾기)
        self._update_next_opening_id()
        
        # 다음 Door ID 계산 (사용 가능한 가장 작은 ID 찾기)
        self._update_next_door_id()
        
        # 다음 Stairs ID 계산 (사용 가능한 가장 작은 ID 찾기)
        self._update_next_stairs_id()
        
        # 해당 층의 평균 Z 좌표 계산
        floor_rooms = [r for r in rooms.values() if r.get('floor_number') == floor_number]
        if floor_rooms:
            self.floor_avg_z = np.mean([r['location'][2] for r in floor_rooms])
        else:
            self.floor_avg_z = 0.0
        
        print("\n--- 🔗 2D Floor Plan Edge Creation ---")
        print("1. Room Selection and Edge Creation:")
        print("   - [Left Click Room]  : Select room for Opening (max 2 rooms)")
        print("   - [Right Click Room] : Select room for Door (max 2 rooms)")
        print("   - [Wheel Click Room]: Select room for Stairs (max 2 rooms)")
        print("   - [Enter]            : Create/Remove node between selected rooms (toggle)")
        print("2. Navigation:")
        print("   - [Backspace]        : Move to next floor")
        print("3. Note:")
        print("   - Left click: Creates Room--Opening--Room structure")
        print("   - Right click: Creates Room--Door--Room structure")
        print("   - Wheel click: Creates Room--Stairs--Room structure")
        print("   - Cannot create edge between same rooms")
        print("   - Click same edge again to remove it")
        
        self.cids = []
        # 마우스 클릭 이벤트
        cid = ax.figure.canvas.mpl_connect('button_press_event', self.onclick)
        self.cids.append(cid)
        # 키보드 이벤트
        cid = ax.figure.canvas.mpl_connect('key_press_event', self.on_key_press)
        self.cids.append(cid)
    
    def _update_next_opening_id(self):
        """사용 가능한 가장 작은 Opening ID를 찾아서 설정"""
        if self.all_collected_openings:
            existing_ids = [int(oid.replace('opening_', '')) for oid in self.all_collected_openings.keys() if oid.startswith('opening_')]
            if existing_ids:
                max_id = max(existing_ids)
                # 1부터 max_id+1까지 중 사용 가능한 가장 작은 ID 찾기
                for i in range(1, max_id + 2):
                    if i not in existing_ids:
                        self.next_opening_id = i
                        return
                self.next_opening_id = max_id + 1
            else:
                self.next_opening_id = 1
        else:
            self.next_opening_id = 1
    
    def _update_next_door_id(self):
        """사용 가능한 가장 작은 Door ID를 찾아서 설정"""
        if self.all_collected_doors:
            existing_ids = [int(oid.replace('door_', '')) for oid in self.all_collected_doors.keys() if oid.startswith('door_')]
            if existing_ids:
                max_id = max(existing_ids)
                # 1부터 max_id+1까지 중 사용 가능한 가장 작은 ID 찾기
                for i in range(1, max_id + 2):
                    if i not in existing_ids:
                        self.next_door_id = i
                        return
                self.next_door_id = max_id + 1
            else:
                self.next_door_id = 1
        else:
            self.next_door_id = 1
    
    def _update_next_stairs_id(self):
        """사용 가능한 가장 작은 Stairs ID를 찾아서 설정"""
        if self.all_collected_stairs:
            existing_ids = [int(oid.replace('stairs_', '')) for oid in self.all_collected_stairs.keys() if oid.startswith('stairs_')]
            if existing_ids:
                max_id = max(existing_ids)
                # 1부터 max_id+1까지 중 사용 가능한 가장 작은 ID 찾기
                for i in range(1, max_id + 2):
                    if i not in existing_ids:
                        self.next_stairs_id = i
                        return
                self.next_stairs_id = max_id + 1
            else:
                self.next_stairs_id = 1
        else:
            self.next_stairs_id = 1
        
    def _find_clicked_room(self, x, y):
        """클릭한 위치가 어떤 방 안에 있는지 찾기
        
        겹치지 않을 때: 첫 번째로 발견된 방 반환 (기존 방식)
        겹칠 때: 클릭 위치에서 방 중심까지의 거리가 가장 가까운 방 반환
        
        Args:
            x, y: 클릭한 위치의 좌표 (평면도 좌표계)
        
        Returns:
            tuple: (room_id, room_data) 또는 (None, None)
        """
        overlapping_rooms = []
        
        # 클릭한 위치에 있는 모든 방 찾기
        for room_id, room_data in self.rooms.items():
            if room_data.get('floor_number') != self.floor_number:
                continue
            
            location = room_data['location']
            size = room_data['size']
            
            room_x, room_y = location[0], location[1]
            room_w, room_d = size[0], size[1]
            
            # 방의 경계
            x_min, x_max = room_x - room_w/2, room_x + room_w/2
            y_min, y_max = room_y - room_d/2, room_y + room_d/2
            
            # 클릭한 위치가 방 안에 있는지 확인
            if x_min <= x <= x_max and y_min <= y <= y_max:
                overlapping_rooms.append((room_id, room_data, room_x, room_y))
        
        if not overlapping_rooms:
            return None, None
        
        # 겹치는 방이 1개면 그대로 반환 (기존 방식)
        if len(overlapping_rooms) == 1:
            return overlapping_rooms[0][0], overlapping_rooms[0][1]
        
        # 겹치는 방이 2개 이상이면 거리 기반으로 가장 가까운 방 선택
        min_distance = float('inf')
        closest_room = None
        
        for room_id, room_data, room_x, room_y in overlapping_rooms:
            # 클릭 위치에서 방 중심까지의 유클리드 거리 계산
            distance = np.sqrt((x - room_x)**2 + (y - room_y)**2)
            if distance < min_distance:
                min_distance = distance
                closest_room = (room_id, room_data)
        
        return closest_room

    def _highlight_room(self, room_id, room_data):
        """선택된 방을 하이라이트 표시
        
        방의 중심에 노란색 사각형 마커를 표시하여 선택된 방을 시각적으로 구분합니다.
        
        Args:
            room_id: 방 ID
            room_data: 방 데이터 딕셔너리
        """
        location = room_data['location']
        x, y = location[0], location[1]
        
        # 선택된 방을 표시하는 마커 추가
        marker = self.ax.plot(x, y, 's', color='yellow', markersize=20, 
                             markeredgecolor='orange', markeredgewidth=3,
                             alpha=0.8, zorder=20)[0]
        self.highlight_markers.append(marker)
        self.ax.figure.canvas.draw_idle()

    def _clear_room_highlights(self):
        """선택된 방의 하이라이트 마커를 모두 제거"""
        for marker in self.highlight_markers:
            try:
                marker.remove()
            except:
                pass
        self.highlight_markers.clear()
        self.ax.figure.canvas.draw_idle()

    def onclick(self, event):
        """마우스 클릭 이벤트 처리
        
        - 왼쪽 클릭: Opening용 방 선택/해제
        - 오른쪽 클릭: Door용 방 선택/해제
        - 마우스 휠 클릭: Stairs용 방 선택/해제
        - 이미 선택된 방을 다시 클릭하면 선택 해제
        - 최대 2개까지만 선택 가능
        """
        if event.inaxes != self.ax:
            return
        
        if event.button not in [1, 2, 3]:  # 왼쪽(1), 휠(2), 오른쪽(3) 클릭만 처리
            return
        
        x, y = event.xdata, event.ydata
        
        # 클릭한 위치가 어떤 방 안에 있는지 확인
        clicked_room_id, clicked_room_data = self._find_clicked_room(x, y)
        
        if clicked_room_id is not None:
            # 클릭 타입에 따라 노드 타입 설정
            if event.button == 1:  # 왼쪽 클릭: Opening
                self.selected_node_type = 'opening'
            elif event.button == 3:  # 오른쪽 클릭: Door
                self.selected_node_type = 'door'
            elif event.button == 2:  # 마우스 휠 클릭: Stairs
                self.selected_node_type = 'stairs'
            
            # 방을 클릭한 경우: 방 선택
            # 이미 선택된 방이면 선택 해제
            if (clicked_room_id, clicked_room_data) in self.selected_rooms:
                self.selected_rooms.remove((clicked_room_id, clicked_room_data))
            else:
                # 새로 선택: 최대 2개까지만 선택 가능
                if len(self.selected_rooms) >= 2:
                    # 이미 2개가 선택되어 있으면 새로 선택 불가
                    return
                
                self.selected_rooms.append((clicked_room_id, clicked_room_data))
            
            # 하이라이트 업데이트
            self._clear_room_highlights()
            for rid, rdata in self.selected_rooms:
                self._highlight_room(rid, rdata)
            
            return

    def _create_edge_from_selected_rooms(self):
        """선택된 방들로부터 Opening/Door 노드와 엣지 생성 또는 삭제 (토글 방식)
        
        - 2개 방이 선택되어 있으면 노드 생성 (Opening 또는 Door)
        - Room --Node--> Room 구조로 엣지 2개 생성
        - 이미 존재하는 연결이면 삭제 (토글)
        - 동일한 방끼리는 연결 생성 불가
        """
        if len(self.selected_rooms) < 2:
            return
        
        # 마지막 2개 방만 사용
        room1_id, room1_data = self.selected_rooms[-2]
        room2_id, room2_data = self.selected_rooms[-1]
        
        # room_id를 정수로 변환 (타입 통일)
        room1_id_int = int(room1_id) if isinstance(room1_id, str) else room1_id
        room2_id_int = int(room2_id) if isinstance(room2_id, str) else room2_id
        
        # 동일한 방끼리는 연결 생성 불가
        if room1_id_int == room2_id_int:
            return
        
        # 정렬된 방 ID로 기존 노드 찾기 (양방향 검색)
        edge_key = tuple(sorted([room1_id_int, room2_id_int]))
        
        # 선택된 노드 타입에 따라 처리
        if self.selected_node_type == 'opening':
            # 이미 존재하는 Opening 찾기
            existing_node_id = None
            node_dict = self.all_collected_openings
            final_dict = self.collected_openings_final
            node_prefix = 'opening_'
            node_type_str = 'opening'
            
            for node_id, node_data in node_dict.items():
                connected_rooms = node_data.get('connected_rooms', [])
                if len(connected_rooms) == 2:
                    node_rooms_key = tuple(sorted(connected_rooms))
                    if node_rooms_key == edge_key:
                        existing_node_id = node_id
                        break
        elif self.selected_node_type == 'door':
            # 이미 존재하는 Door 찾기
            existing_node_id = None
            node_dict = self.all_collected_doors
            final_dict = self.collected_doors_final
            node_prefix = 'door_'
            node_type_str = 'door'
            
            for node_id, node_data in node_dict.items():
                connected_rooms = node_data.get('connected_rooms', [])
                if len(connected_rooms) == 2:
                    node_rooms_key = tuple(sorted(connected_rooms))
                    if node_rooms_key == edge_key:
                        existing_node_id = node_id
                        break
        else:  # stairs
            # 이미 존재하는 Stairs 찾기
            existing_node_id = None
            node_dict = self.all_collected_stairs
            final_dict = self.collected_stairs_final
            node_prefix = 'stairs_'
            node_type_str = 'stairs'
            
            for node_id, node_data in node_dict.items():
                connected_rooms = node_data.get('connected_rooms', [])
                if len(connected_rooms) == 2:
                    node_rooms_key = tuple(sorted(connected_rooms))
                    if node_rooms_key == edge_key:
                        existing_node_id = node_id
                        break
        
        if existing_node_id:
            # 노드가 이미 존재하면 삭제
            if existing_node_id in final_dict:
                del final_dict[existing_node_id]
            if existing_node_id in node_dict:
                del node_dict[existing_node_id]
            
            # 삭제 후 다음 ID 업데이트 (재사용 가능한 ID 찾기)
            if self.selected_node_type == 'opening':
                self._update_next_opening_id()
            elif self.selected_node_type == 'door':
                self._update_next_door_id()
            else:  # stairs
                self._update_next_stairs_id()
            
            # 모든 노드를 다시 그리기 (엣지는 connected_rooms로부터 동적 계산)
            self._redraw_all_edges_and_openings()
        else:
            # 노드 생성 (두 방의 중간점)
            if self.selected_node_type == 'opening':
                # 사용 가능한 가장 작은 ID 사용
                self._update_next_opening_id()
                node_id = f"opening_{self.next_opening_id}"
                self.next_opening_id += 1  # 다음 생성을 위해 증가
                final_dict = self.collected_openings_final
                node_dict = self.all_collected_openings
                node_type_str = 'opening'
            elif self.selected_node_type == 'door':
                # 사용 가능한 가장 작은 ID 사용
                self._update_next_door_id()
                node_id = f"door_{self.next_door_id}"
                self.next_door_id += 1  # 다음 생성을 위해 증가
                final_dict = self.collected_doors_final
                node_dict = self.all_collected_doors
                node_type_str = 'door'
            else:  # stairs
                # 사용 가능한 가장 작은 ID 사용
                self._update_next_stairs_id()
                node_id = f"stairs_{self.next_stairs_id}"
                self.next_stairs_id += 1  # 다음 생성을 위해 증가
                final_dict = self.collected_stairs_final
                node_dict = self.all_collected_stairs
                node_type_str = 'stairs'
            
            loc1 = room1_data['location']
            loc2 = room2_data['location']
            
            node_data = {
                'connected_rooms': sorted([room1_id_int, room2_id_int])
            }
            
            # 노드 추가 (connected_rooms만 저장, 명시적 엣지 생성 안 함)
            final_dict[node_id] = node_data
            node_dict[node_id] = node_data
            
            # 모든 노드를 다시 그리기 (엣지는 connected_rooms로부터 동적 계산)
            self._redraw_all_edges_and_openings()
        
        # 연결 생성/삭제 후 방 선택 초기화
        self.selected_rooms.clear()
        self._clear_room_highlights()
        
        self.ax.figure.canvas.draw_idle()

    def _redraw_all_edges_and_openings(self):
        """모든 엣지와 Opening/Door 노드를 다시 그리기 (누적 표시)
        
        기존 엣지 선과 노드 마커를 모두 제거하고, 현재 층에 속한 모든 엣지와
        노드를 다시 그려서 누적 표시합니다.
        """
        # 기존 엣지 선 제거
        for line in self.edge_lines:
            try:
                if hasattr(line, 'remove'):
                    line.remove()
            except:
                pass
        self.edge_lines.clear()
        
        # 기존 Opening 마커 제거
        for marker in self.opening_markers:
            try:
                if hasattr(marker, 'remove'):
                    marker.remove()
            except:
                pass
        self.opening_markers.clear()
        
        # 기존 Door 마커 제거
        for marker in self.door_markers:
            try:
                if hasattr(marker, 'remove'):
                    marker.remove()
            except:
                pass
        self.door_markers.clear()
        
        # 기존 Stairs 마커 제거
        for marker in self.stairs_markers:
            try:
                if hasattr(marker, 'remove'):
                    marker.remove()
            except:
                pass
        self.stairs_markers.clear()
        
        # 현재 층의 모든 Opening 다시 그리기
        for opening_id, opening_data in self.all_collected_openings.items():
            connected_rooms = opening_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            # 두 방의 위치 찾기
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = self.rooms.get(str(room1_id)) if str(room1_id) in self.rooms else self.rooms.get(room1_id)
            room2 = self.rooms.get(str(room2_id)) if str(room2_id) in self.rooms else self.rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            # 두 방이 모두 현재 층에 있는지 확인
            if (room1.get('floor_number') != self.floor_number or 
                room2.get('floor_number') != self.floor_number):
                continue
            
            # 두 방의 중간점 계산
            loc1 = room1['location']
            loc2 = room2['location']
            opening_location = [
                (loc1[0] + loc2[0]) / 2,
                (loc1[1] + loc2[1]) / 2,
                (loc1[2] + loc2[2]) / 2
            ]
            
            # Opening 마커 그리기
            marker = self.ax.plot(opening_location[0], opening_location[1], 'o', 
                                 color='blue', markersize=12, markeredgewidth=2, 
                                 alpha=0.9, zorder=10)[0]
            self.opening_markers.append(marker)
            opening_num = opening_id.replace('opening_', '')
            text = self.ax.text(opening_location[0], opening_location[1] + 0.5, 
                               f"Opening {opening_num}", 
                               fontsize=8, ha='center', va='bottom', 
                               color='blue', fontweight='bold', zorder=11)
            self.opening_markers.append(text)
        
        # 현재 층의 모든 Door 다시 그리기
        for door_id, door_data in self.all_collected_doors.items():
            connected_rooms = door_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            # 두 방의 위치 찾기
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = self.rooms.get(str(room1_id)) if str(room1_id) in self.rooms else self.rooms.get(room1_id)
            room2 = self.rooms.get(str(room2_id)) if str(room2_id) in self.rooms else self.rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            # 두 방이 모두 현재 층에 있는지 확인
            if (room1.get('floor_number') != self.floor_number or 
                room2.get('floor_number') != self.floor_number):
                continue
            
            # 두 방의 중간점 계산
            loc1 = room1['location']
            loc2 = room2['location']
            door_location = [
                (loc1[0] + loc2[0]) / 2,
                (loc1[1] + loc2[1]) / 2,
                (loc1[2] + loc2[2]) / 2
            ]
            
            # Door 마커 그리기
            marker = self.ax.plot(door_location[0], door_location[1], 'X', 
                                 color='red', markersize=12, markeredgewidth=2, 
                                 alpha=0.9, zorder=10)[0]
            self.door_markers.append(marker)
            door_num = door_id.replace('door_', '')
            text = self.ax.text(door_location[0], door_location[1] + 0.5, 
                               f"Door {door_num}", 
                               fontsize=8, ha='center', va='bottom', 
                               color='red', fontweight='bold', zorder=11)
            self.door_markers.append(text)
        
        # 현재 층의 모든 Stairs 다시 그리기
        for stairs_id, stairs_data in self.all_collected_stairs.items():
            connected_rooms = stairs_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            # 두 방의 위치 찾기
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = self.rooms.get(str(room1_id)) if str(room1_id) in self.rooms else self.rooms.get(room1_id)
            room2 = self.rooms.get(str(room2_id)) if str(room2_id) in self.rooms else self.rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            # 두 방이 모두 현재 층에 있는지 확인
            if (room1.get('floor_number') != self.floor_number or 
                room2.get('floor_number') != self.floor_number):
                continue
            
            # 두 방의 중간점 계산
            loc1 = room1['location']
            loc2 = room2['location']
            stairs_location = [
                (loc1[0] + loc2[0]) / 2,
                (loc1[1] + loc2[1]) / 2,
                (loc1[2] + loc2[2]) / 2
            ]
            
            # Stairs 마커 그리기 (별 모양)
            marker = self.ax.plot(stairs_location[0], stairs_location[1], '*', 
                                 color='green', markersize=14, markeredgewidth=2, 
                                 alpha=0.9, zorder=10)[0]
            self.stairs_markers.append(marker)
            stairs_num = stairs_id.replace('stairs_', '')
            text = self.ax.text(stairs_location[0], stairs_location[1] + 0.5, 
                               f"Stairs {stairs_num}", 
                               fontsize=8, ha='center', va='bottom', 
                               color='green', fontweight='bold', zorder=11)
            self.stairs_markers.append(text)
        
        # Opening 노드의 엣지 그리기 (connected_rooms로부터 직접 계산)
        for opening_id, opening_data in self.all_collected_openings.items():
            connected_rooms = opening_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = self.rooms.get(str(room1_id)) if str(room1_id) in self.rooms else self.rooms.get(room1_id)
            room2 = self.rooms.get(str(room2_id)) if str(room2_id) in self.rooms else self.rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            # 두 방이 모두 현재 층에 있는지 확인
            if (room1.get('floor_number') != self.floor_number or 
                room2.get('floor_number') != self.floor_number):
                continue
            
            # Opening 위치 계산
            loc1 = room1['location']
            loc2 = room2['location']
            opening_location = [
                (loc1[0] + loc2[0]) / 2,
                (loc1[1] + loc2[1]) / 2,
                (loc1[2] + loc2[2]) / 2
            ]
            
            # room1 -> opening -> room2 엣지 그리기
            line1 = self.ax.plot([loc1[0], opening_location[0]], [loc1[1], opening_location[1]], 
                                'k-', linewidth=2, alpha=0.6, zorder=5)[0]
            line2 = self.ax.plot([opening_location[0], loc2[0]], [opening_location[1], loc2[1]], 
                                'k-', linewidth=2, alpha=0.6, zorder=5)[0]
            self.edge_lines.extend([line1, line2])
        
        # Door 노드의 엣지 그리기 (connected_rooms로부터 직접 계산)
        for door_id, door_data in self.all_collected_doors.items():
            connected_rooms = door_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = self.rooms.get(str(room1_id)) if str(room1_id) in self.rooms else self.rooms.get(room1_id)
            room2 = self.rooms.get(str(room2_id)) if str(room2_id) in self.rooms else self.rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            # 두 방이 모두 현재 층에 있는지 확인
            if (room1.get('floor_number') != self.floor_number or 
                room2.get('floor_number') != self.floor_number):
                continue
            
            # Door 위치 계산
            loc1 = room1['location']
            loc2 = room2['location']
            door_location = [
                (loc1[0] + loc2[0]) / 2,
                (loc1[1] + loc2[1]) / 2,
                (loc1[2] + loc2[2]) / 2
            ]
            
            # room1 -> door -> room2 엣지 그리기
            line1 = self.ax.plot([loc1[0], door_location[0]], [loc1[1], door_location[1]], 
                                'k-', linewidth=2, alpha=0.6, zorder=5)[0]
            line2 = self.ax.plot([door_location[0], loc2[0]], [door_location[1], loc2[1]], 
                                'k-', linewidth=2, alpha=0.6, zorder=5)[0]
            self.edge_lines.extend([line1, line2])
        
        # Stairs 노드의 엣지 그리기 (connected_rooms로부터 직접 계산)
        for stairs_id, stairs_data in self.all_collected_stairs.items():
            connected_rooms = stairs_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = self.rooms.get(str(room1_id)) if str(room1_id) in self.rooms else self.rooms.get(room1_id)
            room2 = self.rooms.get(str(room2_id)) if str(room2_id) in self.rooms else self.rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            # 두 방이 모두 현재 층에 있는지 확인
            if (room1.get('floor_number') != self.floor_number or 
                room2.get('floor_number') != self.floor_number):
                continue
            
            # Stairs 위치 계산
            loc1 = room1['location']
            loc2 = room2['location']
            stairs_location = [
                (loc1[0] + loc2[0]) / 2,
                (loc1[1] + loc2[1]) / 2,
                (loc1[2] + loc2[2]) / 2
            ]
            
            # room1 -> stairs -> room2 엣지 그리기
            line1 = self.ax.plot([loc1[0], stairs_location[0]], [loc1[1], stairs_location[1]], 
                                'k-', linewidth=2, alpha=0.6, zorder=5)[0]
            line2 = self.ax.plot([stairs_location[0], loc2[0]], [stairs_location[1], loc2[1]], 
                                'k-', linewidth=2, alpha=0.6, zorder=5)[0]
            self.edge_lines.extend([line1, line2])
        
        # staircase 엣지(room-room 직접 연결) 그리기
        for edge in self.all_collected_edges:
            # connected 타입의 엣지만 그리기
            if edge.get('type') != 'connected':
                continue
            
            node1_id = edge.get('node1_id')
            node2_id = edge.get('node2_id')
            node1_type = edge.get('node1_type', 'room')
            node2_type = edge.get('node2_type', 'room')
            
            # Opening/Door/Stairs 관련 엣지는 건너뛰기 (이미 위에서 그렸음)
            if node1_type in ['opening', 'door', 'stairs'] or node2_type in ['opening', 'door', 'stairs']:
                continue
            
            # room-room 직접 연결만 그리기 (주로 staircase)
            if node1_type == 'room' and node2_type == 'room':
                room1 = self.rooms.get(str(node1_id)) if str(node1_id) in self.rooms else self.rooms.get(node1_id)
                room2 = self.rooms.get(str(node2_id)) if str(node2_id) in self.rooms else self.rooms.get(node2_id)
                
                if room1 and room2 and room1.get('floor_number') == self.floor_number and room2.get('floor_number') == self.floor_number:
                    loc1 = room1['location']
                    loc2 = room2['location']
                    line = self.ax.plot([loc1[0], loc2[0]], [loc1[1], loc2[1]], 
                                       'k-', linewidth=2, alpha=0.6, zorder=5)[0]
                    self.edge_lines.append(line)
    

    def on_key_press(self, event):
        """키보드 이벤트 처리
        
        - Enter: 선택된 방들 사이에 엣지 생성/삭제 (토글)
        - Backspace: 다음 층으로 이동
        """
        if event.key == 'enter':
            self._create_edge_from_selected_rooms()
        elif event.key == 'backspace':
            self.next_floor_requested = True
            print("\n⏭️  Moving to next floor...")

    def disconnect(self):
        """matplotlib 이벤트 핸들러 연결 해제
        
        클래스가 소멸되기 전에 등록된 모든 이벤트 핸들러를 해제합니다.
        """
        if not self.cids:
            return
        try:
            fig = self.ax.figure
            for cid in self.cids:
                fig.canvas.mpl_disconnect(cid)
            self.cids = []
            print("   (Event handlers disconnected)")
        except Exception as e:
            print(f"   (Error disconnecting event handlers: {e})")

# --- 층 관리 함수 ---
def get_floor_numbers(rooms):
    """모든 방에서 층 번호를 추출하고 정렬
    
    Args:
        rooms: 방 데이터 딕셔너리
    
    Returns:
        list: 정렬된 층 번호 리스트 (예: ['A', 'B', 'C'] 또는 [1, 2, 3])
              숫자로 변환 가능하면 숫자 순으로, 아니면 문자열 순으로 정렬
    """
    floor_numbers = set()
    for room_data in rooms.values():
        floor_num = room_data.get('floor_number')
        if floor_num:
            floor_numbers.add(floor_num)
    # 정렬 (문자열이면 알파벳 순, 숫자면 숫자 순)
    try:
        # 숫자로 변환 가능하면 숫자로 정렬
        sorted_floors = sorted(floor_numbers, key=lambda x: (int(x) if str(x).isdigit() else float('inf'), str(x)))
    except:
        # 숫자 변환 실패하면 문자열로 정렬
        sorted_floors = sorted(floor_numbers)
    return sorted_floors

def filter_rooms_by_floor(rooms, floor_number):
    """특정 층의 방들만 필터링
    
    Args:
        rooms: 방 데이터 딕셔너리
        floor_number: 필터링할 층 번호
    
    Returns:
        dict: 해당 층의 방들만 포함한 딕셔너리
    """
    filtered = {}
    for room_id, room_data in rooms.items():
        if room_data.get('floor_number') == floor_number:
            filtered[room_id] = room_data
    return filtered

def create_2d_topdown_view(npz_path, rooms, building, connection_points=None, building_name=None, output_dir=None):
    """2D 평면도 생성 및 인터랙티브 엣지 수집 (층별 뷰)
    
    각 층별로 2D 평면도를 생성하고, 사용자가 마우스 클릭으로 방을 선택하여
    엣지를 생성할 수 있도록 합니다. Backspace 키를 누르면 다음 층으로 이동합니다.
    
    Args:
        npz_path: NPZ 파일 경로 (사용되지 않지만 호환성을 위해 유지)
        rooms: 방 데이터 딕셔너리
        building: 건물 데이터 딕셔너리
        connection_points: 연결 포인트 리스트 (선택적)
        building_name: 건물 이름 (제목 표시용)
        output_dir: 출력 디렉토리 (지도 저장용)
    
    Returns:
        tuple: (fig, ax, all_collected_points, all_collected_openings, all_collected_doors, all_collected_stairs)
            - fig: matplotlib Figure 객체
            - ax: matplotlib Axes 객체
            - all_collected_points: 수집된 모든 엣지 리스트
            - all_collected_openings: 수집된 모든 Opening 노드 딕셔너리
            - all_collected_doors: 수집된 모든 Door 노드 딕셔너리
            - all_collected_stairs: 수집된 모든 Stairs 노드 딕셔너리
    """
    # 모든 층 번호 추출
    floor_numbers = get_floor_numbers(rooms)
    if not floor_numbers:
        print("❌ Floor information not found.")
        return None, None, [], {}, {}, {}
    
    print(f"\n🏢 Found floors: {', '.join(map(str, floor_numbers))}")
    print(f"Total {len(floor_numbers)} floor(s)")
    
    # 전체 좌표 범위 계산
    if not rooms:
        print("❌ No room data found.")
        return None, None, [], {}, {}, {}
    
    # 방들의 위치와 크기로부터 범위 계산
    x_coords = []
    y_coords = []
    for room_data in rooms.values():
        location = room_data['location']
        size = room_data['size']
        x, y = location[0], location[1]
        w, d = size[0], size[1]
        x_coords.extend([x - w/2, x + w/2])
        y_coords.extend([y - d/2, y + d/2])
    
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    margin = 2.0
    global_xlim = (x_min - margin, x_max + margin)
    global_ylim = (y_min - margin, y_max + margin)
    
    # 2D 플롯 생성
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    
    # 현재 층 인덱스
    current_floor_idx = 0
    all_collected_points = []
    all_collected_openings = {}
    all_collected_doors = {}
    all_collected_stairs = {}
    
    # 층별로 반복
    while current_floor_idx < len(floor_numbers):
        current_floor = floor_numbers[current_floor_idx]
        current_floor_rooms = filter_rooms_by_floor(rooms, current_floor)
        
        print(f"\n{'='*60}")
        print(f"🏢 Current floor: {current_floor} ({current_floor_idx + 1}/{len(floor_numbers)})")
        print(f"   Number of rooms: {len(current_floor_rooms)}")
        print(f"{'='*60}")
        
        # 축 초기화
        ax.clear()
        
        # 현재 층의 방들만 그리기 (이전에 생성된 엣지와 Opening/Door/Stairs도 함께 표시)
        plotted_items = plot_rooms_on_ax_2d(ax, rooms, current_floor, connection_points, 
                                           edges=all_collected_points, openings=all_collected_openings, doors=all_collected_doors, stairs=all_collected_stairs)
        
        # 현재 층의 방 범위 계산 (그리드 조정용)
        if current_floor_rooms:
            floor_x_coords = []
            floor_y_coords = []
            for room_data in current_floor_rooms.values():
                location = room_data['location']
                size = room_data['size']
                x, y = location[0], location[1]
                w, d = size[0], size[1]
                floor_x_coords.extend([x - w/2, x + w/2])
                floor_y_coords.extend([y - d/2, y + d/2])
            
            floor_x_min, floor_x_max = min(floor_x_coords), max(floor_x_coords)
            floor_y_min, floor_y_max = min(floor_y_coords), max(floor_y_coords)
            floor_margin = 2.0
            floor_xlim = (floor_x_min - floor_margin, floor_x_max + floor_margin)
            floor_ylim = (floor_y_min - floor_margin, floor_y_max + floor_margin)
        else:
            floor_xlim = global_xlim
            floor_ylim = global_ylim
        
        # 축 설정 (현재 층 범위에 맞춤)
        ax.set_xlabel('X (m)', fontsize=12)
        ax.set_ylabel('Y (m)', fontsize=12)
        ax.set_xlim(floor_xlim)
        ax.set_ylim(floor_ylim)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.5, which='both')
        ax.set_title(f'Floor {current_floor} ({current_floor_idx + 1}/{len(floor_numbers)})', 
                    fontsize=14, fontweight='bold')
        
        # PointCollector2D 생성 및 활성화 (이미 생성된 엣지와 Opening/Door/Stairs 정보 전달 - 참조로 전달)
        point_collector = PointCollector2D(ax, rooms, current_floor, 
                                          all_collected_edges=all_collected_points,
                                          all_collected_openings=all_collected_openings,
                                          all_collected_doors=all_collected_doors,
                                          all_collected_stairs=all_collected_stairs)
        # 이미 생성된 엣지와 Opening을 시각화에 표시
        point_collector._redraw_all_edges_and_openings()
        plt.draw()  # 화면 업데이트
        
        # 제목 (파일명 표시)
        display_name = building_name if building_name else building.get("name", "Unknown")
        fig.suptitle(f'2D Floor Plan: {display_name} - Floor {current_floor}\n'
                    f'({current_floor_idx + 1}/{len(floor_numbers)}) | '
                    f'[Click Room] Select | [Enter] Toggle Edge | [Backspace] Next Floor', 
                    fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        plt.draw()
        
        print(f"\n📍 Select rooms and create edges on floor {current_floor}.")
        print(f"   Press Backspace to move to next floor.")
        
        # 플롯 표시
        plt.show(block=False)
        
        # Backspace 키가 눌릴 때까지 대기
        import time
        while not point_collector.next_floor_requested:
            plt.pause(0.1)
            time.sleep(0.1)
            if not plt.fignum_exists(fig.number):
                print("\n⚠️  Window closed.")
                break
        
        # 현재 층의 엣지와 Opening/Door/Stairs 저장
        all_collected_points.extend(point_collector.collected_edges_final)
        all_collected_openings.update(point_collector.collected_openings_final)
        all_collected_doors.update(point_collector.collected_doors_final)
        all_collected_stairs.update(point_collector.collected_stairs_final)
        point_collector.disconnect()
        
        # 다음 층으로 이동
        current_floor_idx += 1
        
        if current_floor_idx >= len(floor_numbers):
            print("\n✅ All floors completed!")
            break
    
    plt.close(fig)
    
    print(f"\n--- 📍 All Floor Edges Collection Complete ---")
    print(f"Total {len(all_collected_points)} edges collected and confirmed.")
    print(f"Total {len(all_collected_openings)} openings collected and confirmed.")
    print(f"Total {len(all_collected_doors)} doors collected and confirmed.")
    print(f"Total {len(all_collected_stairs)} stairs collected and confirmed.")
    
    # Opening, Door, Stairs 노드를 ID 순서대로 정렬하여 출력
    all_nodes = []
    
    # Opening 노드 추가
    for opening_id, opening_data in sorted(all_collected_openings.items()):
        opening_num = opening_id.replace('opening_', '')
        connected_rooms = opening_data.get('connected_rooms', [])
        if len(connected_rooms) == 2:
            all_nodes.append({
                'type': 'Opening',
                'id': opening_num,
                'room1': connected_rooms[0],
                'room2': connected_rooms[1]
            })
    
    # Door 노드 추가
    for door_id, door_data in sorted(all_collected_doors.items()):
        door_num = door_id.replace('door_', '')
        connected_rooms = door_data.get('connected_rooms', [])
        if len(connected_rooms) == 2:
            all_nodes.append({
                'type': 'Door',
                'id': door_num,
                'room1': connected_rooms[0],
                'room2': connected_rooms[1]
            })
    
    # Stairs 노드 추가
    for stairs_id, stairs_data in sorted(all_collected_stairs.items()):
        stairs_num = stairs_id.replace('stairs_', '')
        connected_rooms = stairs_data.get('connected_rooms', [])
        if len(connected_rooms) == 2:
            all_nodes.append({
                'type': 'Stairs',
                'id': stairs_num,
                'room1': connected_rooms[0],
                'room2': connected_rooms[1]
            })
    
    # room-room 직접 연결 엣지 (주로 staircase) 추가
    for edge in all_collected_points:
        node1_type = edge.get('node1_type', 'room')
        node2_type = edge.get('node2_type', 'room')
        # Opening/Door/Stairs와 관련된 엣지는 제외 (이미 노드로 표시됨)
        if node1_type == 'room' and node2_type == 'room':
            all_nodes.append({
                'type': 'Staircase',
                'id': None,
                'room1': edge.get('node1_id'),
                'room2': edge.get('node2_id')
            })
    
    if all_nodes:
        print("\n--- 📋 Collected Connections (Final) ---")
        # 타입별로 정렬 (Opening, Door, Stairs, Staircase 순서)
        type_order = {'Opening': 0, 'Door': 1, 'Stairs': 2, 'Staircase': 3}
        all_nodes_sorted = sorted(all_nodes, key=lambda x: (type_order.get(x['type'], 99), int(x['id']) if x['id'] else 0))
        
        for node in all_nodes_sorted:
            if node['type'] == 'Staircase':
                print(f"  {node['type']:12} : Room {node['room1']:3} <-> Room {node['room2']:3}")
            else:
                print(f"  {node['type']:12} {node['id']:3} : Room {node['room1']:3} <-> Room {node['room2']:3}")
        print("----------------------------------------")
    
    # 모든 층 작업 완료 후, 전체 층 뷰로 층 간 계단 연결
    if len(floor_numbers) > 1:
        print(f"\n{'='*60}")
        print(f"🏢 Starting Multi-Floor View for Inter-Floor Stairs")
        print(f"{'='*60}")
        
        fig_all, all_collected_stairs = create_all_floors_view(
            rooms, floor_numbers, all_collected_openings, all_collected_doors, 
            all_collected_stairs, all_collected_points, building_name, output_dir
        )
        
        # 층 간 계단 연결 결과 업데이트
        if fig_all:
            plt.close(fig_all)
    
    return fig, ax, all_collected_points, all_collected_openings, all_collected_doors, all_collected_stairs

# --- 최종 지도 저장 함수 ---
def save_final_map(fig, rooms, floor_numbers, all_collected_openings, all_collected_doors, 
                   all_collected_stairs, all_collected_points, building_name, output_dir, 
                   global_xlim, global_ylim):
    """모든 연결을 포함한 최종 지도를 그리고 저장
    
    Args:
        fig: matplotlib Figure 객체 (기존 figure 재사용)
        rooms: 방 데이터 딕셔너리
        floor_numbers: 층 번호 리스트
        all_collected_openings: 수집된 모든 Opening 노드
        all_collected_doors: 수집된 모든 Door 노드
        all_collected_stairs: 수집된 모든 Stairs 노드
        all_collected_points: 수집된 모든 엣지
        building_name: 건물 이름
        output_dir: 출력 디렉토리
        global_xlim: 전역 X축 범위
        global_ylim: 전역 Y축 범위
    """
    print(f"\n--- 📸 Saving Final Map with All Connections ---")
    
    # 기존 figure의 모든 axes 가져오기
    axes = fig.axes
    
    # 각 층별로 모든 연결 정보를 포함하여 다시 그리기
    for idx, floor_num in enumerate(floor_numbers):
        if idx >= len(axes):
            continue
        
        ax = axes[idx]
        ax.clear()
        
        # 해당 층의 같은 층 내 연결 필터링
        same_floor_openings = {}
        same_floor_doors = {}
        same_floor_stairs = {}
        same_floor_edges = []
        
        # Opening 필터링 (같은 층 내)
        for opening_id, opening_data in all_collected_openings.items():
            connected_rooms = opening_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = rooms.get(str(room1_id)) if str(room1_id) in rooms else rooms.get(room1_id)
            room2 = rooms.get(str(room2_id)) if str(room2_id) in rooms else rooms.get(room2_id)
            if room1 and room2:
                if room1.get('floor_number') == floor_num and room2.get('floor_number') == floor_num:
                    same_floor_openings[opening_id] = opening_data
        
        # Door 필터링 (같은 층 내)
        for door_id, door_data in all_collected_doors.items():
            connected_rooms = door_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = rooms.get(str(room1_id)) if str(room1_id) in rooms else rooms.get(room1_id)
            room2 = rooms.get(str(room2_id)) if str(room2_id) in rooms else rooms.get(room2_id)
            if room1 and room2:
                if room1.get('floor_number') == floor_num and room2.get('floor_number') == floor_num:
                    same_floor_doors[door_id] = door_data
        
        # Stairs 필터링 (같은 층 내 + 층간)
        for stairs_id, stairs_data in all_collected_stairs.items():
            connected_rooms = stairs_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = rooms.get(str(room1_id)) if str(room1_id) in rooms else rooms.get(room1_id)
            room2 = rooms.get(str(room2_id)) if str(room2_id) in rooms else rooms.get(room2_id)
            if room1 and room2:
                room1_floor = room1.get('floor_number')
                room2_floor = room2.get('floor_number')
                # 같은 층 내 또는 현재 층과 관련된 층간 계단
                if room1_floor == floor_num or room2_floor == floor_num:
                    same_floor_stairs[stairs_id] = stairs_data
        
        # 같은 층 내 엣지 필터링
        for edge in all_collected_points:
            node1_type = edge.get('node1_type', 'room')
            node2_type = edge.get('node2_type', 'room')
            if node1_type == 'room' and node2_type == 'room':
                node1_id = edge.get('node1_id')
                node2_id = edge.get('node2_id')
                room1 = rooms.get(str(node1_id)) if str(node1_id) in rooms else rooms.get(node1_id)
                room2 = rooms.get(str(node2_id)) if str(node2_id) in rooms else rooms.get(node2_id)
                if room1 and room2:
                    if room1.get('floor_number') == floor_num and room2.get('floor_number') == floor_num:
                        same_floor_edges.append(edge)
        
        # 모든 연결을 포함하여 그리기
        plot_rooms_on_ax_2d(ax, rooms, floor_num,
                           edges=same_floor_edges,
                           openings=same_floor_openings,
                           doors=same_floor_doors,
                           stairs=same_floor_stairs)
        
        # 축 설정
        ax.set_xlim(global_xlim)
        ax.set_ylim(global_ylim)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.5, which='both')
        ax.set_title(f'Floor {floor_num}', fontsize=12, fontweight='bold')
        ax.set_xlabel('X (m)', fontsize=10)
        ax.set_ylabel('Y (m)', fontsize=10)
    
    # 제목 업데이트
    display_name = building_name if building_name else "Unknown"
    fig.suptitle(f'Final Map: {display_name} - All Connections\n'
                f'Opening (Blue) | Door (Red) | Stairs (Green/Purple) | Direct Connections (Black)', 
                fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.draw()
    
    # 파일 저장
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    map_filename = output_dir / f"{building_name}_final_map.png"
    
    try:
        fig.savefig(map_filename, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"✅ Final map saved: {map_filename}")
    except Exception as e:
        print(f"❌ Error saving final map: {e}")

# --- 전체 층 뷰 함수 ---
def create_all_floors_view(rooms, floor_numbers, all_collected_openings, all_collected_doors, 
                          all_collected_stairs, all_collected_points, building_name=None, output_dir=None):
    """모든 층을 한 화면에 표시하고 층 간 계단 연결을 위한 인터랙티브 뷰
    
    Args:
        rooms: 방 데이터 딕셔너리
        floor_numbers: 층 번호 리스트
        all_collected_openings: 수집된 모든 Opening 노드
        all_collected_doors: 수집된 모든 Door 노드
        all_collected_stairs: 수집된 모든 Stairs 노드
        all_collected_points: 수집된 모든 엣지
        building_name: 건물 이름
        output_dir: 출력 디렉토리 (지도 저장용)
    
    Returns:
        tuple: (fig, updated_stairs)
    """
    # 전체 좌표 범위 계산
    x_coords = []
    y_coords = []
    for room_data in rooms.values():
        location = room_data['location']
        size = room_data['size']
        x, y = location[0], location[1]
        w, d = size[0], size[1]
        x_coords.extend([x - w/2, x + w/2])
        y_coords.extend([y - d/2, y + d/2])
    
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    margin = 2.0
    global_xlim = (x_min - margin, x_max + margin)
    global_ylim = (y_min - margin, y_max + margin)
    
    # 서브플롯 생성 (모든 층을 가로로 일렬 배치)
    num_floors = len(floor_numbers)
    
    # 각 층당 너비 계산 (층이 많을수록 좁게)
    width_per_floor = max(4, 20 / num_floors)  # 최소 4, 최대 20
    total_width = width_per_floor * num_floors
    fig_height = 8
    
    fig, axes = plt.subplots(1, num_floors, figsize=(total_width, fig_height))
    
    # 단일 서브플롯인 경우 리스트로 변환
    if num_floors == 1:
        axes = [axes]
    
    # 층 간 계단만 필터링 (같은 층 내 계단은 제외)
    inter_floor_stairs = {}
    for stairs_id, stairs_data in all_collected_stairs.items():
        connected_rooms = stairs_data.get('connected_rooms', [])
        if len(connected_rooms) != 2:
            continue
        
        room1_id, room2_id = connected_rooms[0], connected_rooms[1]
        room1 = rooms.get(str(room1_id)) if str(room1_id) in rooms else rooms.get(room1_id)
        room2 = rooms.get(str(room2_id)) if str(room2_id) in rooms else rooms.get(room2_id)
        
        if not room1 or not room2:
            continue
        
        # 층 간 계단만 포함 (서로 다른 층)
        if room1.get('floor_number') != room2.get('floor_number'):
            inter_floor_stairs[stairs_id] = stairs_data
    
    # 각 층을 서브플롯에 그리기 (이전 노드 제외, 층 간 계단만 표시)
    floor_axes_map = {}
    for idx, floor_num in enumerate(floor_numbers):
        ax = axes[idx]
        
        # 해당 층의 방들만 그리기 (Opening, Door, 같은 층 내 Stairs 제외, 층 간 계단만 표시)
        plot_rooms_on_ax_2d(ax, rooms, floor_num, 
                           edges=[],  # 이전 엣지 제외
                           openings={},  # 이전 Opening 제외
                           doors={},  # 이전 Door 제외
                           stairs=inter_floor_stairs)  # 층 간 계단만 표시
        
        # 축 설정
        ax.set_xlim(global_xlim)
        ax.set_ylim(global_ylim)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.5, which='both')
        ax.set_title(f'Floor {floor_num}', fontsize=12, fontweight='bold')
        ax.set_xlabel('X (m)', fontsize=10)
        ax.set_ylabel('Y (m)', fontsize=10)
        
        floor_axes_map[floor_num] = ax
    
    # 제목 설정
    display_name = building_name if building_name else "Unknown"
    fig.suptitle(f'Multi-Floor View: {display_name}\n'
                f'[Wheel Click Room] Select for Inter-Floor Stairs | [Enter] Create | [Backspace] Finish', 
                fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.draw()
    
    # 층 간 계단 연결을 위한 인터랙티브 기능
    print("\n--- 🔗 Inter-Floor Stairs Connection ---")
    print("1. Select rooms from different floors:")
    print("   - [Wheel Click Room] : Select room for inter-floor stairs (max 2 rooms)")
    print("   - [Enter]            : Create/Remove inter-floor stairs (toggle)")
    print("   - [Backspace]        : Finish and exit")
    print("2. Note:")
    print("   - Select one room from one floor, then another room from different floor")
    print("   - Creates Room--Stairs--Room structure connecting different floors")
    
    # MultiFloorPointCollector 생성 (전역 축 범위 전달)
    multi_collector = MultiFloorPointCollector(
        fig, floor_axes_map, rooms, floor_numbers,
        all_collected_stairs, global_xlim, global_ylim
    )
    
    # Backspace 키가 눌릴 때까지 대기
    import time
    while not multi_collector.finished:
        plt.pause(0.1)
        time.sleep(0.1)
        if not plt.fignum_exists(fig.number):
            print("\n⚠️  Window closed.")
            break
    
    multi_collector.disconnect()
    
    # 업데이트된 Stairs 반환
    updated_stairs = multi_collector.all_collected_stairs
    
    print(f"\n--- ✅ Inter-Floor Stairs Complete ---")
    print(f"Total {len(updated_stairs)} stairs (including inter-floor connections)")
    
    # 최종 지도 저장 (모든 연결 포함)
    if output_dir and building_name:
        save_final_map(fig, rooms, floor_numbers, all_collected_openings, all_collected_doors, 
                      updated_stairs, all_collected_points, building_name, output_dir, 
                      global_xlim, global_ylim)
    
    return fig, updated_stairs

# --- 층 간 계단 연결을 위한 포인트 수집 클래스 ---
class MultiFloorPointCollector:
    """모든 층을 한 화면에 표시하고 층 간 계단 연결을 위한 인터랙티브 클래스
    
    주요 기능:
    - 여러 층의 방을 선택하여 층 간 계단 연결
    - 마우스 휠 클릭으로 방 선택 (최대 2개, 서로 다른 층)
    - Enter 키로 층 간 계단 생성/삭제 (토글)
    - Backspace 키로 종료
    - 이전에 생성한 노드(Opening, Door, 같은 층 내 Stairs)는 표시하지 않음
    """
    def __init__(self, fig, floor_axes_map, rooms, floor_numbers, all_collected_stairs, global_xlim, global_ylim):
        self.fig = fig
        self.floor_axes_map = floor_axes_map  # {floor_num: ax}
        self.rooms = rooms
        self.floor_numbers = floor_numbers
        self.all_collected_stairs = all_collected_stairs  # 참조로 전달받음
        self.global_xlim = global_xlim  # 전역 X축 범위 (모든 층 동일)
        self.global_ylim = global_ylim  # 전역 Y축 범위 (모든 층 동일)
        
        # 선택된 방들 (최대 2개, 서로 다른 층)
        self.selected_rooms = []  # [(room_id, room_data, floor_num), ...]
        
        # 하이라이트 마커들
        self.highlight_markers = []
        
        # 완료 플래그
        self.finished = False
        
        # 다음 Stairs ID 계산
        self._update_next_stairs_id()
        
        # 이벤트 핸들러 등록
        self.cids = []
        cid = fig.canvas.mpl_connect('button_press_event', self.onclick)
        self.cids.append(cid)
        cid = fig.canvas.mpl_connect('key_press_event', self.on_key_press)
        self.cids.append(cid)
    
    def _update_next_stairs_id(self):
        """사용 가능한 가장 작은 Stairs ID를 찾아서 설정"""
        if self.all_collected_stairs:
            existing_ids = [int(sid.replace('stairs_', '')) for sid in self.all_collected_stairs.keys() if sid.startswith('stairs_')]
            if existing_ids:
                max_id = max(existing_ids)
                for i in range(1, max_id + 2):
                    if i not in existing_ids:
                        self.next_stairs_id = i
                        return
                self.next_stairs_id = max_id + 1
            else:
                self.next_stairs_id = 1
        else:
            self.next_stairs_id = 1
    
    def _find_clicked_room(self, x, y, ax):
        """클릭한 위치가 어떤 방 안에 있는지 찾기
        
        겹치지 않을 때: 첫 번째로 발견된 방 반환 (기존 방식)
        겹칠 때: 클릭 위치에서 방 중심까지의 거리가 가장 가까운 방 반환
        
        Args:
            x, y: 클릭한 위치의 좌표
            ax: 클릭한 서브플롯의 Axes 객체
        
        Returns:
            tuple: (room_id, room_data, floor_num) 또는 (None, None, None)
        """
        # 어떤 층의 서브플롯인지 찾기
        clicked_floor = None
        for floor_num, floor_ax in self.floor_axes_map.items():
            if floor_ax == ax:
                clicked_floor = floor_num
                break
        
        if clicked_floor is None:
            return None, None, None
        
        overlapping_rooms = []
        
        # 클릭한 위치에 있는 모든 방 찾기
        for room_id, room_data in self.rooms.items():
            if room_data.get('floor_number') != clicked_floor:
                continue
            
            location = room_data['location']
            size = room_data['size']
            
            room_x, room_y = location[0], location[1]
            room_w, room_d = size[0], size[1]
            
            x_min, x_max = room_x - room_w/2, room_x + room_w/2
            y_min, y_max = room_y - room_d/2, room_y + room_d/2
            
            if x_min <= x <= x_max and y_min <= y <= y_max:
                overlapping_rooms.append((room_id, room_data, room_x, room_y))
        
        if not overlapping_rooms:
            return None, None, None
        
        # 겹치는 방이 1개면 그대로 반환 (기존 방식)
        if len(overlapping_rooms) == 1:
            room_id, room_data, _, _ = overlapping_rooms[0]
            return room_id, room_data, clicked_floor
        
        # 겹치는 방이 2개 이상이면 거리 기반으로 가장 가까운 방 선택
        min_distance = float('inf')
        closest_room = None
        
        for room_id, room_data, room_x, room_y in overlapping_rooms:
            # 클릭 위치에서 방 중심까지의 유클리드 거리 계산
            distance = np.sqrt((x - room_x)**2 + (y - room_y)**2)
            if distance < min_distance:
                min_distance = distance
                closest_room = (room_id, room_data)
        
        if closest_room:
            return closest_room[0], closest_room[1], clicked_floor
        
        return None, None, None
    
    def _highlight_room(self, room_id, room_data, floor_num):
        """선택된 방을 하이라이트 표시"""
        location = room_data['location']
        x, y = location[0], location[1]
        
        # 해당 층의 서브플롯 찾기
        ax = self.floor_axes_map.get(floor_num)
        if ax is None:
            return
        
        marker = ax.plot(x, y, 's', color='yellow', markersize=20, 
                        markeredgecolor='orange', markeredgewidth=3,
                        alpha=0.8, zorder=20)[0]
        self.highlight_markers.append(marker)
        self.fig.canvas.draw_idle()
    
    def _clear_room_highlights(self):
        """선택된 방의 하이라이트 마커를 모두 제거"""
        for marker in self.highlight_markers:
            try:
                marker.remove()
            except:
                pass
        self.highlight_markers.clear()
        self.fig.canvas.draw_idle()
    
    def onclick(self, event):
        """마우스 클릭 이벤트 처리
        
        - 마우스 휠 클릭: 층 간 계단용 방 선택/해제
        - 최대 2개까지만 선택 가능
        - 서로 다른 층의 방만 선택 가능
        """
        if event.inaxes is None:
            return
        
        # 마우스 휠 클릭만 처리 (button == 2)
        if event.button != 2:
            return
        
        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return
        
        # 클릭한 위치가 어떤 방 안에 있는지 확인
        clicked_room_id, clicked_room_data, clicked_floor = self._find_clicked_room(x, y, event.inaxes)
        
        if clicked_room_id is not None:
            # 이미 선택된 방이면 선택 해제
            room_tuple = (clicked_room_id, clicked_room_data, clicked_floor)
            if room_tuple in self.selected_rooms:
                self.selected_rooms.remove(room_tuple)
            else:
                # 새로 선택: 최대 2개까지만 선택 가능
                if len(self.selected_rooms) >= 2:
                    # 첫 번째 선택을 제거하고 새로 추가 (FIFO)
                    self.selected_rooms.pop(0)
                
                self.selected_rooms.append(room_tuple)
            
            # 하이라이트 업데이트
            self._clear_room_highlights()
            for rid, rdata, fnum in self.selected_rooms:
                self._highlight_room(rid, rdata, fnum)
    
    def _create_inter_floor_stairs(self):
        """선택된 방들로부터 층 간 계단 생성 또는 삭제 (토글 방식)"""
        if len(self.selected_rooms) < 2:
            return
        
        room1_id, room1_data, floor1 = self.selected_rooms[-2]
        room2_id, room2_data, floor2 = self.selected_rooms[-1]
        
        # 같은 층이면 층 간 계단이 아님
        if floor1 == floor2:
            print(f"⚠️  Both rooms are on the same floor ({floor1}). Inter-floor stairs require different floors.")
            return
        
        # room_id를 정수로 변환
        room1_id_int = int(room1_id) if isinstance(room1_id, str) else room1_id
        room2_id_int = int(room2_id) if isinstance(room2_id, str) else room2_id
        
        # 정렬된 방 ID로 기존 노드 찾기
        edge_key = tuple(sorted([room1_id_int, room2_id_int]))
        
        # 이미 존재하는 Stairs 찾기
        existing_node_id = None
        for node_id, node_data in self.all_collected_stairs.items():
            connected_rooms = node_data.get('connected_rooms', [])
            if len(connected_rooms) == 2:
                node_rooms_key = tuple(sorted(connected_rooms))
                if node_rooms_key == edge_key:
                    existing_node_id = node_id
                    break
        
        if existing_node_id:
            # 노드가 이미 존재하면 삭제
            del self.all_collected_stairs[existing_node_id]
            self._update_next_stairs_id()
            print(f"🗑️  Removed inter-floor stairs: Room {room1_id_int} (Floor {floor1}) <-> Room {room2_id_int} (Floor {floor2})")
        else:
            # 노드 생성
            self._update_next_stairs_id()
            node_id = f"stairs_{self.next_stairs_id}"
            self.next_stairs_id += 1
            
            node_data = {
                'connected_rooms': sorted([room1_id_int, room2_id_int])
            }
            
            self.all_collected_stairs[node_id] = node_data
            print(f"✅ Created inter-floor stairs: Room {room1_id_int} (Floor {floor1}) <-> Room {room2_id_int} (Floor {floor2})")
        
        # 모든 서브플롯 다시 그리기
        self._redraw_all_floors()
        
        # 연결 생성/삭제 후 방 선택 초기화
        self.selected_rooms.clear()
        self._clear_room_highlights()
    
    def _redraw_all_floors(self):
        """모든 층을 다시 그리기 (층 간 계단만 표시)"""
        # 층 간 계단만 필터링 (같은 층 내 계단은 제외)
        inter_floor_stairs = {}
        for stairs_id, stairs_data in self.all_collected_stairs.items():
            connected_rooms = stairs_data.get('connected_rooms', [])
            if len(connected_rooms) != 2:
                continue
            
            room1_id, room2_id = connected_rooms[0], connected_rooms[1]
            room1 = self.rooms.get(str(room1_id)) if str(room1_id) in self.rooms else self.rooms.get(room1_id)
            room2 = self.rooms.get(str(room2_id)) if str(room2_id) in self.rooms else self.rooms.get(room2_id)
            
            if not room1 or not room2:
                continue
            
            # 층 간 계단만 포함 (서로 다른 층)
            if room1.get('floor_number') != room2.get('floor_number'):
                inter_floor_stairs[stairs_id] = stairs_data
        
        for floor_num, ax in self.floor_axes_map.items():
            ax.clear()
            
            # 방들 그리기 (층 간 계단만 표시, 이전 노드 제외)
            plot_rooms_on_ax_2d(ax, self.rooms, floor_num,
                              edges=[],  # 이전 엣지 제외
                              openings={},  # 이전 Opening 제외
                              doors={},  # 이전 Door 제외
                              stairs=inter_floor_stairs)  # 층 간 계단만 표시
            
            # 축 설정 (초기 설정과 동일한 전역 범위 사용)
            ax.set_xlim(self.global_xlim)
            ax.set_ylim(self.global_ylim)
            
            ax.set_aspect('equal')
            ax.grid(True, alpha=0.5, which='both')
            ax.set_title(f'Floor {floor_num}', fontsize=12, fontweight='bold')
            ax.set_xlabel('X (m)', fontsize=10)
            ax.set_ylabel('Y (m)', fontsize=10)
        
        self.fig.canvas.draw_idle()
    
    def on_key_press(self, event):
        """키보드 이벤트 처리
        
        - Enter: 선택된 방들 사이에 층 간 계단 생성/삭제 (토글)
        - Backspace: 완료 및 종료
        """
        if event.key == 'enter':
            self._create_inter_floor_stairs()
        elif event.key == 'backspace':
            self.finished = True
            print("\n✅ Finished inter-floor stairs connection.")
    
    def disconnect(self):
        """matplotlib 이벤트 핸들러 연결 해제"""
        if not self.cids:
            return
        try:
            for cid in self.cids:
                self.fig.canvas.mpl_disconnect(cid)
            self.cids = []
        except Exception as e:
            print(f"   (Error disconnecting event handlers: {e})")

# --- 객체-방 할당 함수 ---
def assign_nearest_room_to_objects(data):
    """parent_room이 None인 객체들에 가장 가까운 방을 할당
    
    각 객체의 location과 모든 방의 location을 비교하여
    유클리드 거리가 가장 가까운 방을 parent_room으로 할당합니다.
    
    Args:
        data: 로드된 씬 데이터 (dict)
    
    Returns:
        int: 할당된 객체의 개수
    """
    # rooms와 objects 추출
    if 'output' in data:
        rooms = data['output'].get('room', {})
        objects = data['output'].get('object', {})
    else:
        rooms = data.get('room', {})
        objects = data.get('object', {})
    
    if not rooms or not objects:
        return 0
    
    def euclidean_distance(pos1, pos2):
        """두 위치 간의 유클리드 거리 계산"""
        if pos1 is None or pos2 is None:
            return float('inf')
        if isinstance(pos1, list):
            pos1 = np.array(pos1)
        if isinstance(pos2, list):
            pos2 = np.array(pos2)
        return np.sqrt(np.sum((pos1 - pos2) ** 2))
    
    assigned_count = 0
    objects_without_room = []
    
    # parent_room이 None인 객체들 찾기
    for obj_id, obj_data in objects.items():
        parent_room_id = obj_data.get('parent_room')
        if parent_room_id is None:
            obj_location = obj_data.get('location')
            if obj_location is not None:
                objects_without_room.append({
                    'id': obj_id,
                    'data': obj_data,
                    'location': obj_location
                })
    
    if not objects_without_room:
        return 0
    
    print(f"\n📍 Found {len(objects_without_room)} objects without parent_room. Assigning nearest rooms...")
    
    # 각 객체에 대해 가장 가까운 방 찾기
    for obj_info in objects_without_room:
        obj_id = obj_info['id']
        obj_data = obj_info['data']
        obj_location = obj_info['location']
        obj_class = obj_data.get('class_', 'unknown')
        obj_id_val = obj_data.get('id', obj_id)
        
        # 모든 방과의 거리 계산
        min_distance = float('inf')
        nearest_room_id = None
        nearest_room_info = None
        
        for room_id, room_data in rooms.items():
            room_location = room_data.get('location')
            if room_location is None:
                continue
            
            distance = euclidean_distance(obj_location, room_location)
            if distance < min_distance:
                min_distance = distance
                nearest_room_id = room_id
                nearest_room_info = room_data
        
        # 가장 가까운 방 할당
        if nearest_room_id is not None:
            # room_id를 정수로 변환 (일관성 유지)
            if isinstance(nearest_room_id, str):
                try:
                    nearest_room_id = int(nearest_room_id)
                except ValueError:
                    pass
            
            obj_data['parent_room'] = nearest_room_id
            assigned_count += 1
            
            room_category = nearest_room_info.get('scene_category', 'unknown')
            room_floor = nearest_room_info.get('floor_number', 'unknown')
            print(f"  ✅ Object {obj_id_val} ({obj_class}) -> Room {nearest_room_id} ({room_category}, Floor {room_floor}), distance: {min_distance:.2f}m")
        else:
            print(f"  ⚠️  Object {obj_id_val} ({obj_class}): No valid room found (all rooms missing location)")
    
    if assigned_count > 0:
        print(f"\n✅ Assigned {assigned_count} objects to nearest rooms.")
    
    return assigned_count

# --- 메인 함수 ---
def main():
    """메인 함수: NPZ 파일 로드, 2D 평면도 생성, 엣지 수집, JSON 저장
    
    실행 흐름:
    1. NPZ 파일 로드
    2. 2D 평면도 생성 및 인터랙티브 엣지 수집 (Opening/Door/Stairs 노드 생성)
    3. 모든 엣지를 JSON 파일로 저장
    """
    # 현재 파일 위치 기준 상대 경로
    base_dir = Path(__file__).parent
    
    # 같은 디렉토리에서 NPZ 파일 찾기
    npz_files = list(base_dir.glob("*.npz"))
    
    if not npz_files:
        print(f"❌ No NPZ files found in {base_dir}")
        return
    
    # 여러 파일이 있으면 안내 메시지
    if len(npz_files) > 1:
        print(f"⚠️  Found {len(npz_files)} NPZ files. Processing the first one: {npz_files[0].name}")
        print(f"   Other files: {[f.name for f in npz_files[1:]]}")
    
    # 첫 번째 NPZ 파일만 처리 (단일 파일)
    npz_path = npz_files[0]
    npz_filename = npz_path.name
    
    print(f"📂 Processing NPZ file: {npz_filename}")
    
    print(f"📂 Loading NPZ file: {npz_path}")
    data = load_scene_data(npz_path)
    
    if 'output' in data:
        rooms = data['output'].get('room', {})
        building = data['output'].get('building', {})
    else:
        rooms = data.get('room', {})
        building = data.get('building', {})
    
    if not rooms:
        print("❌ No room data found in this scene.")
        return
    
    # 건물명 추출 (NPZ 파일의 building 데이터에서, 없으면 파일명에서)
    if building and 'name' in building:
        building_name = building['name']
    else:
        # 파일명에서 추출 (예: "3DSceneGraph_Coffeen.npz" -> "Coffeen")
        building_name = npz_filename.replace("3DSceneGraph_", "").replace(".npz", "")
        print(f"⚠️  Building name not found in NPZ file. Using filename: {building_name}")
    
    # 출력 파일 경로 (건물명으로 저장)
    output_json_path = base_dir / f"{building_name}.json"
    print(f"📝 Output JSON file: {output_json_path.name}")
    
    try:
        # 2D 평면도 생성 및 포인트 수집
        fig, ax, collected_points_final, collected_openings_final, collected_doors_final, collected_stairs_final = create_2d_topdown_view(
            npz_path, rooms, building, building_name=building_name, output_dir=base_dir
        )
        
        # 수집된 엣지 (staircase 자동 연결은 제거됨 - 이제 Stairs 노드로 직접 생성)
        all_edges = collected_points_final
        
        if not all_edges and not collected_openings_final and not collected_doors_final and not collected_stairs_final:
            print("\n🟡 No edges, openings, doors, or stairs collected. Exiting.")
            return
        
        # 수집된 엣지 정보로 connections 딕셔너리 생성 (door_input.py 방식)
        connections_output = {}
        conn_counter = 1
        
        # Opening 노드를 connections에 저장 (암시적 연결 방식)
        for opening_id, opening_data in collected_openings_final.items():
            conn_id = f"conn_{conn_counter}"
            conn_counter += 1
            # door_input.py와 동일한 구조: type='Opening', connected_rooms만 저장
            connections_output[conn_id] = {
                'type': 'Opening',
                'connected_rooms': opening_data.get('connected_rooms', [])
            }
        
        # Door 노드를 connections에 저장 (암시적 연결 방식)
        for door_id, door_data in collected_doors_final.items():
            conn_id = f"conn_{conn_counter}"
            conn_counter += 1
            # door_input.py와 동일한 구조: type='Door', connected_rooms만 저장
            connections_output[conn_id] = {
                'type': 'Door',
                'connected_rooms': door_data.get('connected_rooms', [])
            }
        
        # Stairs 노드를 connections에 저장 (암시적 연결 방식)
        for stairs_id, stairs_data in collected_stairs_final.items():
            conn_id = f"conn_{conn_counter}"
            conn_counter += 1
            # type='Stairs', connected_rooms만 저장
            connections_output[conn_id] = {
                'type': 'Stairs',
                'connected_rooms': stairs_data.get('connected_rooms', [])
            }
        
        # staircase 엣지(room-room 직접 연결)만 connections에 저장
        # Opening/Door 관련 엣지(room-opening, opening-room, room-door, door-room)는 저장하지 않음
        for edge_data in all_edges:
            node1_type = edge_data.get('node1_type', 'room')
            node2_type = edge_data.get('node2_type', 'room')
            
            # Opening/Door/Stairs와 관련된 엣지는 건너뛰기 (암시적 연결이므로)
            if node1_type in ['opening', 'door', 'stairs'] or node2_type in ['opening', 'door', 'stairs']:
                continue
            
            # room-room 직접 연결만 저장 (주로 staircase)
            conn_id = f"conn_{conn_counter}"
            conn_counter += 1
            node1_id = edge_data.get('node1_id')
            node2_id = edge_data.get('node2_id')
            connection_data = {
                'type': edge_data['type'],
                'connected_rooms': sorted([node1_id, node2_id])
            }
            connections_output[conn_id] = connection_data
        
        if 'output' not in data:
            data['output'] = {}
        data['output']['connections'] = connections_output
        
        # parent_room이 None인 객체들에 가장 가까운 방 할당
        assign_nearest_room_to_objects(data)
        
        try:
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"\n💾 JSON file with edge information saved: {output_json_path}")
        except Exception as e:
            print(f"\n❌ Error occurred while saving JSON file: {e}")
            return
        
        print("\n✨ All tasks completed!")
    
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()


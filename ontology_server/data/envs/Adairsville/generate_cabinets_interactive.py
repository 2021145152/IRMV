#!/usr/bin/env python3
"""
인터랙티브하게 수납장을 배치하는 스크립트

JSON 파일을 읽어서 지도를 표시하고, 사용자가 마우스 클릭으로
수납장을 배치할 방을 선택합니다.
"""

import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# 수납장의 기본 크기 (미터 단위) [width, depth, height]
CABINET_SIZE = [1.0, 0.6, 2.0]  # 수납장 크기

# 수납장의 affordance
CABINET_AFFORDANCES = ["open", "close", "store in", "take from", "place on"]


def get_room_color(scene_category):
    """방 종류(scene_category)에 따른 색상 반환"""
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


def plot_rooms_on_ax_2d(ax, rooms, floor_number, cabinets=None):
    """2D 평면도에 방과 수납장을 그리는 함수"""
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
    
    # 수납장 표시
    if cabinets:
        for cabinet_id, cabinet_data in cabinets.items():
            parent_room = cabinet_data.get('parent_room')
            if parent_room is None:
                continue
            
            room = rooms.get(str(parent_room)) if str(parent_room) in rooms else rooms.get(parent_room)
            if not room or room.get('floor_number') != floor_number:
                continue
            
            location = cabinet_data.get('location', room['location'])
            ax.plot(location[0], location[1], '^', 
                   color='blue', markersize=20, markeredgewidth=2, 
                   alpha=0.9, zorder=10)
            ax.text(location[0], location[1] + 0.5, 
                   f"Cabinet {cabinet_id}", 
                   fontsize=8, ha='center', va='bottom', 
                   color='blue', fontweight='bold')
    
    return plotted_items


def get_floor_numbers(rooms):
    """모든 방에서 층 번호를 추출하고 정렬"""
    floor_numbers = set()
    for room_data in rooms.values():
        floor_num = room_data.get('floor_number')
        if floor_num:
            floor_numbers.add(floor_num)
    try:
        sorted_floors = sorted(floor_numbers, key=lambda x: (int(x) if str(x).isdigit() else float('inf'), str(x)))
    except:
        sorted_floors = sorted(floor_numbers)
    return sorted_floors


def filter_rooms_by_floor(rooms, floor_number):
    """특정 층의 방들만 필터링"""
    filtered = {}
    for room_id, room_data in rooms.items():
        if room_data.get('floor_number') == floor_number:
            filtered[room_id] = room_data
    return filtered


class CabinetCollector:
    """2D 평면도에서 마우스 클릭으로 수납장 배치를 처리하는 클래스"""
    
    def __init__(self, fig, floor_axes_map, rooms, floor_numbers, existing_objects, max_object_id):
        self.fig = fig
        self.floor_axes_map = floor_axes_map  # {floor_num: ax}
        self.rooms = rooms
        self.floor_numbers = floor_numbers
        self.existing_objects = existing_objects
        self.max_object_id = max_object_id
        
        # 선택된 방
        self.selected_cabinet_room = None  # (room_id, room_data, floor_num)
        
        # 생성된 수납장
        self.collected_cabinets = {}
        
        # 하이라이트 마커들
        self.highlight_markers = []
        self.cabinet_markers = []
        
        # 완료 플래그
        self.finished = False
        
        # 다음 ID 계산 (기존 수납장 고려)
        existing_cabinet_ids = []
        
        for k in self.collected_cabinets.keys():
            try:
                existing_cabinet_ids.append(int(k))
            except (ValueError, TypeError):
                pass
        
        # 모든 기존 객체 ID 수집
        all_existing_ids = existing_cabinet_ids
        if all_existing_ids:
            current_max_id = max(max(all_existing_ids), max_object_id)
        else:
            current_max_id = max_object_id
        
        # 다음 ID는 연속된 번호로 할당
        self.next_cabinet_id = current_max_id + 1
        
        print("\n--- 🗄️  Cabinet Placement ---")
        print("1. Room Selection:")
        print("   - [Left Click Room]  : Select room for Cabinet")
        print("   - [Enter]            : Create Cabinet")
        print("2. Navigation:")
        print("   - [Backspace]        : Finish and save")
        print("3. Note:")
        print("   - Click a room to select it, then press Enter to create a cabinet")
        print("   - You can place multiple cabinets in different rooms")
        
        self.cids = []
        cid = fig.canvas.mpl_connect('button_press_event', self.onclick)
        self.cids.append(cid)
        cid = fig.canvas.mpl_connect('key_press_event', self.on_key_press)
        self.cids.append(cid)
    
    def _find_clicked_room(self, x, y, ax):
        """클릭한 위치가 어떤 방 안에 있는지 찾기"""
        # 어떤 층의 서브플롯인지 찾기
        clicked_floor = None
        for floor_num, floor_ax in self.floor_axes_map.items():
            if floor_ax == ax:
                clicked_floor = floor_num
                break
        
        if clicked_floor is None:
            return None, None, None
        
        overlapping_rooms = []
        
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
        
        if len(overlapping_rooms) == 1:
            room_id, room_data, _, _ = overlapping_rooms[0]
            return room_id, room_data, clicked_floor
        
        # 겹치는 방이 여러 개면 가장 가까운 방 선택
        min_distance = float('inf')
        closest_room = None
        
        for room_id, room_data, room_x, room_y in overlapping_rooms:
            distance = np.sqrt((x - room_x)**2 + (y - room_y)**2)
            if distance < min_distance:
                min_distance = distance
                closest_room = (room_id, room_data)
        
        if closest_room:
            return closest_room[0], closest_room[1], clicked_floor
        
        return None, None, None
    
    def _highlight_room(self, room_id, room_data, floor_num, color='yellow'):
        """선택된 방을 하이라이트 표시"""
        location = room_data['location']
        x, y = location[0], location[1]
        
        # 해당 층의 서브플롯 찾기
        ax = self.floor_axes_map.get(floor_num)
        if ax is None:
            return
        
        marker = ax.plot(x, y, 's', color=color, markersize=25, 
                        markeredgecolor='orange', markeredgewidth=3,
                        alpha=0.8, zorder=20)[0]
        self.highlight_markers.append(marker)
        self.fig.canvas.draw_idle()
    
    def _clear_highlights(self):
        """하이라이트 마커 제거"""
        for marker in self.highlight_markers:
            try:
                marker.remove()
            except:
                pass
        self.highlight_markers.clear()
        self.fig.canvas.draw_idle()
    
    def _redraw_cabinets(self):
        """수납장을 다시 그리기 (모든 층)"""
        # 기존 마커 제거
        for marker in self.cabinet_markers:
            try:
                marker.remove()
            except:
                pass
        self.cabinet_markers.clear()
        
        # 수납장 다시 그리기
        for cabinet_id, cabinet_data in self.collected_cabinets.items():
            parent_room = cabinet_data.get('parent_room')
            if parent_room is None:
                continue
            
            room = self.rooms.get(str(parent_room)) if str(parent_room) in self.rooms else self.rooms.get(parent_room)
            if not room:
                continue
            
            floor_num = room.get('floor_number')
            ax = self.floor_axes_map.get(floor_num)
            if ax is None:
                continue
            
            location = cabinet_data.get('location', room['location'])
            marker = ax.plot(location[0], location[1], '^', 
                           color='blue', markersize=20, markeredgewidth=2, 
                           alpha=0.9, zorder=10)[0]
            self.cabinet_markers.append(marker)
            text = ax.text(location[0], location[1] + 0.5, 
                         f"Cabinet {cabinet_id}", 
                         fontsize=8, ha='center', va='bottom', 
                         color='blue', fontweight='bold', zorder=11)
            self.cabinet_markers.append(text)
        
        self.fig.canvas.draw_idle()
    
    def onclick(self, event):
        """마우스 클릭 이벤트 처리"""
        if event.inaxes is None:
            return
        
        if event.button != 1:  # 왼쪽 클릭만 처리
            return
        
        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return
        
        clicked_room_id, clicked_room_data, clicked_floor = self._find_clicked_room(x, y, event.inaxes)
        
        if clicked_room_id is not None:
            if event.button == 1:  # 왼쪽 클릭: 수납장 방 선택
                self.selected_cabinet_room = (clicked_room_id, clicked_room_data, clicked_floor)
                print(f"🗄️  Selected room {clicked_room_id} (Floor {clicked_floor}) for Cabinet")
            
            # 하이라이트 업데이트
            self._clear_highlights()
            if self.selected_cabinet_room:
                self._highlight_room(self.selected_cabinet_room[0], self.selected_cabinet_room[1], 
                                    self.selected_cabinet_room[2], 'blue')
    
    def _create_cabinet(self):
        """선택된 방에 수납장 생성"""
        if not self.selected_cabinet_room:
            print("⚠️  Please select a room for cabinet")
            return
        
        cabinet_room_id, cabinet_room_data, cabinet_floor = self.selected_cabinet_room
        
        # room_id를 정수로 변환
        cabinet_room_id_int = int(cabinet_room_id) if isinstance(cabinet_room_id, str) else cabinet_room_id
        
        # 바닥 Z 좌표 계산
        cabinet_room_location = cabinet_room_data.get("location", [0, 0, 0])
        cabinet_room_size = cabinet_room_data.get("size", [1, 1, 1])
        cabinet_floor_z = cabinet_room_location[2] - cabinet_room_size[2] / 2
        
        # 수납장 위치 (방 중심)
        cabinet_location = cabinet_room_location.copy()
        cabinet_location[2] = cabinet_floor_z + CABINET_SIZE[2] / 2
        
        # 수납장 생성
        cabinet_id = self.next_cabinet_id
        cabinet_data = {
            "id": cabinet_id,
            "class_": "cabinet",
            "location": cabinet_location,
            "size": CABINET_SIZE,
            "parent_room": cabinet_room_id_int,
            "action_affordance": CABINET_AFFORDANCES,
            "material": "wood",
            "tactile_texture": "smooth",
            "visual_texture": "wooden",
            "floor_area": CABINET_SIZE[0] * CABINET_SIZE[1],
            "volume": CABINET_SIZE[0] * CABINET_SIZE[1] * CABINET_SIZE[2],
            "surface_coverage": 0.0,
            "is_open": False
        }
        
        # 저장
        self.collected_cabinets[str(cabinet_id)] = cabinet_data
        
        # ID 업데이트
        self.next_cabinet_id += 1
        
        print(f"✅ Created: Cabinet {cabinet_id} in Room {cabinet_room_id_int} (Floor {cabinet_floor})")
        
        # 선택 초기화
        self.selected_cabinet_room = None
        self._clear_highlights()
        
        # 다시 그리기
        self._redraw_cabinets()
    
    def on_key_press(self, event):
        """키보드 이벤트 처리"""
        if event.key == 'enter':
            self._create_cabinet()
        elif event.key == 'backspace':
            self.finished = True
            print("\n✅ Finished cabinet placement.")
    
    def disconnect(self):
        """이벤트 핸들러 연결 해제"""
        if not self.cids:
            return
        try:
            for cid in self.cids:
                self.fig.canvas.mpl_disconnect(cid)
            self.cids = []
        except Exception as e:
            print(f"   (Error disconnecting event handlers: {e})")


def create_interactive_cabinet_placement(json_path: Path):
    """인터랙티브하게 수납장을 배치 (모든 층을 한 화면에 표시)"""
    print(f"📂 Loading JSON file: {json_path}")
    
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    if "output" not in data:
        print("❌ Invalid JSON structure: 'output' key not found")
        return None
    
    output = data["output"]
    rooms = output.get("room", {})
    existing_objects = output.get("object", {})
    building = output.get("building", {})
    
    if not rooms:
        print("❌ No rooms found in JSON file")
        return None
    
    building_name = building.get("name", "Unknown")
    
    print(f"🏢 Found {len(rooms)} rooms")
    print(f"📦 Found {len(existing_objects)} existing objects")
    
    # 층 번호 추출
    floor_numbers = get_floor_numbers(rooms)
    if not floor_numbers:
        print("❌ Floor information not found.")
        return None
    
    print(f"\n🏢 Found floors: {', '.join(map(str, floor_numbers))}")
    print(f"Total {len(floor_numbers)} floor(s)")
    
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
    
    # 기존 객체 ID 중 최대값 찾기
    max_object_id = 0
    for obj_id_str in existing_objects.keys():
        try:
            obj_id = int(obj_id_str)
            max_object_id = max(max_object_id, obj_id)
        except (ValueError, TypeError):
            pass
    
    # 기존 수납장 찾기
    all_cabinets = {}
    for obj_id_str, obj_data in existing_objects.items():
        obj_class = obj_data.get('class_', '')
        if obj_class == 'cabinet':
            all_cabinets[obj_id_str] = obj_data
    
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
    
    # 각 층을 서브플롯에 그리기
    floor_axes_map = {}
    for idx, floor_num in enumerate(floor_numbers):
        ax = axes[idx]
        
        # 해당 층의 방들만 그리기
        plot_rooms_on_ax_2d(ax, rooms, floor_num, 
                           cabinets=all_cabinets)
        
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
    fig.suptitle(f'Cabinet Placement: {building_name}\n'
                f'[Left Click] Select Room | [Enter] Create Cabinet | [Backspace] Finish', 
                fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.draw()
    
    # ID 계산 (기존 객체 + 기존 수납장)
    current_max_id = max_object_id
    if all_cabinets:
        current_max_id = max(current_max_id, max(int(k) for k in all_cabinets.keys()))
    
    # CabinetCollector 생성
    collector = CabinetCollector(fig, floor_axes_map, rooms, floor_numbers, 
                                existing_objects, current_max_id)
    collector.collected_cabinets = all_cabinets
    collector._redraw_cabinets()
    
    print(f"\n📍 Place cabinets on any floor.")
    print(f"   Press Backspace to finish and save.")
    
    # 플롯 표시
    plt.show(block=False)
    
    # Backspace 키가 눌릴 때까지 대기
    import time
    while not collector.finished:
        plt.pause(0.1)
        time.sleep(0.1)
        if not plt.fignum_exists(fig.number):
            print("\n⚠️  Window closed.")
            break
    
    # 최종 수납장 저장
    all_cabinets = collector.collected_cabinets
    collector.disconnect()
    
    plt.close(fig)
    
    print(f"\n--- ✅ Cabinet Placement Complete ---")
    print(f"Total {len(all_cabinets)} cabinets collected")
    
    return all_cabinets


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="인터랙티브하게 수납장을 배치하는 스크립트"
    )
    parser.add_argument(
        "--json", "-j",
        type=str,
        help="JSON 파일 경로 (지정하지 않으면 현재 디렉토리의 첫 번째 JSON 파일 사용)"
    )
    
    args = parser.parse_args()
    
    # JSON 파일 경로 결정
    if args.json:
        json_path = Path(args.json)
        if not json_path.exists():
            print(f"❌ JSON file not found: {json_path}")
            return
    else:
        script_dir = Path(__file__).parent
        json_files = list(script_dir.glob("*.json"))
        if not json_files:
            print(f"❌ No JSON files found in {script_dir}")
            return
        json_path = json_files[0]
        if len(json_files) > 1:
            print(f"⚠️  Multiple JSON files found. Using: {json_path.name}")
    
    # JSON 파일 로드
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 인터랙티브 배치
    all_cabinets = create_interactive_cabinet_placement(json_path)
    
    if all_cabinets is None:
        return
    
    # 기존 객체에 추가
    output = data["output"]
    existing_objects = output.get("object", {})
    
    # 수납장 추가
    existing_objects.update(all_cabinets)
    output["object"] = existing_objects
    
    # 새 JSON 파일로 저장
    base_name = json_path.stem
    output_path = json_path.parent / f"{base_name}_with_cabinets.json"
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved to: {output_path}")
    print("\n✨ Done! You can now run json_to_dynamic_ttl.py to update TTL files.")


if __name__ == "__main__":
    main()


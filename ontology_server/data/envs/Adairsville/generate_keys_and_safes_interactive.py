#!/usr/bin/env python3
"""
인터랙티브하게 열쇠와 금고를 배치하는 스크립트

JSON 파일을 읽어서 지도를 표시하고, 사용자가 마우스 클릭으로
금고와 열쇠를 배치할 방을 선택합니다.
"""

import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# 금고와 열쇠의 기본 크기 (미터 단위) [width, depth, height]
SAFE_SIZE = [0.6, 0.5, 1.2]  # 금고 크기
KEY_SIZE = [0.05, 0.02, 0.15]  # 열쇠 크기

# 금고와 열쇠의 affordance
SAFE_AFFORDANCES = ["open", "close", "unlock with key", "lock", "store in", "take from"]
KEY_AFFORDANCES = ["pick up", "unlock", "lock", "use"]


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


def plot_rooms_on_ax_2d(ax, rooms, floor_number, safes=None, keys=None):
    """2D 평면도에 방과 금고/열쇠를 그리는 함수"""
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
    
    # 금고 표시
    if safes:
        for safe_id, safe_data in safes.items():
            parent_room = safe_data.get('parent_room')
            if parent_room is None:
                continue
            
            room = rooms.get(str(parent_room)) if str(parent_room) in rooms else rooms.get(parent_room)
            if not room or room.get('floor_number') != floor_number:
                continue
            
            location = safe_data.get('location', room['location'])
            ax.plot(location[0], location[1], 's', 
                   color='red', markersize=20, markeredgewidth=2, 
                   alpha=0.9, zorder=10)
            ax.text(location[0], location[1] + 0.5, 
                   f"Safe {safe_id}", 
                   fontsize=8, ha='center', va='bottom', 
                   color='red', fontweight='bold')
    
    # 열쇠 표시
    if keys:
        for key_id, key_data in keys.items():
            parent_room = key_data.get('parent_room')
            if parent_room is None:
                continue
            
            room = rooms.get(str(parent_room)) if str(parent_room) in rooms else rooms.get(parent_room)
            if not room or room.get('floor_number') != floor_number:
                continue
            
            location = key_data.get('location', room['location'])
            ax.plot(location[0], location[1], '*', 
                   color='gold', markersize=18, markeredgewidth=2, 
                   alpha=0.9, zorder=10)
            ax.text(location[0], location[1] + 0.5, 
                   f"Key {key_id}", 
                   fontsize=8, ha='center', va='bottom', 
                   color='gold', fontweight='bold')
    
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


class KeySafeCollector:
    """2D 평면도에서 마우스 클릭으로 금고와 열쇠 배치를 처리하는 클래스"""
    
    def __init__(self, fig, floor_axes_map, rooms, floor_numbers, existing_objects, max_object_id):
        self.fig = fig
        self.floor_axes_map = floor_axes_map  # {floor_num: ax}
        self.rooms = rooms
        self.floor_numbers = floor_numbers
        self.existing_objects = existing_objects
        self.max_object_id = max_object_id
        
        # 선택된 방들
        self.selected_safe_room = None  # (room_id, room_data, floor_num)
        self.selected_key_room = None  # (room_id, room_data, floor_num)
        
        # 생성된 금고와 열쇠
        self.collected_safes = {}
        self.collected_keys = {}
        
        # 하이라이트 마커들
        self.highlight_markers = []
        self.safe_markers = []
        self.key_markers = []
        
        # 완료 플래그
        self.finished = False
        
        # 다음 ID 계산 (기존 금고/열쇠 고려)
        existing_safe_ids = []
        existing_key_ids = []
        
        for k in self.collected_safes.keys():
            try:
                existing_safe_ids.append(int(k))
            except (ValueError, TypeError):
                pass
        
        for k in self.collected_keys.keys():
            try:
                existing_key_ids.append(int(k))
            except (ValueError, TypeError):
                pass
        
        # 모든 기존 객체 ID 수집
        all_existing_ids = existing_safe_ids + existing_key_ids
        if all_existing_ids:
            current_max_id = max(max(all_existing_ids), max_object_id)
        else:
            current_max_id = max_object_id
        
        # 다음 ID는 연속된 번호로 할당 (금고와 열쇠는 쌍으로 생성)
        self.next_safe_id = current_max_id + 1
        self.next_key_id = current_max_id + 2
        
        print("\n--- 🔐 Key and Safe Placement ---")
        print("1. Room Selection:")
        print("   - [Left Click Room]  : Select room for Safe")
        print("   - [Right Click Room] : Select room for Key")
        print("   - [Enter]            : Create Safe-Key pair")
        print("2. Navigation:")
        print("   - [Backspace]        : Finish and save")
        print("3. Note:")
        print("   - Select one room for safe, then one room for key")
        print("   - Press Enter to create the pair")
        print("   - Safe and key can be in the same or different rooms/floors")
        
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
    
    def _redraw_safes_and_keys(self):
        """금고와 열쇠를 다시 그리기 (모든 층)"""
        # 기존 마커 제거
        for marker in self.safe_markers + self.key_markers:
            try:
                marker.remove()
            except:
                pass
        self.safe_markers.clear()
        self.key_markers.clear()
        
        # 금고 다시 그리기
        for safe_id, safe_data in self.collected_safes.items():
            parent_room = safe_data.get('parent_room')
            if parent_room is None:
                continue
            
            room = self.rooms.get(str(parent_room)) if str(parent_room) in self.rooms else self.rooms.get(parent_room)
            if not room:
                continue
            
            floor_num = room.get('floor_number')
            ax = self.floor_axes_map.get(floor_num)
            if ax is None:
                continue
            
            location = safe_data.get('location', room['location'])
            marker = ax.plot(location[0], location[1], 's', 
                           color='red', markersize=20, markeredgewidth=2, 
                           alpha=0.9, zorder=10)[0]
            self.safe_markers.append(marker)
            text = ax.text(location[0], location[1] + 0.5, 
                         f"Safe {safe_id}", 
                         fontsize=8, ha='center', va='bottom', 
                         color='red', fontweight='bold', zorder=11)
            self.safe_markers.append(text)
        
        # 열쇠 다시 그리기
        for key_id, key_data in self.collected_keys.items():
            parent_room = key_data.get('parent_room')
            if parent_room is None:
                continue
            
            room = self.rooms.get(str(parent_room)) if str(parent_room) in self.rooms else self.rooms.get(parent_room)
            if not room:
                continue
            
            floor_num = room.get('floor_number')
            ax = self.floor_axes_map.get(floor_num)
            if ax is None:
                continue
            
            location = key_data.get('location', room['location'])
            marker = ax.plot(location[0], location[1], '*', 
                           color='gold', markersize=18, markeredgewidth=2, 
                           alpha=0.9, zorder=10)[0]
            self.key_markers.append(marker)
            text = ax.text(location[0], location[1] + 0.5, 
                         f"Key {key_id}", 
                         fontsize=8, ha='center', va='bottom', 
                         color='gold', fontweight='bold', zorder=11)
            self.key_markers.append(text)
        
        self.fig.canvas.draw_idle()
    
    def onclick(self, event):
        """마우스 클릭 이벤트 처리"""
        if event.inaxes is None:
            return
        
        if event.button not in [1, 3]:  # 왼쪽(1), 오른쪽(3) 클릭만 처리
            return
        
        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return
        
        clicked_room_id, clicked_room_data, clicked_floor = self._find_clicked_room(x, y, event.inaxes)
        
        if clicked_room_id is not None:
            if event.button == 1:  # 왼쪽 클릭: 금고 방 선택
                self.selected_safe_room = (clicked_room_id, clicked_room_data, clicked_floor)
                print(f"🔒 Selected room {clicked_room_id} (Floor {clicked_floor}) for Safe")
            elif event.button == 3:  # 오른쪽 클릭: 열쇠 방 선택
                self.selected_key_room = (clicked_room_id, clicked_room_data, clicked_floor)
                print(f"🗝️  Selected room {clicked_room_id} (Floor {clicked_floor}) for Key")
            
            # 하이라이트 업데이트
            self._clear_highlights()
            if self.selected_safe_room:
                self._highlight_room(self.selected_safe_room[0], self.selected_safe_room[1], 
                                    self.selected_safe_room[2], 'red')
            if self.selected_key_room:
                self._highlight_room(self.selected_key_room[0], self.selected_key_room[1], 
                                    self.selected_key_room[2], 'gold')
    
    def _create_safe_key_pair(self):
        """선택된 방들로부터 금고-열쇠 쌍 생성"""
        if not self.selected_safe_room or not self.selected_key_room:
            print("⚠️  Please select both a room for safe and a room for key")
            return
        
        safe_room_id, safe_room_data, safe_floor = self.selected_safe_room
        key_room_id, key_room_data, key_floor = self.selected_key_room
        
        # room_id를 정수로 변환
        safe_room_id_int = int(safe_room_id) if isinstance(safe_room_id, str) else safe_room_id
        key_room_id_int = int(key_room_id) if isinstance(key_room_id, str) else key_room_id
        
        # 바닥 Z 좌표 계산
        safe_room_location = safe_room_data.get("location", [0, 0, 0])
        safe_room_size = safe_room_data.get("size", [1, 1, 1])
        safe_floor_z = safe_room_location[2] - safe_room_size[2] / 2
        
        key_room_location = key_room_data.get("location", [0, 0, 0])
        key_room_size = key_room_data.get("size", [1, 1, 1])
        key_floor_z = key_room_location[2] - key_room_size[2] / 2
        
        # 금고 위치 (방 중심)
        safe_location = safe_room_location.copy()
        safe_location[2] = safe_floor_z + SAFE_SIZE[2] / 2
        
        # 열쇠 위치 (방 중심)
        key_location = key_room_location.copy()
        key_location[2] = key_floor_z + KEY_SIZE[2] / 2
        
        # 금고 생성
        safe_id = self.next_safe_id
        safe_data = {
            "id": safe_id,
            "class_": "safe",
            "location": safe_location,
            "size": SAFE_SIZE,
            "parent_room": safe_room_id_int,
            "action_affordance": SAFE_AFFORDANCES,
            "material": "metal",
            "tactile_texture": "smooth",
            "visual_texture": "metallic",
            "floor_area": SAFE_SIZE[0] * SAFE_SIZE[1],
            "volume": SAFE_SIZE[0] * SAFE_SIZE[1] * SAFE_SIZE[2],
            "surface_coverage": 0.0,
            "requires_key": self.next_key_id,
            "is_open": False,
            "is_locked": True  # requires_key가 있는 금고는 기본적으로 잠겨있음
        }
        
        # 열쇠 생성
        key_id = self.next_key_id
        key_data = {
            "id": key_id,
            "class_": "key",
            "location": key_location,
            "size": KEY_SIZE,
            "parent_room": key_room_id_int,
            "action_affordance": KEY_AFFORDANCES,
            "material": "metal",
            "tactile_texture": "smooth",
            "visual_texture": "metallic",
            "floor_area": KEY_SIZE[0] * KEY_SIZE[1],
            "volume": KEY_SIZE[0] * KEY_SIZE[1] * KEY_SIZE[2],
            "surface_coverage": 0.0,
            "unlocks": safe_id
        }
        
        # 저장
        self.collected_safes[str(safe_id)] = safe_data
        self.collected_keys[str(key_id)] = key_data
        
        # ID 업데이트 (다음 쌍을 위해)
        self.next_safe_id += 2
        self.next_key_id += 2
        
        print(f"✅ Created: Safe {safe_id} in Room {safe_room_id_int} (Floor {safe_floor}) <-> Key {key_id} in Room {key_room_id_int} (Floor {key_floor})")
        
        # 선택 초기화
        self.selected_safe_room = None
        self.selected_key_room = None
        self._clear_highlights()
        
        # 다시 그리기
        self._redraw_safes_and_keys()
    
    def on_key_press(self, event):
        """키보드 이벤트 처리"""
        if event.key == 'enter':
            self._create_safe_key_pair()
        elif event.key == 'backspace':
            self.finished = True
            print("\n✅ Finished key and safe placement.")
    
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


def create_interactive_key_safe_placement(json_path: Path):
    """인터랙티브하게 열쇠와 금고를 배치 (모든 층을 한 화면에 표시)"""
    print(f"📂 Loading JSON file: {json_path}")
    
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    if "output" not in data:
        print("❌ Invalid JSON structure: 'output' key not found")
        return None, None
    
    output = data["output"]
    rooms = output.get("room", {})
    existing_objects = output.get("object", {})
    building = output.get("building", {})
    
    if not rooms:
        print("❌ No rooms found in JSON file")
        return None, None
    
    building_name = building.get("name", "Unknown")
    
    print(f"🏢 Found {len(rooms)} rooms")
    print(f"📦 Found {len(existing_objects)} existing objects")
    
    # 층 번호 추출
    floor_numbers = get_floor_numbers(rooms)
    if not floor_numbers:
        print("❌ Floor information not found.")
        return None, None
    
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
    
    # 기존 금고와 열쇠 찾기
    all_safes = {}
    all_keys = {}
    for obj_id_str, obj_data in existing_objects.items():
        obj_class = obj_data.get('class_', '')
        if obj_class == 'safe':
            all_safes[obj_id_str] = obj_data
        elif obj_class == 'key':
            all_keys[obj_id_str] = obj_data
    
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
                           safes=all_safes, keys=all_keys)
        
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
    fig.suptitle(f'Key & Safe Placement: {building_name}\n'
                f'[Left Click] Safe Room | [Right Click] Key Room | [Enter] Create | [Backspace] Finish', 
                fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.draw()
    
    # ID 계산 (기존 객체 + 기존 금고/열쇠)
    current_max_id = max_object_id
    if all_safes:
        current_max_id = max(current_max_id, max(int(k) for k in all_safes.keys()))
    if all_keys:
        current_max_id = max(current_max_id, max(int(k) for k in all_keys.keys()))
    
    # KeySafeCollector 생성
    collector = KeySafeCollector(fig, floor_axes_map, rooms, floor_numbers, 
                                existing_objects, current_max_id)
    collector.collected_safes = all_safes
    collector.collected_keys = all_keys
    collector._redraw_safes_and_keys()
    
    print(f"\n📍 Place safes and keys on any floor.")
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
    
    # 최종 금고와 열쇠 저장
    all_safes = collector.collected_safes
    all_keys = collector.collected_keys
    collector.disconnect()
    
    plt.close(fig)
    
    print(f"\n--- ✅ Key & Safe Placement Complete ---")
    print(f"Total {len(all_safes)} safes collected")
    print(f"Total {len(all_keys)} keys collected")
    
    return all_safes, all_keys


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="인터랙티브하게 열쇠와 금고를 배치하는 스크립트"
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
    all_safes, all_keys = create_interactive_key_safe_placement(json_path)
    
    if all_safes is None or all_keys is None:
        return
    
    # 기존 객체에 추가
    output = data["output"]
    existing_objects = output.get("object", {})
    
    # 금고와 열쇠 추가
    existing_objects.update(all_safes)
    existing_objects.update(all_keys)
    output["object"] = existing_objects
    
    # 새 JSON 파일로 저장
    base_name = json_path.stem
    output_path = json_path.parent / f"{base_name}_with_keys_and_safes.json"
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved to: {output_path}")
    print("\n✨ Done! You can now run json_to_dynamic_ttl.py to update TTL files.")


if __name__ == "__main__":
    main()


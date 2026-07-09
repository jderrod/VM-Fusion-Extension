"""
Generate combined order JSON files from scenario CSVs.
Each order combines multiple components into a single input JSON.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(BASE_DIR), "temp")
os.makedirs(OUT_DIR, exist_ok=True)


def parse_bool(val):
    return val.strip() == "1" if val.strip() else None


def parse_float(val):
    val = val.strip()
    return float(val) if val else None


# ═══════════════════════════════════════════════════════════════════════════
# ORDER 1: IBUS123456 — 3X8X Door scenarios 10, 11, 43, 55, 57
# ═══════════════════════════════════════════════════════════════════════════
def build_order1():
    order_id = "IBUS123456"
    csv_path = os.path.join(BASE_DIR, "3X8X Door inputs & outputs v10 macro_enabled 2026_02_12(ValidationScenarios vFin ).csv")
    wanted = [10, 11, 43, 55, 57]

    lines = open(csv_path, "r", encoding="utf-8").readlines()
    data_lines = lines[8:]

    row_map = {}
    for line in data_lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 13:
            continue
        scenario = parts[0].strip()
        if not scenario.startswith("3X8X_DV_"):
            continue
        num = int(scenario.replace("3X8X_DV_", ""))
        if num in wanted:
            row_map[num] = parts

    doors = []
    for i, snum in enumerate(wanted):
        parts = row_map[snum]
        comp_id = "D" + str(i + 1)
        doors.append({
            "id": [comp_id, "string", "door ID"],
            "parameters": {
                "series_id": ["3082G.67P", "string", "series ID of the component"],
                "component_height": [float(parts[2]), "float", "height of the component in inches"],
                "component_width": [float(parts[3]), "float", "width of the component in inches"],
                "component_floor_clearance": [float(parts[4]), "float", "floor clearance of the component in inches"],
                "component_ceiling_clearance": [float(parts[5]), "float", "ceiling clearance of the component in inches."],
                "door_hinging_right": [parts[7].strip() == "1", "bool", "indicates whether the door is hinged on the right side when viewed from outside the stall"],
                "door_swinging_out": [parts[8].strip() == "1", "bool", "indicates whether the door swings outward into the bathroom"],
                "door_wall_post_hinging": [parts[9].strip() == "1", "bool", "indicates whether the door is hinged on a wall post"],
                "door_wall_post_latching": [parts[10].strip() == "1", "bool", "indicates whether the door latches to a wall post"],
                "door_wall_keep_latching": [parts[11].strip() == "1", "bool", "indicates whether the door latches to a wall keep"],
                "door_perp_stile_keeper": [parts[12].strip() == "1", "bool", "indicates whether the door latches on a perpendicular stile"],
                "floor_to_ceiling": [parts[6].strip() == "1", "bool", "indicates whether the stall is floor to ceiling or not"],
            }
        })
        print(f"  {comp_id} <- 3X8X_DV_{snum:04d}  (1-{comp_id}-{order_id})")

    order = {
        "order_id": [order_id, "string", "identifier for the order"],
        "doors": doors,
        "panels": [],
        "stiles": [],
    }
    path = os.path.join(OUT_DIR, order_id + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(order, f, indent=4)
    print(f"  -> {path}  ({len(doors)} doors)\n")


# ═══════════════════════════════════════════════════════════════════════════
# ORDER 2: IBUS456123 — 3X86 Stile scenarios 10, 11, 15, 16, 19, 22
# ═══════════════════════════════════════════════════════════════════════════
def build_order2():
    order_id = "IBUS456123"
    csv_path = os.path.join(BASE_DIR, "3X86 Stile inputs & outputs v08 macro_enabled 2026_03_12(ValidationScenario vFin).csv")
    wanted = [10, 11, 15, 16, 19, 22]

    lines = open(csv_path, "r", encoding="utf-8").readlines()
    data_lines = lines[3:]  # 3X86 data starts at line index 3

    row_map = {}
    for line in data_lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 17:
            continue
        scenario = parts[1].strip()
        if not scenario.startswith("3X86_SV_"):
            continue
        num = int(scenario.replace("3X86_SV_", ""))
        if num in wanted:
            row_map[num] = parts

    stiles = []
    for i, snum in enumerate(wanted):
        parts = row_map[snum]
        comp_id = "S" + str(i + 1)

        component_height = float(parts[3])
        component_width = float(parts[4])
        ld_height = parse_float(parts[5])
        ld_floor_clearance = parse_float(parts[6])
        ld_ceiling_clearance = parse_float(parts[7])
        rd_height = parse_float(parts[8])
        rd_floor_clearance = parse_float(parts[9])
        rd_ceiling_clearance = parse_float(parts[10])
        left_side_door = parts[11].strip() == "1"
        ld_hinging_right = parse_bool(parts[12])
        ld_swinging_out = parse_bool(parts[13])
        right_side_door = parts[14].strip() == "1"
        rd_hinging_right = parse_bool(parts[15])
        rd_swinging_out = parse_bool(parts[16])

        if not left_side_door:
            ld_height = None
            ld_floor_clearance = None
            ld_ceiling_clearance = None
            ld_hinging_right = None
            ld_swinging_out = None

        if not right_side_door:
            rd_height = None
            rd_floor_clearance = None
            rd_ceiling_clearance = None
            rd_hinging_right = None
            rd_swinging_out = None

        stiles.append({
            "id": [comp_id, "string", "stile ID"],
            "parameters": {
                "series_id": ["3086G.67P", "string", "series ID of the component"],
                "component_height": [component_height, "float", "height of the component in inches"],
                "component_width": [component_width, "float", "width of the component in inches"],
                "left_side_door": [left_side_door, "bool", "indicates whether there is a door on the stile's left side when viewed from the room"],
                "LD_hinging_right": [ld_hinging_right, "bool", "indicates whether the left side of the stile serves as the hinge stile for the adjacent door, rather than the keep stile"],
                "LD_height": [ld_height, "float", "height of the door on the left side of the stile"],
                "LD_floor_clearance": [ld_floor_clearance, "float", "floor clearance of the door on the left side of the stile"],
                "LD_ceiling_clearance": [ld_ceiling_clearance, "float", "ceiling clearance of the door on the left side of the stile"],
                "LD_swinging_out": [ld_swinging_out, "bool", "indicates whether the door on the left side of the stile swings outward into the bathroom"],
                "right_side_door": [right_side_door, "bool", "indicates whether there is a door on the stile's right side when viewed from the room"],
                "RD_hinging_right": [rd_hinging_right, "bool", "indicates whether the right side of the stile serves as the hinge stile for the adjacent door, rather than the keep stile"],
                "RD_height": [rd_height, "float", "height of the door on the right side of the stile"],
                "RD_floor_clearance": [rd_floor_clearance, "float", "floor clearance of the door on the right side of the stile"],
                "RD_ceiling_clearance": [rd_ceiling_clearance, "float", "ceiling clearance of the door on the right side of the stile"],
                "RD_swinging_out": [rd_swinging_out, "bool", "indicates whether the door on the right side of the stile swings outward into the bathroom"],
            }
        })
        print(f"  {comp_id} <- 3X86_SV_{snum:04d}  (1-{comp_id}-{order_id})")

    order = {
        "order_id": [order_id, "string", "identifier for the order"],
        "doors": [],
        "panels": [],
        "stiles": stiles,
    }
    path = os.path.join(OUT_DIR, order_id + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(order, f, indent=4)
    print(f"  -> {path}  ({len(stiles)} stiles)\n")


# ═══════════════════════════════════════════════════════════════════════════
# ORDER 3: IBUS789123 — 3X82 Stile scenarios 10, 11, 16, 17, 18, 20, 24, 49
# ═══════════════════════════════════════════════════════════════════════════
def build_order3():
    order_id = "IBUS789123"
    csv_path = os.path.join(BASE_DIR, "3X82 Stile inputs & outputs v15 macro_enabled 2026_02_26(ValidationScenarios vFin)(3).csv")
    wanted = [10, 11, 16, 17, 18, 20, 24, 49]

    lines = open(csv_path, "r", encoding="utf-8").readlines()
    data_lines = lines[2:]  # 3X82 data starts at line index 2

    row_map = {}
    for line in data_lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 15:
            continue
        scenario = parts[1].strip()
        if not scenario.startswith("3X82_SV_"):
            continue
        num = int(scenario.replace("3X82_SV_", ""))
        if num in wanted:
            row_map[num] = parts

    stiles = []
    for i, snum in enumerate(wanted):
        parts = row_map[snum]
        comp_id = "S" + str(i + 1)

        component_height = float(parts[3])
        component_width = float(parts[4])
        ld_height = parse_float(parts[5])
        ld_floor_clearance = parse_float(parts[6])
        rd_height = parse_float(parts[7])
        rd_floor_clearance = parse_float(parts[8])
        left_side_door = parts[9].strip() == "1"
        ld_hinging_right = parse_bool(parts[10])
        ld_swinging_out = parse_bool(parts[11])
        right_side_door = parts[12].strip() == "1"
        rd_hinging_right = parse_bool(parts[13])
        rd_swinging_out = parse_bool(parts[14])

        if not left_side_door:
            ld_height = None
            ld_floor_clearance = None
            ld_hinging_right = None
            ld_swinging_out = None

        if not right_side_door:
            rd_height = None
            rd_floor_clearance = None
            rd_hinging_right = None
            rd_swinging_out = None

        stiles.append({
            "id": [comp_id, "string", "stile ID"],
            "parameters": {
                "series_id": ["3082G.67P", "string", "series ID of the component"],
                "component_height": [component_height, "float", "height of the component in inches"],
                "component_width": [component_width, "float", "width of the component in inches"],
                "left_side_door": [left_side_door, "bool", "indicates whether there is a door on the stile's left side when viewed from the room"],
                "LD_hinging_right": [ld_hinging_right, "bool", "indicates whether the left side of the stile serves as the hinge stile for the adjacent door, rather than the keep stile"],
                "LD_height": [ld_height, "float", "height of the door on the left side of the stile"],
                "LD_floor_clearance": [ld_floor_clearance, "float", "floor clearance of the door on the left side of the stile"],
                "LD_swinging_out": [ld_swinging_out, "bool", "indicates whether the door on the left side of the stile swings outward into the bathroom"],
                "right_side_door": [right_side_door, "bool", "indicates whether there is a door on the stile's right side when viewed from the room"],
                "RD_hinging_right": [rd_hinging_right, "bool", "indicates whether the right side of the stile serves as the hinge stile for the adjacent door, rather than the keep stile"],
                "RD_height": [rd_height, "float", "height of the door on the right side of the stile"],
                "RD_floor_clearance": [rd_floor_clearance, "float", "floor clearance of the door on the right side of the stile"],
                "RD_swinging_out": [rd_swinging_out, "bool", "indicates whether the door on the right side of the stile swings outward into the bathroom"],
            }
        })
        print(f"  {comp_id} <- 3X82_SV_{snum:04d}  (1-{comp_id}-{order_id})")

    order = {
        "order_id": [order_id, "string", "identifier for the order"],
        "doors": [],
        "panels": [],
        "stiles": stiles,
    }
    path = os.path.join(OUT_DIR, order_id + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(order, f, indent=4)
    print(f"  -> {path}  ({len(stiles)} stiles)\n")


if __name__ == "__main__":
    print("=== Order 1: IBUS123456 (5 doors) ===")
    build_order1()
    print("=== Order 2: IBUS456123 (6 stiles, 3X86) ===")
    build_order2()
    print("=== Order 3: IBUS789123 (8 stiles, 3X82) ===")
    build_order3()
    print("Done!")

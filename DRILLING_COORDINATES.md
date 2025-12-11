# Drilling Coordinates Export

## Overview

The system automatically exports drilling coordinates for door and stile components as part of the order processing workflow. These coordinates specify:
- **X-axis positions** of individual hinge holes
- **Y-axis distance** from edge (single value per component)

- **Doors:** Always export drilling coordinates for all hinge holes + door_hinge_hole_y_dist
- **Stiles:** Conditionally export drilling based on boolean flags (left/right interior/exterior drilling) + stile_hinge_hole_y_dist

## Output File Format

### Individual Component Files
**Filename Convention:**
```
1-{ComponentID}-{OrderID}-drilling.json
```

**Example:** `1-D1-IBUS366574-drilling.json`

### Compiled Order File
**Filename Convention:**
```
{OrderID}-all-drilling.json
```

**Example:** `IBUS366574-all-drilling.json`

**Description:** Contains all drilling coordinates for all components (doors and stiles) in the order.

### File Location
Drilling coordinate files are saved in the G-code output folder alongside the NC programs:
```
M:\S2S File Test\output\gcode\{OrderID}\
├── 1-D1-IBUS366574-drilling.json       ← Individual door D1
├── 1-D2-IBUS366574-drilling.json       ← Individual door D2
├── 1-S1-IBUS366574-drilling.json       ← Individual stile S1 (if drilling required)
└── IBUS366574-all-drilling.json        ← Compiled (all components with drilling)
```

### Individual Component JSON Structure

```json
{
  "component_id": "D1",
  "order_id": "IBUS366574",
  "unit": "in",
  "description": "Hinge hole drilling coordinates (X and Y-axis positions)",
  "holes": {
    "door_hinge_hole_y_dist": {
      "value": 0.5,
      "unit": "in",
      "expression": "hinge_hole_x_dist",
      "comment": "Y-axis distance from edge to hinge holes"
    },
    "top_hinge_hole_1_x_value": {
      "value": 1.72,
      "unit": "in",
      "expression": "door_top_margin",
      "comment": "X-axis position of the door hinge hole"
    },
    "top_hinge_hole_2_x_value": {
      "value": 3.22,
      "unit": "in",
      "expression": "top_hinge_hole_1_x_value + hinge_hole_space",
      "comment": "X-axis position of the door hinge hole"
    },
    "mid_top_hinge_hole_1_x_value": {
      "value": 30.147,
      "unit": "in",
      "expression": "top_hinge_hole_1_x_value + inter_hinge_gap + mid_top_hinge_offset",
      "comment": "X-axis position of the door hinge hole"
    },
    "mid_top_hinge_hole_2_x_value": {
      "value": 31.647,
      "unit": "in",
      "expression": "mid_top_hinge_hole_1_x_value + hinge_hole_space",
      "comment": "X-axis position of the door hinge hole"
    },
    "mid_bottom_hinge_hole_1_x_value": {
      "value": 61.043,
      "unit": "in",
      "expression": "mid_top_hinge_hole_1_x_value + inter_hinge_gap + mid_bottom_hinge_offset",
      "comment": "X-axis position of the door hinge hole"
    },
    "mid_bottom_hinge_hole_2_x_value": {
      "value": 62.543,
      "unit": "in",
      "expression": "mid_bottom_hinge_hole_1_x_value + hinge_hole_space",
      "comment": "X-axis position of the door hinge hole"
    },
    "bottom_hinge_hole_1_x_value": {
      "value": 89.47,
      "unit": "in",
      "expression": "mid_bottom_hinge_hole_1_x_value + inter_hinge_gap + mid_top_hinge_offset",
      "comment": "X-axis position of the door hinge hole"
    },
    "bottom_hinge_hole_2_x_value": {
      "value": 90.97,
      "unit": "in",
      "expression": "bottom_hinge_hole_1_x_value + hinge_hole_space",
      "comment": "X-axis position of the door hinge hole"
    }
  }
}
```

### Compiled Order JSON Structure

```json
{
  "order_id": "IBUS366574",
  "unit": "in",
  "description": "Compiled drilling coordinates for all door components in this order",
  "component_count": 2,
  "components": [
    {
      "component_id": "D1",
      "order_id": "IBUS366574",
      "unit": "in",
      "description": "Hinge hole drilling coordinates (X and Y-axis positions)",
      "holes": {
        "door_hinge_hole_y_dist": { "value": 0.5, "unit": "in", ... },
        "top_hinge_hole_1_x_value": { "value": 1.72, "unit": "in", ... },
        "top_hinge_hole_2_x_value": { "value": 3.22, "unit": "in", ... },
        "mid_top_hinge_hole_1_x_value": { "value": 30.147, "unit": "in", ... },
        "mid_top_hinge_hole_2_x_value": { "value": 31.647, "unit": "in", ... },
        "mid_bottom_hinge_hole_1_x_value": { "value": 61.043, "unit": "in", ... },
        "mid_bottom_hinge_hole_2_x_value": { "value": 62.543, "unit": "in", ... },
        "bottom_hinge_hole_1_x_value": { "value": 89.47, "unit": "in", ... },
        "bottom_hinge_hole_2_x_value": { "value": 90.97, "unit": "in", ... }
      }
    },
    {
      "component_id": "D2",
      "order_id": "IBUS366574",
      "unit": "in",
      "description": "Hinge hole drilling coordinates (X and Y-axis positions)",
      "holes": {
        "door_hinge_hole_y_dist": { "value": 0.5, "unit": "in", ... },
        "top_hinge_hole_1_x_value": { "value": 1.72, "unit": "in", ... },
        "top_hinge_hole_2_x_value": { "value": 3.22, "unit": "in", ... },
        "mid_top_hinge_hole_1_x_value": { "value": 30.147, "unit": "in", ... },
        "mid_top_hinge_hole_2_x_value": { "value": 31.647, "unit": "in", ... },
        "mid_bottom_hinge_hole_1_x_value": { "value": 61.043, "unit": "in", ... },
        "mid_bottom_hinge_hole_2_x_value": { "value": 62.543, "unit": "in", ... },
        "bottom_hinge_hole_1_x_value": { "value": 89.47, "unit": "in", ... },
        "bottom_hinge_hole_2_x_value": { "value": 90.97, "unit": "in", ... }
      }
    }
  ]
}
```

**Note:** The compiled file contains the complete individual drilling data for each door component in the `components` array.

## Hole Parameters

### Y-Axis Distance Parameter
- `door_hinge_hole_y_dist` - Distance from edge (doors)
- `stile_hinge_hole_y_dist` - Distance from edge (stiles)

### Standard Door Configuration (3 Hinge Sets - 6 Holes)
- `top_hinge_hole_1_x_value` - First hole of top hinge
- `top_hinge_hole_2_x_value` - Second hole of top hinge
- `mid_bottom_hinge_hole_1_x_value` - First hole of middle hinge
- `mid_bottom_hinge_hole_2_x_value` - Second hole of middle hinge
- `bottom_hinge_hole_1_x_value` - First hole of bottom hinge
- `bottom_hinge_hole_2_x_value` - Second hole of bottom hinge

### Extended Door Configuration (4 Hinge Sets - 8 Holes)
All of the above, plus:
- `mid_top_hinge_hole_1_x_value` - First hole of mid-top hinge
- `mid_top_hinge_hole_2_x_value` - Second hole of mid-top hinge

## Stile Drilling Parameters

### Boolean Flags (Control Which Sides to Drill)
Stiles have 4 boolean parameters that determine if drilling is required:
- `left_interior_drilling` - Left side, interior facing
- `left_exterior_drilling` - Left side, exterior facing
- `right_interior_drilling` - Right side, interior facing
- `right_exterior_drilling` - Right side, exterior facing

**Logic:**
- If **ALL 4 flags are 0** → No drilling file created
- If **either left flag is true** → Export LEFT side parameters (LD_*)
- If **either right flag is true** → Export RIGHT side parameters (RD_*)
- Both sides can be true simultaneously

### Left Side Drilling Parameters (LD_*)
Exported when `left_interior_drilling` OR `left_exterior_drilling` is true:
- `LD_top_hinge_hole_1_x_value`
- `LD_top_hinge_hole_2_x_value`
- `LD_mid_top_hinge_hole_1_x_value`
- `LD_mid_top_hinge_hole_2_x_value`
- `LD_mid_bottom_hinge_hole_1_x_value`
- `LD_mid_bottom_hinge_hole_2_x_value`
- `LD_bottom_hinge_hole_1_x_value`
- `LD_bottom_hinge_hole_2_x_value`

### Right Side Drilling Parameters (RD_*)
Exported when `right_interior_drilling` OR `right_exterior_drilling` is true:
- `RD_top_hinge_hole_1_x_value`
- `RD_top_hinge_hole_2_x_value`
- `RD_mid_top_hinge_hole_1_x_value`
- `RD_mid_top_hinge_hole_2_x_value`
- `RD_mid_bottom_hinge_hole_1_x_value`
- `RD_mid_bottom_hinge_hole_2_x_value`
- `RD_bottom_hinge_hole_1_x_value`
- `RD_bottom_hinge_hole_2_x_value`

## Units

- **All coordinates are in inches**
- Values are rounded to 3 decimal places
- X-axis coordinates represent horizontal positions along component length
- Y-axis distance represents perpendicular distance from edge

## Component Types

Drilling coordinates are exported for:
- **Door components:** Component IDs starting with "D" (e.g., D1, D2, D3)
  - Always export all hinge hole parameters
- **Stile components:** Component IDs starting with "S" (e.g., S1, S2)
  - Conditionally export based on boolean drilling flags
  - May export left side, right side, both, or neither
- **Panel components:** Do not generate drilling coordinate files

## Integration with Workflow

Drilling coordinates are exported automatically during order processing:

1. **Parameter Application** - Parameters are applied to the door model
2. **Parameter Export** - Full parameters exported to CSV and JSON
3. **Drilling Export** - Drilling coordinates extracted and exported ← *NEW*
4. **CAM Regeneration** - Toolpaths are regenerated
5. **G-code Generation** - NC programs are created

The drilling file is created in the same folder as the NC program for easy reference.

## Using Drilling Coordinates

### Machine Setup
The drilling coordinate file can be:
- Imported into CNC control software
- Used for manual drill press operations
- Referenced for quality control inspection
- Integrated with automated drilling systems

### Coordinate System
- **X-Axis:** Horizontal positions along component length
- **Y-Axis:** Distance from edge (single value per component)
- **Units:** Inches

### Example Usage
For a door with:
- `door_hinge_hole_y_dist: 0.5 inches` - Distance from edge
- `top_hinge_hole_1_x_value: 1.72 inches` - Position along length

This represents drilling at 1.72" from top, 0.5" from edge.

## Troubleshooting

### No Drilling File Generated
**Possible causes:**
1. Component is not a door (panel or stile)
2. No hinge hole parameters found in model
3. Export failed (check logs)

**Solution:**
- Verify component type is "door"
- Check `output\logs\{OrderID}.log` for drilling export messages
- Ensure master door model has hinge hole parameters defined

### Missing Hole Parameters
**If some holes are missing:**
- The model may not have all hinge configurations defined
- Check if door uses 3-hinge (6 holes) or 4-hinge (8 holes) configuration
- Verify parameter names match expected format

### Incorrect Values
**If coordinates seem wrong:**
- Verify model parameters are correctly applied
- Check the expression field to understand how value is calculated
- Review full parameter export (`{ComponentID}_all_parameters.json`)

## Log Messages

Successful individual export:
```
D1: Drilling coordinates exported: Exported 8 drilling coordinates to 1-D1-IBUS366574-drilling.json (523 bytes)
```

Successful compiled file:
```
Created compiled drilling file: IBUS366574-all-drilling.json with 2 door(s)
```

Failed export:
```
D1: Drilling coordinate export failed: No drilling parameters found for D1
```

## Technical Details

### Implementation
- **Module:** `parameter_exporter.py`
- **Method:** `export_drilling_coordinates()`
- **Called from:** `order_processor.py` (doors and stiles)

### Parameter Extraction

**For All Components**, first searches for:
- `hinge_hole_x_dist` - Renamed to `door_hinge_hole_y_dist` or `stile_hinge_hole_y_dist` in output

**For Doors**, the system searches for:
- `top_hinge_hole_1_y_value` through `bottom_hinge_hole_2_y_value` (8 parameters in model)
- Renamed to `_x_value` in output JSON

**For Stiles**, the system:
1. Checks 4 boolean flags: `left_interior_drilling`, `left_exterior_drilling`, `right_interior_drilling`, `right_exterior_drilling`
2. If left flags are true, searches for: `LD_top_hinge_hole_1_y_value` through `LD_bottom_hinge_hole_2_y_value` (8 parameters in model)
3. If right flags are true, searches for: `RD_top_hinge_hole_1_y_value` through `RD_bottom_hinge_hole_2_y_value` (8 parameters in model)
4. May export 0, 8, or 16 hole parameters depending on flags
5. Renamed to `_x_value` in output JSON

**Note:** Parameters are renamed from `_y_value` (model) to `_x_value` (output) to indicate X-axis positions. The `hinge_hole_x_dist` parameter is renamed to `*_y_dist` in output.

Values are extracted from both user parameters and model parameters.

### Unit Conversion
- Fusion 360 stores all values internally in centimeters
- Export method converts to inches: `value_inches = value_cm / 2.54`
- Rounded to 3 decimal places for precision

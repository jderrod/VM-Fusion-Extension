# JSON Order Format Specification

## Overview

The Fusion Manufacturing Extension uses a structured JSON format to define manufacturing orders. Orders are organized by component type (panels, doors, stiles) with parameters in a type-safe format.

## File Location

Place your order JSON files in: `samples/JSON_9013830.json` (or any name you prefer)

The extension looks for `samples/JSON_9013830.json` by default.

## Structure

```json
{
  "order_id": [value, type, description],
  "panels": [array of panel components],
  "doors": [array of door components],
  "stiles": [array of stile components]
}
```

## Complete Example

```json
{
  "order_id": ["IBUS366574", "string", "identifier for the order"],
  "panels": [
    {
      "id": ["P1", "string", "panel ID"],
      "parameters": {
        "series_id": ["3082G.67P", "string", "series ID of the component"],
        "component_height": [96, "float", "height of the component in inches"],
        "component_width": [10.5, "float", "width of the component in inches"],
        "component_floor_clearance": [1, "float", "floor clearance in inches"],
        "panel_inline_front": [false, "bool", "front edge alignment"],
        "panel_inline_back": [false, "bool", "back edge alignment"]
      }
    }
  ],
  "doors": [
    {
      "id": ["D1", "string", "door ID"],
      "parameters": {
        "component_height": [96, "float", "height in inches"],
        "component_width": [34.375, "float", "width in inches"],
        "component_floor_clearance": [1, "float", "floor clearance in inches"],
        "door_hinging_right": [false, "bool", "right-side hinge"],
        "door_swinging_out": [true, "bool", "outward swing"],
        "door_wall_post_hinging": [false, "bool", "wall post hinge"],
        "door_wall_keep_latching": [false, "bool", "wall keep latch"]
      }
    }
  ],
  "stiles": [
    {
      "id": ["S1", "string", "stile ID"],
      "parameters": {
        "component_height": [97.75, "float", "height in inches"],
        "component_width": [3, "float", "width in inches"],
        "stile_left_side_door": [false, "bool", "door on left side"],
        "stile_left_side_hinging": [false, "bool", "left hinge stile"],
        "stile_left_side_door_height": [null, "float", "left door height"],
        "stile_right_side_door": [true, "bool", "door on right side"],
        "stile_right_side_hinging": [true, "bool", "right hinge stile"],
        "stile_right_side_door_height": [96, "float", "right door height"]
      }
    }
  ]
}
```

## Field Specifications

### Top Level

| Field | Format | Required | Description |
|-------|--------|----------|-------------|
| `order_id` | `[value, type, desc]` | Yes | Unique identifier for the order |
| `panels` | Array | No | Array of panel components |
| `doors` | Array | No | Array of door components |
| `stiles` | Array | No | Array of stile components |

**Note**: At least one component type array (`panels`, `doors`, or `stiles`) must be present.

### Component Object

Each component (panel, door, or stile) has:

| Field | Format | Required | Description |
|-------|--------|----------|-------------|
| `id` | `[value, type, desc]` | Yes | Component identifier (e.g., "P1", "D1", "S1") |
| `parameters` | Object | Yes | Dictionary of parameters to apply |

### Parameter Format

Each parameter uses the format: `[value, datatype, description]`

**Format**: `"parameter_name": [value, "datatype", "description"]`

**Elements**:
1. **value**: The actual value (number, string, boolean, or null)
2. **datatype**: Type specification (see Data Types below)
3. **description**: Human-readable description of what this parameter controls

### Data Types

| Type | Example | Notes |
|------|---------|-------|
| `"float"` | `[96.5, "float", "height"]` | Decimal numbers |
| `"int"` | `[10, "int", "count"]` | Whole numbers |
| `"bool"` | `[true, "bool", "enabled"]` | Boolean (true/false) |
| `"string"` | `["ABC", "string", "code"]` | Text values |
| `null` | `[null, "float", "optional"]` | Null values (converted to 0) |

### Boolean Conversion

Boolean values are automatically converted to Fusion 360 parameter format:
- `true` → `"1"`
- `false` → `"0"`

### Null Values

Null values are converted to `"0"` for numeric types.

## Parameter Matching

**Important**: The extension uses **auto-parameter matching**.

- Only parameters that **exist in your .f3d model** will be updated
- Parameters in JSON that don't exist in the model are **silently skipped**
- This allows you to include extra parameters in JSON for documentation

**Example**:
```json
// Your door model has: component_height, component_width, door_hinging_right
// JSON has: component_height, component_width, door_hinging_right, series_id

// Result: Updates the 3 parameters in the model
// Skips: series_id (not in model)
```

## Component Types

### Panels

Common panel parameters:
- `component_height` - Height in inches
- `component_width` - Width in inches
- `component_floor_clearance` - Floor clearance in inches
- `panel_inline_front` - Front edge alignment
- `panel_inline_back` - Back edge alignment

### Doors

Common door parameters:
- `component_height` - Height in inches
- `component_width` - Width in inches
- `component_floor_clearance` - Floor clearance in inches
- `door_hinging_right` - Right-side hinge
- `door_swinging_out` - Outward swing
- `door_wall_post_hinging` - Wall post hinge
- `door_wall_keep_latching` - Wall keep latch

### Stiles

Common stile parameters:
- `component_height` - Height in inches
- `component_width` - Width in inches
- `stile_left_side_door` - Door on left side
- `stile_left_side_hinging` - Left side as hinge stile
- `stile_left_side_door_height` - Height of left door
- `stile_right_side_door` - Door on right side
- `stile_right_side_hinging` - Right side as hinge stile
- `stile_right_side_door_height` - Height of right door

## Processing Order

Components are processed in this sequence:
1. **All panels** (using panel model from `inputs/panel/`)
2. **All doors** (using door model from `inputs/door/`)
3. **All stiles** (using stile model from `inputs/stile/`)

For each component:
1. Open/activate the appropriate model
2. Match JSON parameters to model parameters
3. Update matching parameters
4. Regenerate CAM toolpaths
5. Post-process and generate G-code

## Validation

The extension validates:
- ✅ JSON syntax is valid
- ✅ At least one component type array exists
- ✅ Each component has required fields (`id`, `parameters`)
- ✅ Parameter values match their declared types

## Tips

### 1. Document Your Parameters
Use the description field to explain what each parameter does:
```json
"component_height": [96, "float", "height of the component in inches"]
```

### 2. Include Extra Parameters
You can include parameters for documentation even if they're not in all models:
```json
"series_id": ["3082G.67P", "string", "series ID - used for reference only"]
```

### 3. Null for Optional Parameters
Use `null` for optional parameters that may not apply:
```json
"stile_left_side_door_height": [null, "float", "height of left door (if present)"]
```

### 4. Consistent Naming
Use consistent parameter names across component types:
- ✅ `component_height` (all types)
- ❌ `door_height`, `panel_height`, `stile_height`

### 5. Self-Documenting IDs
Use clear component IDs:
- ✅ `["P1", "string", "Front left panel"]`
- ❌ `["1", "string", "Component"]`

## Validation Errors

Common errors and solutions:

| Error | Cause | Solution |
|-------|-------|----------|
| "No component arrays found" | Missing panels/doors/stiles | Add at least one component array |
| "Missing 'parameters' field" | Component has no parameters | Add `parameters` object |
| "Invalid JSON syntax" | Malformed JSON | Validate JSON syntax |
| Parameter not updated | Parameter doesn't exist in model | Add parameter to model or remove from JSON |

## Example Workflow

1. **Create your order JSON**:
   - Copy `samples/JSON_9013830.json` as a template
   - Update `order_id` with your order number
   - Add your components with appropriate parameters

2. **Verify model parameters**:
   - Open each model in Fusion 360
   - Check Modify → Change Parameters
   - Ensure parameter names match JSON

3. **Run the order**:
   - Extension automatically matches parameters
   - Processes all components
   - Generates G-code

4. **Check the logs**:
   - Review `logs/pipeline_YYYYMMDD_HHMMSS.log`
   - Verify all parameters were updated
   - Check for any warnings or errors

## See Also

- **Setup Guide**: `QUICKSTART_V2.md`
- **Inputs Folder**: `docs/INPUTS_FOLDER_SETUP.md`
- **Sample JSON**: `samples/JSON_9013830.json`

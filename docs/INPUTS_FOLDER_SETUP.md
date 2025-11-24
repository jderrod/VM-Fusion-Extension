# Inputs Folder Setup Guide

## Overview

The inputs folder provides a centralized location for persistent model files (.f3d) that are used across multiple orders. Instead of specifying a model path for each component in your JSON, you set up your models once in the inputs folder, and they're automatically used for all future orders.

## Folder Structure

```
FusionExtension/
├── inputs/
│   ├── door/
│   │   └── [your-door-model.f3d]
│   ├── panel/
│   │   └── [your-panel-model.f3d]
│   └── stile/
│       └── [your-stile-model.f3d]
```

## Setup Instructions

### 1. Create the Inputs Folder

The inputs folder will be automatically created when you first run the extension with the new JSON format. It will be located at:

```
FusionExtension/inputs/
```

### 2. Add Your Model Files

Place one `.f3d` file in each component type folder:

- **Door model**: Place in `inputs/door/` 
  - Example: `inputs/door/PartitionDoor.f3d`
  
- **Panel model**: Place in `inputs/panel/`
  - Example: `inputs/panel/PartitionPanel.f3d`
  
- **Stile model**: Place in `inputs/stile/`
  - Example: `inputs/stile/PartitionStile.f3d`

### 3. Ensure Models Have Correct Parameters

Each model must have user parameters that match the parameter names in your JSON order files. For example:

**Door Model Parameters:**
- `component_height`
- `component_width`
- `component_floor_clearance`
- `door_hinging_right`
- `door_swinging_out`
- `door_wall_post_hinging`
- `door_wall_keep_latching`

**Panel Model Parameters:**
- `component_height`
- `component_width`
- `component_floor_clearance`
- `panel_inline_front`
- `panel_inline_back`

**Stile Model Parameters:**
- `component_height`
- `component_width`
- `stile_left_side_door`
- `stile_left_side_hinging`
- `stile_left_side_door_height`
- `stile_left_side_door_floor_clearance`
- `stile_left_side_door_swinging_out`
- `stile_right_side_door`
- `stile_right_side_hinging`
- `stile_right_side_door_height`
- `stile_right_side_door_floor_clearance`
- `stile_right_side_door_swinging_out`

## New JSON Format

The new JSON format (v2) uses the following structure:

```json
{
    "order_id": ["IBUS366574", "string", "identifier for the order"],
    "panels": [
        {
            "id": ["P1", "string", "panel ID"],
            "parameters": {
                "component_height": [96, "float", "height of the component in inches"],
                "component_width": [10.5, "float", "width of the component in inches"],
                ...
            }
        }
    ],
    "doors": [
        {
            "id": ["D1", "string", "door ID"],
            "parameters": {
                "component_height": [96, "float", "height of the component in inches"],
                ...
            }
        }
    ],
    "stiles": [
        {
            "id": ["S1", "string", "stile ID"],
            "parameters": {
                "component_height": [97.75, "float", "height of the component in inches"],
                ...
            }
        }
    ]
}
```

### Parameter Format

Each parameter value is stored as a list with three elements:
1. **Value**: The actual parameter value (number, string, or boolean)
2. **Datatype**: The data type ("string", "float", "int", "bool")
3. **Description**: A human-readable description of the parameter

Examples:
- `[96, "float", "height of the component in inches"]`
- `[true, "bool", "indicates whether the door is hinged on the right side"]`
- `["3082G.67P", "string", "series ID of the component"]`

## How It Works

1. **Order Processing**: When you run an order, the system reads the JSON file
2. **Component Iteration**: It processes panels first, then doors, then stiles
3. **Model Switching**: For each component type, it opens/activates the corresponding model from the inputs folder
4. **Parameter Application**: It applies the parameters from the JSON to the active model
5. **Toolpath Regeneration**: CAM toolpaths are regenerated based on the new parameters
6. **G-code Generation**: Post-processing generates the G-code files

## Benefits

- **Persistent Models**: Set up models once, use them for all orders
- **Automatic Model Switching**: The system automatically switches between Door, Panel, and Stile models
- **Type Safety**: The datatype field ensures parameters are correctly formatted
- **Self-Documenting**: Descriptions provide context for each parameter
- **Modular Design**: Easy to update or replace individual model files

## Troubleshooting

### "No model configured" error

- Check that you have placed a .f3d file in the appropriate inputs subfolder
- Ensure the file has the .f3d extension
- Verify the folder names are exactly: `door`, `panel`, `stile` (lowercase)

### "Parameter not found" error

- Open your model in Fusion 360
- Check the "Modify" > "Change Parameters" dialog
- Ensure all parameter names in your JSON exactly match the user parameter names in the model
- Parameter names are case-sensitive

### Model not opening

- Ensure the .f3d file is not corrupted
- Try opening the file manually in Fusion 360 first
- Check that the file path doesn't contain special characters

## Next Steps

See `samples/JSON_9013830.json` for a complete example of the new JSON format.

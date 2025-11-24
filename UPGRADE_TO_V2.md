# Upgrade Guide: Modular Order Processing (v2)

## Overview

This upgrade introduces a modular architecture for processing manufacturing orders with persistent model storage. Instead of specifying model paths in each JSON order, you now maintain a set of reusable models that are automatically used for all orders.

## Key Changes

### 1. **Persistent Model Storage**

- **New `inputs/` folder** with subfolders for `door/`, `panel/`, and `stile/`
- Drop your `.f3d` model files once, use them for all future orders
- Automatic model switching during order processing

### 2. **New JSON Format**

The JSON structure has changed to support the new architecture:

**Old Format (v1):**
```json
{
  "orderId": "ORDER-001",
  "components": [
    {
      "componentId": "door-001",
      "fusionModelPath": "F360MT - PartitionDoor Rev 1",
      "parameters": {
        "component_height": "84 in",
        "component_width": "30 in"
      }
    }
  ]
}
```

**New Format (v2):**
```json
{
  "order_id": ["IBUS366574", "string", "identifier for the order"],
  "panels": [{
    "id": ["P1", "string", "panel ID"],
    "parameters": {
      "component_height": [96, "float", "height in inches"],
      "component_width": [10.5, "float", "width in inches"]
    }
  }],
  "doors": [{
    "id": ["D1", "string", "door ID"],
    "parameters": {
      "component_height": [96, "float", "height in inches"]
    }
  }],
  "stiles": [{
    "id": ["S1", "string", "stile ID"],
    "parameters": {
      "component_height": [97.75, "float", "height in inches"]
    }
  }]
}
```

### 3. **Enhanced Parameter Format**

Parameters now include type information and descriptions:

```json
"parameter_name": [value, datatype, description]
```

- **value**: The actual parameter value (number, string, bool)
- **datatype**: Type specification ("float", "int", "bool", "string")
- **description**: Human-readable description

Examples:
- `[96, "float", "height of the component in inches"]`
- `[true, "bool", "indicates right hinge"]`
- `["3082G.67P", "string", "series ID"]`

### 4. **Component Type Organization**

Orders are now organized by component type:
- `panels[]` - Array of panel components
- `doors[]` - Array of door components
- `stiles[]` - Array of stile components

Processing happens in order: panels → doors → stiles

## New Files

### Core Modules
- **`src/model_manager.py`** - Manages persistent model storage and retrieval
- **`setup_inputs_folder.ps1`** - PowerShell script to initialize folder structure
- **`docs/INPUTS_FOLDER_SETUP.md`** - Detailed setup guide

### Updated Files
- **`src/order_processor.py`** - Added `process_order_v2()` and `process_component_v2()`
- **`src/parameter_manager.py`** - Added `update_parameters_from_json()` to handle new format
- **`src/command_handler.py`** - Auto-detects JSON format and uses appropriate processor

## Setup Instructions

### Step 1: Initialize Inputs Folder

Run the setup script:

```powershell
.\setup_inputs_folder.ps1
```

This creates:
```
inputs/
├── door/
├── panel/
└── stile/
```

### Step 2: Add Your Models

Place one `.f3d` file in each subfolder:

```
inputs/
├── door/
│   └── YourDoorModel.f3d
├── panel/
│   └── YourPanelModel.f3d
└── stile/
    └── YourStileModel.f3d
```

### Step 3: Verify Model Parameters

Open each model and verify it has user parameters matching your JSON:

**Required Door Parameters:**
- component_height, component_width, component_floor_clearance
- door_hinging_right, door_swinging_out
- door_wall_post_hinging, door_wall_keep_latching

**Required Panel Parameters:**
- component_height, component_width, component_floor_clearance
- panel_inline_front, panel_inline_back

**Required Stile Parameters:**
- component_height, component_width
- stile_left_side_door, stile_left_side_hinging
- stile_left_side_door_height, stile_left_side_door_floor_clearance
- stile_left_side_door_swinging_out
- stile_right_side_door, stile_right_side_hinging
- stile_right_side_door_height, stile_right_side_door_floor_clearance
- stile_right_side_door_swinging_out

### Step 4: Use New JSON Format

Update your JSON orders to use the v2 format (see `samples/JSON_9013830.json` for complete example).

## Backward Compatibility

The extension maintains backward compatibility:
- Old JSON format (v1) still works with `sample_order.json`
- New JSON format (v2) automatically detected and processed with `JSON_9013830.json`
- Command handler auto-detects format and routes to appropriate processor

## Benefits

### ✓ **Modularity**
- Models maintained separately from orders
- Easy to update or replace models without changing JSON

### ✓ **Type Safety**
- Explicit data types prevent parameter formatting errors
- Automatic conversion of booleans, floats, integers

### ✓ **Self-Documenting**
- Parameter descriptions embedded in JSON
- Clear understanding of what each parameter controls

### ✓ **Organized Processing**
- Components processed by type (panels → doors → stiles)
- Automatic model switching for each component type

### ✓ **Scalability**
- Process any number of panels, doors, and stiles in one order
- Models reused across unlimited orders

## Workflow Example

1. **Setup (one time)**
   ```powershell
   .\setup_inputs_folder.ps1
   # Copy your .f3d models to inputs subfolders
   ```

2. **Create Order JSON**
   ```json
   {
     "order_id": ["ORDER-123", "string", "Order identifier"],
     "panels": [...],
     "doors": [...],
     "stiles": [...]
   }
   ```

3. **Run Order**
   - Extension auto-detects v2 format
   - Opens panel model, applies parameters, regenerates toolpaths
   - Opens door model, applies parameters, regenerates toolpaths
   - Opens stile model, applies parameters, regenerates toolpaths
   - Generates G-code for all components

## Migration from v1 to v2

If you have existing v1 JSON orders, you'll need to convert them:

1. Reorganize `components[]` into `panels[]`, `doors[]`, `stiles[]`
2. Remove `fusionModelPath` (now handled by inputs folder)
3. Convert parameter values from strings to `[value, type, description]` format
4. Update `orderId` to `order_id` with same format

Example conversion tool could be created if needed.

## Troubleshooting

### "No model configured" Error
- Ensure you've placed .f3d files in inputs subfolders
- Check folder names are exactly: `door`, `panel`, `stile` (lowercase)
- Run `.\setup_inputs_folder.ps1` to verify setup

### Parameter Not Found
- Open your model in Fusion 360
- Check "Modify" > "Change Parameters"
- Ensure parameter names exactly match (case-sensitive)
- Verify parameter is a "User Parameter" not "Model Parameter"

### Type Conversion Errors
- Check datatype field matches the actual value type
- Use "float" for decimals, "int" for whole numbers, "bool" for true/false
- For null values, use datatype but set value to null (converts to 0)

## API Reference

### ModelManager

```python
model_mgr = ModelManager(app, inputs_folder="/path/to/inputs")

# Check if model is available
if model_mgr.is_model_available('door'):
    # Open the model
    success, doc, msg = model_mgr.open_model('door')
```

### ParameterManager

```python
param_mgr = ParameterManager(design)

# Update parameters from v2 JSON format
results = param_mgr.update_parameters_from_json(parameters_dict)
```

### OrderProcessor

```python
processor = OrderProcessor(app, inputs_folder="/path/to/inputs")

# Process v2 format order
success, message = processor.process_order_v2(order_file_path)
```

## Support

For questions or issues:
1. Check `docs/INPUTS_FOLDER_SETUP.md` for detailed instructions
2. Review sample JSON: `samples/JSON_9013830.json`
3. Run `.\setup_inputs_folder.ps1` to verify folder structure
4. Check logs in `logs/` folder for debugging information

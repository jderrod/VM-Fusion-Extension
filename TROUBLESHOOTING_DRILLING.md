# Troubleshooting Drilling Coordinate Export

## Issue: Drilling files not being generated

### What to Check:

#### 1. Check the Log File
After running an order, check the log file:
```
M:\S2S File Test\output\logs\{OrderID}.log
```

Look for these messages:

**Drilling parameter search:**
```
D1: Searching for drilling parameters in design
D1: Output path: M:\S2S File Test\output\gcode\IBUS366574\1-D1-IBUS366574-drilling.json
D1: Total parameters in design: XXX
```

**If parameters are found:**
```
D1: Found drilling parameter: top_hinge_hole_1_y_value
D1: Added top_hinge_hole_1_x_value = 1.72 in
D1: Found drilling parameter: top_hinge_hole_2_y_value
D1: Added top_hinge_hole_2_x_value = 3.22 in
...
D1: Drilling coordinates exported: Exported 8 drilling coordinates to 1-D1-IBUS366574-drilling.json (523 bytes)
```

**If NO parameters are found:**
```
D1: No drilling parameters found! Searched for: top_hinge_hole_1_y_value, top_hinge_hole_2_y_value, mid_top_hinge_hole_1_y_value...
D1: Drilling coordinate export failed: No drilling parameters found for D1
```

**Compiled file:**
```
Created compiled drilling file: IBUS366574-all-drilling.json with 2 door(s)
```

#### 2. Check Output Directory
The drilling files should be here:
```
M:\S2S File Test\output\gcode\{OrderID}\
```

Look for:
- Individual files: `1-D1-IBUS366574-drilling.json`
- Compiled file: `IBUS366574-all-drilling.json`

#### 3. Check if Door Parameters Exist
Open the all parameters file:
```
M:\S2S File Test\output\parameters\{OrderID}\D1_all_parameters.json
```

Search for these parameter names:
- `top_hinge_hole_1_y_value`
- `top_hinge_hole_2_y_value`
- `mid_top_hinge_hole_1_y_value`
- `mid_top_hinge_hole_2_y_value`
- `mid_bottom_hinge_hole_1_y_value`
- `mid_bottom_hinge_hole_2_y_value`
- `bottom_hinge_hole_1_y_value`
- `bottom_hinge_hole_2_y_value`

**These should be in either:**
- `user_parameters` section
- `model_parameters` section

If they're NOT in the all_parameters.json file, then the door model doesn't have these parameters defined.

#### 4. Check Component Type
Drilling coordinates are ONLY exported for door components.

Look in the log for:
```
Processing door 1/2: D1
```

If it says "panel" or "stile", drilling files won't be created.

## Common Issues:

### Issue 1: Parameters Don't Exist in Door Model
**Symptom:** Log says "No drilling parameters found"

**Solution:** 
- The master door model needs to have parameters named:
  - `top_hinge_hole_1_y_value`
  - `top_hinge_hole_2_y_value`
  - etc.
- These must be defined in the door model at: `M:\S2S File Test\input\door\`
- Check the door model in Fusion 360 → Modify → Change Parameters
- Make sure these parameters exist and have values

### Issue 2: Wrong Component Type
**Symptom:** No drilling export attempted

**Solution:**
- Verify the order JSON has components under `"doors": [...]`
- Check component ID starts with "D" (e.g., D1, D2)

### Issue 3: Directory Doesn't Exist
**Symptom:** Files not created but log shows success

**Solution:**
- Check if directory exists: `M:\S2S File Test\output\gcode\{OrderID}\`
- The code should auto-create it, but check for permission issues

### Issue 4: Parameters Are There But Wrong Names
**Symptom:** All parameters export has drilling values but drilling export fails

**Solution:**
- Check the exact parameter names in the all_parameters.json
- They MUST be exactly: `top_hinge_hole_1_y_value` (not x_value, not Y_value, etc.)
- Case sensitive!

## Quick Test:

1. Run a door order
2. Immediately check: `M:\S2S File Test\output\logs\{OrderID}.log`
3. Search for: "Searching for drilling parameters"
4. Read the next 10-20 lines to see what was found
5. Report back what you see

## Expected Behavior:

For an order with 2 doors (D1, D2):

**Files created:**
```
M:\S2S File Test\output\gcode\IBUS366574\
├── 1-D1-IBUS366574-drilling.json       (Individual D1)
├── 1-D2-IBUS366574-drilling.json       (Individual D2)
└── IBUS366574-all-drilling.json        (Compiled)
```

**Log entries:**
```
D1: Searching for drilling parameters in design
D1: Total parameters in design: 150
D1: Found drilling parameter: top_hinge_hole_1_y_value
D1: Added top_hinge_hole_1_x_value = 1.72 in
... (8 parameters total)
D1: Drilling coordinates exported: Exported 8 drilling coordinates to 1-D1-IBUS366574-drilling.json (523 bytes)

D2: Searching for drilling parameters in design
... (same for D2)

Created compiled drilling file: IBUS366574-all-drilling.json with 2 door(s)
```

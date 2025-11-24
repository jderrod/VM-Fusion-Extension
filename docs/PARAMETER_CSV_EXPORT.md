# Parameter CSV Export Feature

## Overview

Automatically exports all model parameters to a CSV file for each component after parameters are applied. This provides a complete record of all parameter values used to generate each door.

## When It Happens

```
1. Parameters applied (e.g., 84" x 30")
   ↓
2. 3D Model exported (door-panel-001.step)
   ↓
3. Parameters exported to CSV ← NEW STEP
   ↓
4. Toolpaths regenerated
   ↓
5. G-code generated
```

## Export Configuration

### Output Directory
```
C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\Parameters
```

### File Format
**CSV (Comma-Separated Values)**
- Opens in Excel, Google Sheets, or any text editor
- Easy to parse programmatically
- Human-readable format

### File Naming
Files are named using the component ID:
- `door-panel-001_all_parameters.csv`
- `door-panel-002_all_parameters.csv`
- `door-panel-003_all_parameters.csv`

## CSV Structure

### Columns

| Column | Description | Example |
|--------|-------------|---------|
| **Type** | Parameter type (User/Model) | `User` |
| **Parameter Name** | Name of the parameter | `component_height` |
| **Value** | Numeric value | `96.0` |
| **Unit** | Unit of measurement | `in` |
| **Expression** | Full expression | `84 in` |
| **Comment** | Parameter description | `Height of the component` |

### Example CSV Content

```csv
Type,Parameter Name,Value,Unit,Expression,Comment
User,component_height,96.0,in,96 in,
User,component_width,30.0,in,30 in,
User,component_floor_clearance,2.0,in,2 in,
User,door_hinging_right,0.0,,0,
User,door_swinging_out,0.0,,0,
User,door_wall_post_hinging,1.0,,1,
User,door_wall_keep_latching,1.0,,1,
Model,door_thickness,0.75,in,0.75 in,
Model,door_top_margin,1.72,in,1.72 in,
Model,notching_x,0.4414,in,0.4414 in,
...
```

## What Gets Exported

### User Parameters (Applied from JSON)
- All parameters you specified in the order JSON
- With their applied values
- **Type: "User"**

### Model Parameters (Computed)
- All other parameters in the model
- Including formulas and dependencies
- **Type: "Model"**

Example:
```
component_height_limited = min(96 in; max(72 in; component_height))
door_bottom_margin = 1.72 in + if(...; notching_z; 0 in)
```

## Example Output

After processing 3 doors:

### Parameters Directory
```
C:\...\Parameters\
  door-panel-001_all_parameters.csv  (84" x 30" door)
  door-panel-002_all_parameters.csv  (96" x 36" door)
  door-panel-003_all_parameters.csv  (72" x 24" door)
```

### Models Directory
```
C:\...\Models\
  door-panel-001.step
  door-panel-002.step
  door-panel-003.step
```

### NC Programs Directory
```
C:\...\NC Programs\
  1001.nc  (door-panel-001)
  1002.nc  (door-panel-002)
  1003.nc  (door-panel-003)
```

## Use Cases

### 1. Manufacturing Documentation
Complete record of parameters used for each door:
- Customer orders 84" x 30" door
- CSV proves exact parameters used
- Archive with order records

### 2. Quality Control
- Compare manufactured part to CSV parameters
- Verify dimensions match order
- Audit trail for compliance

### 3. Data Analysis
- Import CSVs into database
- Analyze parameter trends
- Generate reports on door configurations

### 4. Troubleshooting
- If a door has issues, check the CSV
- See all computed parameter values
- Verify formulas evaluated correctly

### 5. Customer Documentation
- Send CSV with NC files
- Customer sees exact specifications
- Transparent parameter documentation

## Success Message

After successful processing:

```
door-panel-001: Processing complete!

✓ Updated 7 parameter(s)
✓ Exported 3D model: door-panel-001.step
✓ Exported parameters: door-panel-001_all_parameters.csv  ← NEW!
✓ Regenerated 2 CAM setup(s)
✓ Generated 1/2 NC program(s):
    • hinge_side: 1001.nc

Output: C:\...\NC Programs
```

## Logs

Export is logged in detail:

```
INFO - door-panel-001: Parameters exported: Exported 44 parameters to door-panel-001_all_parameters.csv (2156 bytes)
```

Or if it fails:

```
WARNING - door-panel-001: Parameter export failed: No parameters found
```

## Module: parameter_exporter.py

**Location**: `src/parameter_exporter.py`  
**Lines**: ~150 lines  
**Class**: `ParameterExporter`

**Key Methods**:
- `export_parameters()` - Export user parameters only
- `export_all_parameters()` - Export user + model parameters (default)
- `get_output_directory()` - Get configured path

## Configuration Options

### Change Output Directory

Edit `src/order_processor.py`, line 284:

```python
params_output_dir = r'C:\Your\Custom\Path\Parameters'
```

### Export User Parameters Only

To export only the parameters you applied (not computed ones):

```python
# In order_processor.py, line 288, change:
param_export_success, param_export_msg, param_export_path = param_exporter.export_parameters(design, comp_id)
```

This will export only:
- component_height
- component_width
- component_floor_clearance
- door_hinging_right
- door_swinging_out
- door_wall_post_hinging
- door_wall_keep_latching

## Opening CSV Files

### In Excel
1. Double-click the CSV file
2. Opens directly in Excel
3. All columns formatted

### In Google Sheets
1. File → Import
2. Select the CSV
3. Auto-formats columns

### In Python
```python
import pandas as pd
df = pd.read_csv('door-panel-001_all_parameters.csv')
print(df)
```

### In PowerShell
```powershell
Import-Csv "door-panel-001_all_parameters.csv" | Format-Table
```

## Verification

**Check if CSVs are being created**:

```powershell
Get-ChildItem "C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\Parameters" -Filter *.csv | Sort-Object LastWriteTime -Descending
```

**View a CSV**:

```powershell
Get-Content "C:\...\Parameters\door-panel-001_all_parameters.csv" | Select-Object -First 10
```

## Error Handling

If parameter export fails:
- ⚠️ Warning logged
- ✅ Component continues processing
- ✅ 3D model still exports
- ✅ Toolpaths still regenerate
- ✅ NC files still generate

**CSV export failure does NOT fail the order** - treated as non-critical warning.

## Data Analysis Example

### Load All Door Parameters
```python
import pandas as pd
import glob

# Load all CSV files
csv_files = glob.glob('Parameters/*.csv')
all_params = []

for file in csv_files:
    df = pd.read_csv(file)
    df['component_id'] = file.split('/')[-1].split('_')[0]
    all_params.append(df)

# Combine into one dataframe
combined = pd.concat(all_params)

# Analyze door sizes
heights = combined[combined['Parameter Name'] == 'component_height']['Value']
widths = combined[combined['Parameter Name'] == 'component_width']['Value']

print(f"Average height: {heights.mean()}")
print(f"Average width: {widths.mean()}")
```

## Benefits

✅ **Complete Documentation** - Every parameter recorded  
✅ **Easy to Review** - Open in Excel/Google Sheets  
✅ **Audit Trail** - Permanent record per component  
✅ **Troubleshooting** - See all computed values  
✅ **Data Analysis** - Import into databases/reports  
✅ **Quality Control** - Verify manufacturing specs  

## Future Enhancements

Possible improvements:
- 🔲 Add timestamp to CSV
- 🔲 Include order ID in filename
- 🔲 Export to JSON format option
- 🔲 Include tolerance information
- 🔲 Add parameter change history
- 🔲 Generate comparison reports between components

## Summary

**Phase**: 2.6 (after Parameters, alongside Model Export)  
**Format**: CSV (comma-separated values)  
**Output**: `C:\...\Parameters\{component-id}_all_parameters.csv`  
**Content**: All user + model parameters with values and expressions  
**Behavior**: Non-blocking (warning if fails)  
**Benefit**: Complete parameter documentation per component  

Every door now gets a complete parameter snapshot in CSV format! 📊

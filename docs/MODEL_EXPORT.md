# 3D Model Export Feature

## Overview

Automatically exports a 3D model file for each component after parameters are applied but before CAM toolpath regeneration. This provides a snapshot of the exact geometry that will be manufactured.

## When It Happens

```
1. Parameters applied (e.g., 84" x 30")
   ↓
2. 3D Model exported ← NEW STEP
   ↓
3. Toolpaths regenerated
   ↓
4. G-code generated
```

## Export Configuration

### Output Directory
```
C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\Models
```

### File Format
**Default: STEP (.step)**
- Industry-standard CAD exchange format
- Preserves exact geometry
- Can be opened in any CAD software

**Alternatives available:**
- STL (.stl) - For 3D printing/mesh
- SAT (.sat) - ACIS solid format
- IGES (.igs) - Legacy CAD exchange

### File Naming
Files are named using the component ID:
- `door-panel-001.step`
- `door-panel-002.step`
- `door-panel-003.step`

## Example Output

After processing 3 doors, you'll have:

**Models Directory:**
```
C:\...\Models\
  door-panel-001.step  (84" x 30" door)
  door-panel-002.step  (96" x 36" door)
  door-panel-003.step  (72" x 24" door)
```

**NC Programs Directory:**
```
C:\...\NC Programs\
  1001.nc  (door-panel-001)
  1002.nc  (door-panel-002)
  1003.nc  (door-panel-003)
```

## What Gets Exported

The exported model includes:
- ✅ All geometry with applied parameters
- ✅ Exact dimensions (height, width, clearances)
- ✅ Door configuration (hinging, swing direction)
- ✅ Wall post positions
- ✅ All parametric features resolved

The export captures the model **as it will be manufactured** - after parameters are applied but using the design geometry.

## Supported Formats

### STEP (Default)
```python
format='step'
```
- **Extension**: .step
- **Best for**: CAD interchange, archival
- **File size**: Medium
- **Opens in**: All CAD software (Fusion, SolidWorks, AutoCAD, etc.)

### STL
```python
format='stl'
```
- **Extension**: .stl
- **Best for**: 3D printing, mesh visualization
- **File size**: Large (depends on resolution)
- **Opens in**: 3D printing software, mesh viewers

### SAT (ACIS)
```python
format='sat'
```
- **Extension**: .sat
- **Best for**: ACIS-based CAD systems
- **File size**: Small
- **Opens in**: AutoCAD, some CAM software

### IGES
```python
format='iges'
```
- **Extension**: .igs
- **Best for**: Legacy CAD interchange
- **File size**: Medium
- **Opens in**: Most CAD software (older format)

## Changing Export Format

To change the export format, edit `src/order_processor.py`:

```python
# Find this line (around line 273):
export_success, export_msg, export_path = model_exporter.export_model(design, comp_id, format='step')

# Change 'step' to one of: 'stl', 'sat', 'iges'
export_success, export_msg, export_path = model_exporter.export_model(design, comp_id, format='stl')
```

## Error Handling

If model export fails:
- ⚠️ Warning logged
- ✅ Component continues processing
- ✅ Toolpaths still regenerate
- ✅ NC files still generate

**Export failure does NOT fail the order** - it's treated as a non-critical warning.

## Use Cases

### 1. Manufacturing Archive
Keep a snapshot of what was actually manufactured:
- Customer orders specific size
- Model exported with those parameters
- Archive proves what dimensions were used

### 2. Quality Control
- Export model before manufacturing
- Compare finished part to exported model
- Verify dimensions match order

### 3. Customer Documentation
- Send customer STEP file of their door
- They can verify dimensions before manufacturing
- Import into their building models

### 4. Revision Tracking
- door-panel-001.step = Original design
- door-panel-001-rev2.step = After modification
- Compare versions in CAD software

## Success Message

After successful processing, you'll see:

```
door-panel-001: Processing complete!

✓ Updated 7 parameter(s)
✓ Exported 3D model: door-panel-001.step
✓ Regenerated 2 CAM setup(s)
✓ Generated 1/2 NC program(s):
    • hinge_side: 1001.nc
    • routing_side: FAILED (...)

Output: C:\...\NC Programs
```

## Logs

Export is logged in detail:

```
INFO - door-panel-001: Parameter updates complete, exporting 3D model
INFO - door-panel-001: Model exported: Exported door-panel-001.step (45623 bytes)
INFO - door-panel-001: Starting CAM regeneration
```

Or if it fails:

```
WARNING - door-panel-001: Model export failed: Export path not accessible
```

## Module: model_exporter.py

**Location**: `src/model_exporter.py`  
**Lines**: ~200 lines  
**Class**: `ModelExporter`

**Key Methods**:
- `export_model()` - Main entry point
- `export_as_step()` - STEP export
- `export_as_stl()` - STL export
- `export_as_sat()` - SAT export
- `export_as_iges()` - IGES export

## Configuration Options

### Change Output Directory

Edit `src/order_processor.py`, line 269:

```python
models_output_dir = r'C:\Your\Custom\Path\Models'
```

### Multiple Formats

To export multiple formats per component:

```python
# Export both STEP and STL
model_exporter.export_model(design, comp_id, format='step')
model_exporter.export_model(design, comp_id, format='stl')
```

### Custom Naming

Currently uses component ID. To customize:

```python
# In model_exporter.py, modify filename generation
output_filename = f"{component_id}_{timestamp}.step"
```

## Verification

**To verify exports are working**:

1. Run an order
2. Check output directory:
   ```powershell
   Get-ChildItem "C:\...\Models" -Filter *.step
   ```
3. Open a .step file in Fusion or another CAD program
4. Verify dimensions match order parameters

## Future Enhancements

Possible improvements:
- 🔲 Export both pre- and post-parameter models (comparison)
- 🔲 Include timestamp in filename
- 🔲 Export drawing/PDF with dimensions
- 🔲 Compress exports (ZIP)
- 🔲 Cloud upload (Dropbox, SharePoint)
- 🔲 Email notification with file attached

## Troubleshooting

### Issue: "Export completed but file not found"

**Cause**: Output directory doesn't exist or no write permissions

**Solution**:
1. Verify directory exists
2. Check write permissions
3. Try different directory

### Issue: Large STL files

**Cause**: High mesh resolution

**Solution**: Use STEP instead (smaller, better quality)

### Issue: Export takes too long

**Cause**: Complex geometry

**Solution**:
- STEP is usually fastest
- SAT is compact
- STL can be slow for complex parts

## Summary

**Phase**: 2.5 (between Parameters and CAM)  
**Format**: STEP (default), STL, SAT, IGES available  
**Output**: `C:\...\Models\{component-id}.step`  
**Behavior**: Non-blocking (warning if fails)  
**Benefit**: Archival snapshot of manufactured geometry  

Export gives you a permanent record of what was actually manufactured, with exact dimensions as specified in the order! 📐

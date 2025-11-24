# Current Setup - Fusion Manufacturing Extension

## Status: ✅ Ready for Production

**Last Updated**: November 24, 2025

## What This Extension Does

Automates the complete manufacturing pipeline for bathroom partition components:
1. **Reads JSON orders** with panels, doors, and stiles
2. **Applies parameters** to Fusion 360 models
3. **Regenerates CAM toolpaths** based on new parameters
4. **Generates G-code** for CNC machines

## Current Configuration

### JSON Format
- **Standard**: v2 format (panels/doors/stiles organization)
- **Location**: `samples/JSON_9013830.json`
- **Spec**: See `JSON_FORMAT.md` for complete specification

### Model Storage
- **Location**: `inputs/` folder with subfolders
  - `inputs/door/` - Door model (.f3d file)
  - `inputs/panel/` - Panel model (.f3d file)
  - `inputs/stile/` - Stile model (.f3d file)
- **Setup**: Run `.\setup_inputs_folder.ps1` to create structure

### Output Directories
- **G-code**: `C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\NC Programs`
- **STEP models**: `C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\Models`
- **Parameters CSV**: `C:\Users\james.derrod\OneDrive - Bobrick Washroom Equipment\Documents\Fusion 360\Parameters`
- **Logs**: `logs/` folder in extension directory

## Key Features

### ✅ Auto-Parameter Matching
- Reads parameters from your .f3d model
- Only updates parameters that exist in the model
- Silently skips parameters in JSON that aren't in the model
- **No hardcoding needed** - works with any model parameters

### ✅ Persistent Models
- Set up models once in `inputs/` folder
- Automatically switches between door/panel/stile models
- No need to specify model path in each order

### ✅ Type-Safe Parameters
- Parameters in format: `[value, datatype, description]`
- Automatic type conversion (bool → 1/0, float, int, string)
- Self-documenting with descriptions

### ✅ Complete Logging
- Every run logged to `logs/pipeline_YYYYMMDD_HHMMSS.log`
- Detailed audit trail
- Log path shown in all UI messages

### ✅ Robust Model Opening
- Works from blank/untitled document
- Opens and activates models automatically
- Handles already-open models gracefully

## Quick Start

### First Time Setup

1. **Create inputs folder**:
   ```powershell
   .\setup_inputs_folder.ps1
   ```

2. **Add your models**:
   - Place Door.f3d in `inputs/door/`
   - Place Panel.f3d in `inputs/panel/`
   - Place Stile.f3d in `inputs/stile/`

3. **Verify parameters**:
   - Open each model
   - Check Modify → Change Parameters
   - Note the parameter names

### Running Orders

1. **Create/edit order JSON**:
   - Use `samples/JSON_9013830.json` as template
   - Update order_id
   - Add your components with parameters

2. **Run in Fusion 360**:
   - Click "Run Order" button
   - Extension processes all components automatically
   - Check output folders for results

3. **Review logs**:
   - Check `logs/` folder for detailed execution log
   - Log path shown in success/error messages

## File Structure

```
FusionExtension/
├── src/                         # Python source code
│   ├── addin.py                # Main add-in entry point
│   ├── command_handler.py      # Command execution
│   ├── order_processor.py      # Order processing logic
│   ├── model_manager.py        # Model storage management
│   ├── parameter_manager.py    # Parameter updates
│   ├── cam_manager.py          # CAM toolpath generation
│   ├── post_processor.py       # G-code generation
│   ├── validator.py            # JSON validation
│   └── logger.py               # Logging utilities
├── inputs/                      # Persistent model storage
│   ├── door/                   # Door model(s)
│   ├── panel/                  # Panel model(s)
│   └── stile/                  # Stile model(s)
├── samples/                     # Example orders
│   └── JSON_9013830.json       # Current order format
├── logs/                        # Execution logs
├── docs/                        # Documentation
└── setup_inputs_folder.ps1     # Setup script
```

## Documentation

| Document | Purpose |
|----------|---------|
| `QUICKSTART_V2.md` | Quick start guide (3 steps) |
| `JSON_FORMAT.md` | Complete JSON format specification |
| `docs/INPUTS_FOLDER_SETUP.md` | Detailed model setup instructions |
| `CHANGES_AUTO_MATCH.md` | Recent changes and improvements |
| `IMPLEMENTATION_SUMMARY.md` | Technical implementation details |

## Common Tasks

### Adding a New Order
1. Copy `samples/JSON_9013830.json`
2. Update `order_id` field
3. Modify component arrays (panels/doors/stiles)
4. Update parameter values
5. Run in Fusion 360

### Updating a Model
1. Replace .f3d file in `inputs/door/`, `inputs/panel/`, or `inputs/stile/`
2. Ensure parameter names match your JSON
3. No code changes needed

### Checking What Happened
1. Look in `logs/` folder
2. Open most recent `pipeline_YYYYMMDD_HHMMSS.log`
3. Search for errors or warnings
4. Check parameter update confirmations

### Troubleshooting
1. **Models not found**: Run `.\setup_inputs_folder.ps1` to check status
2. **Parameters not updating**: Open model and verify parameter names match JSON
3. **Validation errors**: Check `logs/` for details
4. **CAM errors**: Ensure model has CAM setups configured

## Parameter Matching Behavior

The extension uses **smart parameter matching**:

```
JSON Parameters          Model Parameters         Result
─────────────────       ─────────────────        ──────
component_height    →   component_height         ✓ Updated
component_width     →   component_width          ✓ Updated
series_id          →   (not in model)            ⚠ Skipped
door_hinging        →   (not in model)            ⚠ Skipped
                        custom_param             ✗ Not updated
```

**Key Points**:
- Only updates parameters that **exist in both** JSON and model
- Extra JSON parameters are **silently skipped** (no error)
- Model parameters not in JSON are **left unchanged**
- Parameter names are **case-sensitive**

## Processing Flow

```
Order JSON
    ↓
Validation (v2 format)
    ↓
For each PANEL:
    Open panel model → Match parameters → Update → Regenerate CAM → Post-process
    ↓
For each DOOR:
    Open door model → Match parameters → Update → Regenerate CAM → Post-process
    ↓
For each STILE:
    Open stile model → Match parameters → Update → Regenerate CAM → Post-process
    ↓
Complete
```

## System Requirements

- **Fusion 360**: Latest version
- **Python**: 3.7+ (bundled with Fusion)
- **Windows**: PowerShell for setup scripts
- **Models**: .f3d files with user parameters matching JSON

## Best Practices

1. **Consistent Naming**: Use same parameter names across all models
2. **Document Parameters**: Use description field in JSON
3. **Version Control**: Keep order JSONs in version control
4. **Test Models**: Verify parameters exist before running large orders
5. **Check Logs**: Review logs after each run
6. **Backup Models**: Keep backups of your .f3d files

## Known Limitations

1. **One Model Per Type**: Currently supports one .f3d file per component type
2. **User Parameters Only**: Only updates user parameters (not model parameters)
3. **Sequential Processing**: Components processed one at a time (not parallel)
4. **Fixed Output Paths**: Output directories are hardcoded

## Future Enhancements

Potential improvements:
- [ ] Multiple models per type with selection logic
- [ ] Parallel component processing
- [ ] Configurable output paths
- [ ] Web interface for order creation
- [ ] Batch processing of multiple orders
- [ ] Real-time progress updates
- [ ] Automatic model parameter discovery

## Support

For issues or questions:
1. Check the logs first: `logs/pipeline_*.log`
2. Review documentation: `JSON_FORMAT.md`, `QUICKSTART_V2.md`
3. Verify setup: Run `.\setup_inputs_folder.ps1`
4. Check model parameters: Modify → Change Parameters in Fusion

## Version History

- **v2.0** (Nov 2025): Modular architecture with persistent models
- **v1.0** (Oct 2025): Initial component-based processing

---

**Status**: Production Ready ✅  
**Format**: v2 JSON only  
**Auto-matching**: Enabled  
**Logging**: Full audit trail

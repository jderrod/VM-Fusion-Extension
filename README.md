# Fusion 360 Automated Manufacturing Pipeline

## Overview
Python-based automation system for Autodesk Fusion 360 Desktop that processes manufacturing orders by:
1. Loading parametric Fusion 360 models
2. Applying parameter values from JSON input
3. Regenerating CAM toolpaths
4. Post-processing to generate G-code (.nc files)
5. Organizing outputs with comprehensive logging

## Project Status
**Current Phase:** Phase 1 - Fusion Add-in Skeleton ✅  
**Ready for:** Manual testing in Fusion 360

## Architecture

### Input Format
Orders are defined as JSON files conforming to `schema.json`:
- **Order-level metadata**: orderId, version, timestamp
- **Components array**: Each component specifies:
  - Fusion model path
  - Parameter values to apply
  - Post-processor configuration
  - Optional CAM setup filtering

### Parameter System
The system modifies Fusion 360 user parameters defined in the model:
- **Primary parameters** (user-configurable): Listed in `FusionModelParams/FusionModelParametersToChange.csv`
- **Derived parameters** (formulas): Listed in `FusionModelParams/FusionModelParametersAll.csv`
- Parameter dependencies are handled automatically by Fusion's parametric engine

### Workflow
```
JSON Order → Validate Schema → For Each Component:
  1. Open Fusion Model
  2. Apply Parameters (update user parameter expressions)
  3. Regenerate Model (Fusion auto-computes dependencies)
  4. Switch to CAM Workspace
  5. Regenerate Toolpaths (generateAllToolpaths)
  6. Post Process (generate .nc files)
  7. Log Results
→ Collect & Organize Outputs
```

## Directory Structure
```
FusionExtension/
├── schema.json              # JSON schema definition
├── llms.txt                 # Context for LLM assistants
├── README.md                # This file
├── src/                     # Source code
│   ├── addin.py            # Fusion add-in entry point ✅
│   ├── app.py              # Main application logic ✅
│   ├── command_handler.py  # Command handlers ✅
│   ├── logger.py           # Logging utilities ✅
│   ├── validator.py        # Schema validation ✅
│   ├── parameter_manager.py # Parameter application (TBD)
│   ├── cam_manager.py      # CAM operations (TBD)
│   └── post_processor.py   # Post processing (TBD)
├── tests/                   # Unit tests
│   └── test_validator.py   # Schema validation tests ✅
├── samples/                 # Example files
│   └── sample_order.json   # Sample order with door parameters ✅
├── docs/                    # Documentation
│   ├── schema.md           # Schema documentation ✅
│   ├── dev-notes.md        # Development notes ✅
│   └── PHASE1_TESTING.md   # Phase 1 testing guide ✅
└── FusionModelParams/       # Parameter reference files
    ├── FusionModelParametersToChange.csv    # User-modifiable parameters
    └── FusionModelParametersAll.csv         # All parameters including derived
```

## Development Phases

### ✅ Phase 0: Setup
- [x] Create project scaffold
- [x] Define JSON schema with versioning
- [x] Create sample order file
- [x] Add schema validation tests (41 tests passing)
- [x] Document schema and development approach

### ✅ Phase 1: Fusion Add-in Skeleton
- [x] Create add-in with run/stop entry points
- [x] Register "Run Order" command
- [x] Implement JSON file loading and validation
- [x] Add basic error handling and logging
- [x] Create interactive command dialog
- [x] Integrate file selection with validation

### Phase 2: Parameter Application
- [ ] Load Fusion design document
- [ ] Read user parameters from model
- [ ] Apply parameter values from JSON
- [ ] Validate parameter updates
- [ ] Handle parameter type conversions

### Phase 3: Toolpath Regeneration
- [ ] Switch to CAM workspace
- [ ] Call generateAllToolpaths()
- [ ] Handle invalid toolpaths
- [ ] Log regeneration status

### Phase 4: Post Processing
- [ ] Configure post processor selection
- [ ] Create NCProgramInput
- [ ] Execute postProcess() for each setup
- [ ] Validate .nc file creation
- [ ] Implement custom file naming

### Phase 5: Multi-Component Orders
- [ ] Iterate through component array
- [ ] Process each component independently
- [ ] Aggregate logs and outputs
- [ ] Add skip/retry logic
- [ ] Implement output organization

## Key Parameters (from FusionModelParams)

### User-Modifiable Parameters
- `component_height` (in): Height of the component [72-96 in range]
- `component_width` (in): Width of the component [22-37.5 in range]
- `component_floor_clearance` (in): Floor clearance [1-12 in range]
- `door_hinging_right` (0/1): Door hinges on right side relative to room
- `door_swinging_out` (0/1): Door swings out relative to cabin
- `door_wall_post_hinging` (0/1): Wall post on hinging side
- `door_wall_keep_latching` (0/1): Wall keep on latching side

### Derived Parameters (Auto-computed)
- `component_height_limited`: Clamped height within valid range
- `component_width_limited`: Clamped width within valid range
- `door_drilling_left`/`door_drilling_right`: Computed drilling side
- `door_notching_left`/`door_notching_right`: Computed notching requirements
- And many more formula-driven parameters...

## Testing Strategy
1. **Unit Tests**: Pure Python logic (schema validation, parameter parsing)
2. **Integration Tests**: Fusion API interaction (parameter setting, CAM operations)
3. **Manual Validation**: Run complete orders in Fusion and verify .nc output

## Development Environment
- **IDE**: Windsurf
- **Python**: 3.x (Fusion embedded interpreter)
- **Fusion API**: adsk.core, adsk.fusion, adsk.cam
- **Testing**: pytest for unit tests
- **Schema Validation**: jsonschema library

## Getting Started
1. Review the schema in `schema.json`
2. Examine the sample order in `samples/sample_order.json`
3. Check parameter definitions in `FusionModelParams/`
4. Proceed to Phase 1 when ready to implement the add-in

## API References
- [Fusion CAM API Introduction](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CAMIntroduction_UM.htm)
- [CAM.generateToolpath](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CAM_generateToolpath.htm)
- [PostProcessInput](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/PostProcessInput.htm)
- [NCProgram.postProcess](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/NCProgram_postProcess.htm)
- [Python Add-in Template](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/PythonTemplate_UM.htm)

## License
Internal project - not for public distribution
"# FusionExtension" 
"# FusionLocalFinal" 

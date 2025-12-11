# Anderson Stratos Post Processor Configuration

This folder contains the machine definition and post processor for the Anderson Stratos CNC router.

## Files

### Anderson Stratos.mch
Machine definition file for the Anderson Stratos Pro Full line CNC router.

**Specifications:**
- **Vendor:** Anderson America
- **Model:** Stratos
- **Type:** CNC Router (Milling)
- **Axes:** X, Y, Z (3-axis)
- **Travel:**
  - X-axis: 3149.6 mm
  - Y-axis: 2184.4 mm
  - Z-axis: 254 mm
- **Spindle:** 
  - Max Speed: 24,000 RPM
  - Power: 13.4 kW
- **Tool Changer:** 10 tools
- **Units:** Millimeters

### Anderson Stratos 2.cps
Custom post processor for generating G-code for the Anderson Stratos machine.

**Features:**
- Based on Fanuc controller format
- Custom configuration for Anderson Stratos Pro Full line
- DSI EDIT version
- Extension: .nc
- Integer program names

## Usage

The system automatically uses these files when generating G-code:

1. **Master Models:** Ensure your Fusion 360 master models (door.f3d, panel.f3d, stile.f3d) have CAM setups configured to use the Anderson Stratos machine definition.

2. **Automatic Processing:** When the pipeline processes orders, it automatically:
   - Uses `Anderson Stratos 2.cps` as the post processor
   - Generates G-code compatible with the Anderson Stratos machine
   - Outputs files in the format: `1-[ComponentID]-[OrderID].nc`

## Updating

If you need to update the machine definition or post processor:

1. **Machine Definition (.mch):**
   - Edit `Anderson Stratos.mch` in a text editor
   - Update any machine parameters as needed
   - Update the corresponding machine in Fusion 360 CAM Library

2. **Post Processor (.cps):**
   - Edit `Anderson Stratos 2.cps` in a text editor or Fusion 360 post processor editor
   - Test changes with sample toolpaths
   - Verify generated G-code is correct for your machine

3. **Applying Changes:**
   - Restart the Fusion 360 extension to load updated post processor
   - Update master model CAM setups if machine definition changed

## Machine Configuration in Fusion 360

To configure a CAM setup to use this machine:

1. Open your model in Fusion 360
2. Switch to MANUFACTURE workspace
3. Create or edit a Setup
4. Under Machine tab:
   - Select "Anderson Stratos" from machine library
   - Or import `Anderson Stratos.mch` if not in library
5. Configure post processor:
   - Select "Anderson Stratos 2" from post library
   - Or browse to `Anderson Stratos 2.cps`

## Technical Notes

- The post processor is referenced relative to the extension installation directory
- Path: `FusionExtension/Post Processing/Anderson Stratos 2.cps`
- The system automatically uses this post processor for all generated G-code
- No need to manually configure post processor for each order

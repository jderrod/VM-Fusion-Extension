# Toolbar Button Setup Guide

## Expected Result

After loading the extension, you should see:
- **Location:** Design workspace → SOLID toolbar panel
- **Button:** "Specs to Machine" with Bobrick logo icon
- **Type:** Standalone button (not dropdown)
- **Icon:** Blue Bobrick oval logo (32x32 pixels)

## Installation Steps

1. **Stop any running instance:**
   - Utilities → ADD-INS
   - Select "FusionManufacturingPipeline"
   - Click "Stop"

2. **Close all Fusion 360 dialogs and panels**

3. **Run the extension:**
   - Click "Run" in the ADD-INS dialog
   - Wait for success message

4. **Find the button:**
   - Switch to Design workspace (if not already there)
   - Look at the SOLID toolbar panel
   - The button should be at the end of the SOLID panel
   - Label: "Specs to Machine"
   - Icon: Bobrick blue oval logo

## Troubleshooting

### Button Not Visible

**Check 1: Verify workspace**
- Make sure you're in the **Design workspace** (not Render, Animation, etc.)
- Top menu should show: DESIGN tab active

**Check 2: Check SOLID panel**
- Look for the SOLID panel in the toolbar
- It's usually the first panel with CREATE dropdown
- Scroll through the buttons in that panel
- The button might be at the very end

**Check 3: Check toolbar overflow**
- If your screen is narrow, some buttons go to overflow menu
- Look for ">>" symbol at end of toolbar
- Click it to see hidden buttons

**Check 4: Verify extension loaded**
- Utilities → ADD-INS
- "FusionManufacturingPipeline" should show "Running"
- Green checkmark = running
- If not running, click "Run"

### Button Shows But No Icon

**Check 1: Icon files exist**
```
FusionExtension\UI Elements\
  ├── bobrick_logo.png  ✓
  ├── 16x16.png        ✓
  └── 32x32.png        ✓
```

**Check 2: Regenerate icons**
Run from FusionExtension directory:
```powershell
python -c "from PIL import Image; img = Image.open('UI Elements/bobrick_logo.png'); img.resize((32,32)).save('UI Elements/32x32.png'); img.resize((16,16)).save('UI Elements/16x16.png')"
```

**Check 3: Restart Fusion**
- Close Fusion 360 completely
- Reopen Fusion 360
- Extension should auto-start if "Run on Startup" is checked

### Error Messages

**"Workspace not found"**
- Fusion might still be loading
- Wait 10 seconds and try again

**"Could not find SOLID panel"**
- Design workspace not active
- Switch to Design workspace
- Stop and restart extension

**"Failed to create control"**
- Another extension might be conflicting
- Try disabling other extensions
- Restart Fusion 360

## Verification

After successful setup, you should be able to:

1. ✓ See button in SOLID panel
2. ✓ See Bobrick logo icon on button
3. ✓ Click button to open dialog
4. ✓ Choose "Start Folder Monitor" or "Process Single Order"

## Getting Help

If button still doesn't appear:

1. Check the log file:
   - `FusionExtension/logs/pipeline.log`
   - Look for registration errors

2. Try alternative location:
   - The old code had it in CREATE dropdown
   - Check there as fallback

3. Completely reinstall:
   - Stop extension
   - Delete from ADD-INS
   - Restart Fusion 360
   - Re-add extension

## Technical Details

**Button Properties:**
- Command ID: `ManufacturingPipelineRunOrder`
- Panel: `SolidCreatePanel`
- Workspace: `FusionSolidEnvironment`
- Icon folder: `UI Elements/`
- Promoted: Yes (always visible)

**Icon Specifications:**
- Format: PNG with transparency
- Sizes: 16x16 and 32x32 pixels
- Location: `UI Elements/` folder
- Naming: `16x16.png` and `32x32.png`

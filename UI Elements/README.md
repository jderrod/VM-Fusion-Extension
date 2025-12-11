# UI Elements

This folder contains custom UI elements for the Fusion 360 Manufacturing Pipeline extension.

## Bobrick Logo Icon

**Files:**
- `bobrick_logo.png` - Original high-resolution logo
- `16x16.png` - Small icon for Fusion 360 toolbar (generated)
- `32x32.png` - Standard icon for Fusion 360 toolbar (generated)

The Bobrick logo is used as the custom icon for the "Specs to Machine" toolbar button in Fusion 360's Design workspace.

### Icon Specifications

- **Original:** 200x80 pixels (bobrick_logo.png)
- **Toolbar Icons:** 16x16 and 32x32 pixels (auto-generated for Fusion)
- **Format:** PNG with transparency
- **Style:** Blue oval Bobrick brand logo
- **Location:** Displayed as a button on the SOLID panel in the Design workspace

### Fusion 360 Icon Resources

Fusion 360 requires icons in specific sizes. The extension automatically uses:
- **16x16.png** - Small toolbar icon
- **32x32.png** - Standard toolbar icon (most common)

These are automatically generated from the original `bobrick_logo.png` when the extension loads.

### Icon Display

The icon appears:
- On the toolbar in the Design workspace (SOLID panel)
- Button label: "Specs to Machine"
- Tooltip: "Bobrick Specs to Machine - Automated order processing"

### Updating the Icon

If you need to update or change the icon:

1. **Prepare New Icon:**
   - Recommended size: 32x32 or 64x64 pixels for toolbar buttons
   - Format: PNG with transparent background
   - Keep it simple and recognizable at small sizes

2. **Replace File:**
   - Replace `bobrick_logo.png` with your new icon
   - Keep the same filename, or update the path in `src/app.py`

3. **Update Code (if changing filename):**
   - Edit `src/app.py`
   - Find line: `icon_path = str(Path(__file__).parent.parent / 'UI Elements' / 'bobrick_logo.png')`
   - Update the filename to match your new icon

4. **Reload Extension:**
   - Stop the extension in Fusion 360
   - Restart the extension to see the new icon

### Icon Best Practices

For Fusion 360 toolbar icons:
- **Size:** 32x32 or 64x64 pixels recommended
- **Format:** PNG with transparency
- **Colors:** Use clear, contrasting colors
- **Simplicity:** Keep design simple for small display sizes
- **Branding:** Match your company brand colors

### Troubleshooting

**Icon not showing:**
- Verify file exists at: `FusionExtension/UI Elements/bobrick_logo.png`
- Check file permissions (should be readable)
- Restart Fusion 360 completely
- Check logs for any errors

**Icon looks blurry:**
- Increase resolution (try 64x64 or 128x128)
- Ensure PNG is high quality, not compressed
- Use vector source if available

**Icon wrong size:**
- Fusion auto-scales, but starting with proper size helps
- Try exporting at 32x32, 48x48, or 64x64 pixels

# Quick Start Guide - Modular Order Processing

## 🚀 Get Started in 3 Steps

### Step 1: Set Up Your Models (One-Time Setup)

Run the setup script:
```powershell
.\setup_inputs_folder.ps1
```

Place your .f3d model files:
```
inputs/
├── door/
│   └── [YourDoorModel.f3d]     ← Drop your door model here
├── panel/
│   └── [YourPanelModel.f3d]    ← Drop your panel model here
└── stile/
    └── [YourStileModel.f3d]    ← Drop your stile model here
```

### Step 2: Create Your Order JSON

Use the new format (see `samples/JSON_9013830.json` for complete example):

```json
{
  "order_id": ["YOUR-ORDER-ID", "string", "Order identifier"],
  "panels": [
    {
      "id": ["P1", "string", "Panel 1"],
      "parameters": {
        "component_height": [96, "float", "height in inches"],
        "component_width": [10.5, "float", "width in inches"]
      }
    }
  ],
  "doors": [
    {
      "id": ["D1", "string", "Door 1"],
      "parameters": {
        "component_height": [96, "float", "height in inches"],
        "component_width": [34.375, "float", "width in inches"]
      }
    }
  ],
  "stiles": [
    {
      "id": ["S1", "string", "Stile 1"],
      "parameters": {
        "component_height": [97.75, "float", "height in inches"],
        "component_width": [3, "float", "width in inches"]
      }
    }
  ]
}
```

### Step 3: Run Your Order

1. Open Fusion 360
2. Run the extension
3. The system will:
   - Auto-detect the v2 format
   - Process all panels (open panel model → apply parameters → regenerate toolpaths)
   - Process all doors (open door model → apply parameters → regenerate toolpaths)
   - Process all stiles (open stile model → apply parameters → regenerate toolpaths)
   - Generate G-code for everything

## 📋 Parameter Format

Each parameter uses the format: `[value, datatype, description]`

| Type | Example | Notes |
|------|---------|-------|
| Float | `[96.5, "float", "description"]` | For decimals |
| Integer | `[10, "int", "description"]` | For whole numbers |
| Boolean | `[true, "bool", "description"]` | For true/false |
| String | `["ABC123", "string", "description"]` | For text |
| Null | `[null, "float", "description"]` | Converts to 0 |

## ✅ What You Get

- **Automatic Model Switching**: System opens the right model for each component type
- **Type-Safe Parameters**: No more parameter formatting errors
- **Batch Processing**: Process multiple panels, doors, and stiles in one order
- **Persistent Models**: Set up once, use forever
- **Full Pipeline**: Parameters → Toolpaths → G-code, all automated

## 📁 Output Files

All output goes to your configured directories:

- **G-code**: `C:\...\NC Programs\`
- **STEP Models**: `C:\...\Models\`
- **Parameters CSV**: `C:\...\Parameters\`

## ⚡ Common Tasks

### Add a New Component to an Order
Just add it to the appropriate array:
```json
"doors": [
  {...existing door...},
  {
    "id": ["D_NEW", "string", "New door"],
    "parameters": {...}
  }
]
```

### Update a Model
Simply replace the .f3d file in the inputs folder.

### Check Model Parameters
Open model in Fusion → Modify → Change Parameters → View user parameters

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "No model configured" | Run `.\setup_inputs_folder.ps1` and add .f3d files |
| "Parameter not found" | Check parameter names match exactly (case-sensitive) |
| Type conversion error | Verify datatype matches the value type |
| Model won't open | Ensure .f3d file is not corrupted |

## 📚 More Information

- **Detailed Setup**: `docs/INPUTS_FOLDER_SETUP.md`
- **Full Upgrade Guide**: `UPGRADE_TO_V2.md`
- **Sample JSON**: `samples/JSON_9013830.json`

---

**Ready to start?** Run `.\setup_inputs_folder.ps1` now!

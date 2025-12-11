# Automated Order Processing Guide

## Overview

This system automatically processes manufacturing orders by watching a folder for new JSON files. When a file is dropped, it:
1. Launches Fusion 360
2. Loads the extension
3. Processes the order
4. Saves results
5. Moves the file to completed/failed folder

## Architecture

```
order_dropbox/           ← Drop JSON files here
     ↓
File Watcher Service     ← Monitors folder
     ↓
Fusion 360               ← Auto-launches
     ↓
Extension Auto-Run       ← Processes order
     ↓
order_completed/         ← Success
order_failed/            ← Failures
```

## Setup

### 1. Install Python Dependencies

The watcher service needs the `watchdog` library:

```powershell
pip install -r requirements_watcher.txt
```

Or manually:
```powershell
pip install watchdog
```

### 2. Configure Fusion 360 Path

Edit `order_watcher_service.py` line 243 if your Fusion 360 is installed elsewhere:

```python
fusion_path = r'C:\Program Files\Autodesk\Fusion 360\Fusion360.exe'
```

### 3. Set Up Extension in Fusion

1. In Fusion 360: Utilities → ADD-INS
2. Click the **+** button (Add)
3. Browse to: `c:\Users\james.derrod\FusionExtension`
4. Click **OK**
5. Check "Run on Startup" (important for auto-run!)
6. Click **Run**

### 4. Configure Models

Place your `.f3d` model files:
```
inputs/
├── door/YourDoorModel.f3d
├── panel/YourPanelModel.f3d
└── stile/YourStileModel.f3d
```

## Running the Watcher Service

### Start the Service

```powershell
cd c:\Users\james.derrod\FusionExtension
python order_watcher_service.py
```

You'll see:
```
============================================================
Order Watcher Service Starting
============================================================
Watch folder: C:\Users\james.derrod\FusionExtension\order_dropbox
Processing folder: C:\Users\james.derrod\FusionExtension\order_processing
Completed folder: C:\Users\james.derrod\FusionExtension\order_completed
Failed folder: C:\Users\james.derrod\FusionExtension\order_failed
Fusion 360: C:\Program Files\Autodesk\Fusion 360\Fusion360.exe

Waiting for order files...
(Press Ctrl+C to stop)
```

### As a Windows Service (Optional)

To run as a background Windows service, you can use NSSM (Non-Sucking Service Manager):

1. Download NSSM from: https://nssm.cc/download
2. Install the service:
   ```powershell
   nssm install FusionOrderWatcher "C:\Path\To\Python.exe" "C:\Users\james.derrod\FusionExtension\order_watcher_service.py"
   ```
3. Start the service:
   ```powershell
   nssm start FusionOrderWatcher
   ```

## Usage

### 1. Drop Order File

Simply copy or move a JSON order file into the `order_dropbox/` folder:

```powershell
copy my_order.json order_dropbox\
```

### 2. Watch the Process

The watcher service will:
- Detect the new file (within seconds)
- Validate the JSON format
- Move it to `order_processing/`
- Launch Fusion 360 (if not already running)
- Wait for processing to complete
- Move to `order_completed/` or `order_failed/`

### 3. Check Results

**Successful orders** go to: `order_completed/`
- Filename: `YYYYMMDD_HHMMSS_original_name.json`
- G-code files in your output folders

**Failed orders** go to: `order_failed/`
- Filename: `YYYYMMDD_HHMMSS_original_name.json`
- Error details in: `YYYYMMDD_HHMMSS_original_name.txt`

### 4. Check Logs

**Watcher service logs**: `logs/watcher_YYYYMMDD_HHMMSS.log`
**Extension logs**: `logs/pipeline_YYYYMMDD_HHMMSS.log`

## Folder Structure

```
FusionExtension/
├── order_dropbox/           ← Drop new orders here
├── order_processing/        ← Currently processing
├── order_completed/         ← Successfully completed
├── order_failed/            ← Failed orders with error logs
├── logs/                    ← All service and extension logs
│   ├── watcher_*.log
│   └── pipeline_*.log
├── order_watcher_service.py ← File watcher service
└── src/
    └── auto_run_handler.py  ← Extension auto-run code
```

## JSON Order Format

Orders must use the v2 format:

```json
{
  "order_id": ["ORDER-123", "string", "Order identifier"],
  "panels": [{
    "id": ["P1", "string", "Panel 1"],
    "parameters": {
      "component_height": [96, "float", "height in inches"],
      "component_width": [10.5, "float", "width in inches"]
    }
  }],
  "doors": [...],
  "stiles": [...]
}
```

See `samples/JSON_9013830.json` for a complete example.

## How It Works

### File Watcher Service

1. **Monitors** `order_dropbox/` for new `.json` files
2. **Validates** JSON format
3. **Moves** file to `order_processing/`
4. **Creates** trigger file: `auto_run_order.json`
5. **Launches** Fusion 360
6. **Waits** for result file: `auto_run_result.json`
7. **Moves** order to completed/failed folder

### Extension Auto-Run

1. **Checks** for trigger file on startup
2. **Validates** order format
3. **Opens** required models
4. **Processes** all components
5. **Writes** result file
6. **Cleans up** trigger file

### Communication

- **Trigger File**: `auto_run_order.json` (watcher → extension)
- **Result File**: `auto_run_result.json` (extension → watcher)

## Troubleshooting

### Watcher service not detecting files

- Check the service is running: Look for console output
- Verify watch folder path is correct
- Try dropping a test file

### Fusion 360 doesn't launch

- Check Fusion path in `order_watcher_service.py`
- Verify Fusion 360 is installed
- Try launching manually first

### Extension doesn't auto-run

- Ensure extension has "Run on Startup" checked
- Verify trigger file is created: `auto_run_order.json`
- Check extension logs: `logs/pipeline_*.log`

### Order processing fails

- Check `order_failed/` for error details
- Review extension logs
- Verify models are configured in `inputs/` folder
- Ensure JSON format is valid

### Timeout errors

- Default timeout is 30 minutes per order
- Adjust in `order_watcher_service.py` line 134:
  ```python
  timeout = 1800  # seconds
  ```

## Performance

### Expected Processing Times

- **JSON validation**: < 1 second
- **Model loading**: 10-30 seconds (all 3 models)
- **Component processing**: 2-5 minutes per component
- **Total order**: Depends on component count

For a typical 14-component order: ~30-60 minutes

### Parallel Processing

Currently processes one order at a time. Multiple orders will queue.

To process multiple orders in parallel:
- Run multiple watcher services with different watch folders
- Each launches its own Fusion instance

## Advanced Configuration

### Custom Watch Folder

Edit `order_watcher_service.py`:

```python
watch_folder = Path(r'C:\Your\Custom\Path\dropbox')
```

### Email Notifications

Add email notifications on completion/failure by extending `OrderFileHandler`:

```python
def _process_order(self, file_path):
    success = self._run_fusion_order(processing_path)
    
    if success:
        self._send_email(f'Order {file_path.name} completed')
    else:
        self._send_email(f'Order {file_path.name} failed')
```

### Network Folder Monitoring

To watch a network drive:

```python
watch_folder = Path(r'\\server\share\orders\dropbox')
```

Note: Network monitoring may have delays.

## Best Practices

1. **Test orders first** - Run manually before automating
2. **Check logs regularly** - Monitor for errors
3. **Backup completed orders** - Archive order history
4. **Monitor disk space** - G-code files can be large
5. **Update models carefully** - Test changes before production

## Security Considerations

- **File access**: Service runs with user permissions
- **Network monitoring**: Be cautious with shared folders
- **JSON validation**: Service validates but doesn't sanitize
- **Fusion access**: Anyone can drop files if folder is accessible

## Support

### Logs to Check

1. **Watcher service**: `logs/watcher_*.log`
2. **Extension**: `logs/pipeline_*.log`
3. **Failed orders**: `order_failed/*.txt`

### Common Issues

| Issue | Check | Solution |
|-------|-------|----------|
| Service not starting | Python installed? | Install Python 3.7+ |
| Watchdog import error | Dependencies installed? | `pip install watchdog` |
| Fusion doesn't launch | Path correct? | Update `fusion_path` |
| Extension doesn't run | Run on startup? | Enable in ADD-INS |
| Models not found | Files in inputs/? | Copy .f3d files |
| Timeout | Order too large? | Increase timeout value |

## Examples

### Process a Single Order

```powershell
# Start watcher
python order_watcher_service.py

# In another terminal, drop order
copy samples\JSON_9013830.json order_dropbox\

# Watch console output
# Check order_completed\ when done
```

### Batch Processing

```powershell
# Drop multiple orders at once
copy orders\*.json order_dropbox\

# They'll process sequentially
```

### Test Mode

```powershell
# Validate JSON without processing
python -c "import json; json.load(open('test.json'))"
```

## Future Enhancements

Potential improvements:
- Web interface for order submission
- Real-time progress updates via WebSocket
- Email/SMS notifications
- Parallel order processing
- Priority queue system
- API endpoint for order submission
- Cloud storage integration

---

**Status**: ✅ Ready for Use  
**Mode**: Automated file watcher  
**Processing**: Sequential, one order at a time  
**Timeout**: 30 minutes per order

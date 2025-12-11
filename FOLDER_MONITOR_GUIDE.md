# Folder Monitor Guide

## Overview

The Folder Monitor feature allows the Fusion extension to continuously watch the `order_dropbox/` folder and automatically process any JSON order files that are placed there.

## Quick Start

### 1. Load the Extension

In Fusion 360:
- Go to **Utilities** → **ADD-INS**
- Find **FusionManufacturingPipeline**
- Click **Run**

### 2. Start Folder Monitoring

- Click **SOLID** → **CREATE** → **Run Order**
- In the dialog, click **YES** (Start Folder Monitor)
- The extension will:
  - Open all models (door, panel, stile)
  - Start watching `order_dropbox/` folder
  - Show confirmation message

### 3. Drop Order Files

Simply drop JSON order files into:
```
FusionExtension/order_dropbox/
```

The extension will:
- ✓ Detect new files within 3 seconds
- ✓ Add files to processing queue
- ✓ Process files one at a time (in order)
- ✓ Validate the JSON format
- ✓ Process the order automatically
- ✓ Move completed files to `order_completed/`
- ✓ Move failed files to `order_failed/` (with error details)
- ✓ Continue monitoring and processing continuously

### 4. Stop Monitoring

- Click **SOLID** → **CREATE** → **Run Order** again
- Click **OK** to stop monitoring

## Folder Structure

```
FusionExtension/
├── order_dropbox/          ← Drop new orders here
├── order_processing/       ← Files being processed
├── order_completed/        ← Successfully completed orders
└── order_failed/           ← Failed orders (with .txt error files)
```

## Features

### ✓ Queue-Based Processing
- Files are added to a queue as they're detected
- Processes one file at a time (no race conditions)
- Multiple files can be dropped simultaneously
- Queue processes until empty, then waits for more

### ✓ Continuous Processing
- Runs in the background while Fusion is open
- No need for external scripts or services
- Checks for new files every 3 seconds
- Never stops - always ready for the next file

### ✓ Automatic File Management
- Moves files through processing stages
- Timestamps completed/failed files
- Creates error logs for failed orders

### ✓ Smart Validation
- Validates JSON format before processing
- Rejects invalid files immediately
- Logs detailed error messages

### ✓ Model Efficiency
- Opens all models once at startup
- Switches between models during processing
- No repeated open/close operations

## Processing Multiple Files

You can drop multiple JSON files at once:

```powershell
# Drop multiple orders
copy samples\JSON_9013830.json order_dropbox\order1.json
copy samples\JSON_9013830.json order_dropbox\order2.json
copy samples\JSON_9013830.json order_dropbox\order3.json
```

**What happens:**
1. All 3 files are detected and queued (within ~3 seconds)
2. `order1.json` starts processing
3. When done, `order2.json` starts automatically
4. Then `order3.json` processes
5. Monitor continues waiting for more files

**Queue is always active** - you can drop more files while others are processing!

## Workflow Options

When you click "Run Order", you get three choices:

### YES - Start Folder Monitor (Recommended for Production)
- Continuous processing
- Hands-free operation
- Best for batch processing multiple orders

### NO - Process Single Order
- One-time processing
- Uses `samples/JSON_9013830.json`
- Shows progress dialog
- Good for testing

### CANCEL
- Do nothing

## Tips

### For Development/Testing
1. Keep a test JSON in `samples/`
2. Use "Process Single Order" mode for quick tests
3. Check logs in `logs/` folder

### For Production
1. Start Folder Monitor mode
2. Keep Fusion 360 running with extension loaded
3. Drop orders into `order_dropbox/`
4. Monitor `order_completed/` and `order_failed/` folders
5. Check logs if issues occur

### Error Handling
- Failed orders are moved to `order_failed/`
- Each failed order gets a `.txt` file with error details
- All activity is logged to `logs/pipeline_*.log`

## Logging

All operations are logged to:
```
FusionExtension/logs/pipeline_YYYYMMDD_HHMMSS.log
```

Log entries include:
- File detection events
- Validation results
- Processing status
- File movements
- Errors and exceptions

## Troubleshooting

### Monitor Won't Start
- Check that models exist in `inputs/door/`, `inputs/panel/`, `inputs/stile/`
- Run model selection dialog first if needed
- Check logs for errors

### Files Not Being Detected
- Wait up to 3 seconds after dropping files
- Ensure files have `.json` extension
- Check file isn't locked by another process

### Orders Failing
- Check the `.txt` file in `order_failed/` for details
- Validate JSON format against schema
- Review logs for detailed error messages
- Ensure models are compatible with order parameters

## Advantages Over External Watcher

✓ **Simpler Setup**: No external Python scripts needed
✓ **No Launch Issues**: Fusion already running
✓ **Better Integration**: Direct access to Fusion API
✓ **Easier Debugging**: All logs in one place
✓ **More Reliable**: No inter-process communication needed

## Comparison

| Feature | Folder Monitor (New) | External Watcher (Old) |
|---------|---------------------|------------------------|
| Setup | Load extension only | Run separate Python script |
| Fusion Launch | Manual (once) | Automatic (problematic) |
| File Detection | 3 seconds | 2 seconds |
| Error Handling | Integrated | Via trigger files |
| Logging | Single system | Split between processes |
| Reliability | High | Medium |

## Next Steps

For production deployment:
1. Test thoroughly with sample orders
2. Set up a network folder for `order_dropbox/`
3. Configure automated order generation to drop files there
4. Monitor logs and output folders regularly
5. Keep Fusion running with extension loaded

For automation, you could:
- Use Windows Task Scheduler to start Fusion on system boot
- Create a monitoring dashboard for completed/failed folders
- Set up email alerts for failed orders
- Archive completed orders periodically

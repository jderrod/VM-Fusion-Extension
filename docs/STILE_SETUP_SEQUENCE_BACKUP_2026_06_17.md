# Stile Setup Sequence - Backup of 2-Door Logic (Pre Jun 17, 2026)

This file contains the original 2-door ordering logic from `_build_stile_setup_sequence()` 
in `src/order_processor.py` before the drilling-aware reordering was implemented.

## Revert Instructions

To revert, replace the `elif num_doors == 2:` block (lines ~1190-1225) in 
`_build_stile_setup_sequence()` with the code below, and remove any 
`drilling_paired_data` parameter and drilling-flag reading logic that was added.

## Original 2-Door Logic

```python
            elif num_doors == 2:
                if ld_outswing == rd_outswing:
                    # Both doors swing the same direction
                    # Same swings always post G57 first, then Rotate 180°, then G59
                    if not ld_outswing:
                        # Both in-swing (interior rabbeting both sides)
                        # G57 = right rabbet, G59 = left rabbet
                        sequence = [
                            _find_setup('Right Rabbet - In G57'),
                            _find_setup('Left Rabbet - In G59')
                        ]
                        handling = 'both in-swing'
                    else:
                        # Both out-swing (exterior rabbeting both sides)
                        # G57 = left rabbet, G59 = right rabbet
                        sequence = [
                            _find_setup('Left Rabbet - Out G57'),
                            _find_setup('Right Rabbet - Out G59')
                        ]
                        handling = 'both out-swing'
                else:
                    # Opposite swing directions
                    if not ld_outswing and rd_outswing:
                        # Left in, Right out (right before left for G59)
                        sequence = [
                            _find_setup('Right Rabbet - Out G59'),
                            _find_setup('Left Rabbet - In G59')
                        ]
                        handling = 'left in + right out'
                    else:
                        # Left out, Right in
                        sequence = [
                            _find_setup('Left Rabbet - Out G57'),
                            _find_setup('Right Rabbet - In G57')
                        ]
                        handling = 'left out + right in'
```

## Original Selection Rules (Summary)

Two doors, same swing direction (G57 first, Rotate 180°, G59 second):
- Both In  → [Right Rabbet - In G57] then [Left Rabbet - In G59]
- Both Out → [Left Rabbet - Out G57] then [Right Rabbet - Out G59]

Two doors, opposite swing directions:
- Left In  + Right Out → [Right Rabbet - Out G59] then [Left Rabbet - In G59]
- Left Out + Right In  → [Left Rabbet - Out G57] then [Right Rabbet - In G57]

## Parameters Used (original)

- series_id, left_side_door, right_side_door, LD_swinging_out, RD_swinging_out

## What Changed (Jun 17, 2026)

New 2-door ordering logic — ONLY applies to **opposite-face rabbeting** (one side interior, 
other side exterior, i.e. opposite swing directions). Same-face rabbeting (both in-swing or 
both out-swing) retains the original fixed ordering (G57 first, Rotate 180°, G59).

For opposite-face cases, drilling flags determine sequence order:
1. **No drilling on either side** → 3082: left side first; 3086: right side first
2. **Drilling on one side only** → Side with drilling goes first
3. **Drilling on both sides** → Side with FlipRotate=3 (first face at drill machine) goes first

New parameters used: left_interior_drilling, left_exterior_drilling, 
right_interior_drilling, right_exterior_drilling, drilling_paired_data (FlipRotate values)

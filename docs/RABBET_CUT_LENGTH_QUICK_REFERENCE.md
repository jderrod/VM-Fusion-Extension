# Rabbet Cut Length — Quick Hand Calculation

## The Formula

```
Cut on Material = Linear Distance on Material + (1.136" x Number of Insertion Arcs)
```

---

## Step-by-Step

### 1. Find the Main Linear Cut

Open the G-code and look for the **long G1 line** — the one where only X changes (Y stays constant). This is the main cut along the stile.

```
Example:
   N115 G3 X-2.6142 Y-0.05 ...    ← entry arc ends here (start of linear)
   N120 G1 X81.4378                ← main linear cut (end X)
   N125 G3 X82.4502 Y0.2174 ...   ← exit arc starts here
```

The linear cut goes from **X = -2.6142** to **X = 81.4378**.

### 2. Clamp to Material Bounds

The material spans from **X = 0** to **X = sheetX** (read from `#527` in the G-code header).

For G59 (mirrored), the material spans **X = -sheetX** to **X = 0**.

```
Clamped Start = max(0, startX)
Clamped End   = min(sheetX, endX)
Linear on Material = Clamped End - Clamped Start

Example:
   sheetX = 110.375
   Clamped Start = max(0, -2.6142) = 0
   Clamped End   = min(110.375, 81.4378) = 81.4378
   Linear on Material = 81.4378 - 0 = 81.438"
```

If the toolpath extends past the material edge (through-rabbeting), the clamping handles it automatically.

### 3. Count the Insertion Arcs

Look for **G3** (or G2) lines immediately before and after the main linear cut.

- **Arc present** = the rabbet starts/ends with an insertion curve = **add 1.136"**
- **No arc** (tool exits linearly through the stile edge) = through-rabbeting = **add 0"**

```
Example:
   N115 G3 ...   ← Entry arc present   → +1.136"
   N125 G3 ...   ← Exit arc present    → +1.136"
```

### 4. Add It Up

```
Cut on Material = Linear on Material + Arc Contributions

Example:
   = 81.438 + 1.136 (exit arc only, entry arc is off-material)
   = 82.574"
```

---

## Quick Reference Table

| End Condition | What You See in G-Code | Add |
|---|---|---|
| Insertion arc | G3/G2 line next to the main G1 cut, arc is within material bounds | **+1.136"** |
| Through-rabbeting | Main G1 cut extends past 0 or sheetX (tool exits through edge) | **+0"** |

| Scenario | # Arcs on Material | Formula |
|---|---|---|
| Both ends have insertion arcs | 2 | Linear + 2.272" |
| One insertion arc, one through | 1 | Linear + 1.136" |
| Both ends through-rabbeting | 0 | Linear only |

---

## How to Tell if an Arc is On-Material or Off-Material

The entry arc is off-material if its X range is entirely outside [0, sheetX]. For G57, if both the arc start and end X are negative, the arc is off-material and contributes 0".

```
Example (entry arc OFF material):
   Arc goes from X = -3.6265 to X = -2.6142
   Both X values < 0 → arc is off-material → +0"

Example (exit arc ON material):
   Arc goes from X = 81.4378 to X = 82.4502
   Both X values > 0 and < sheetX → arc is on-material → +1.136"
```

---

## Worked Examples

### Example 1: LEFT RABBET OUT (S5, G57)

```
G-code:
   #527 = 110.375                              sheetX = 110.375
   G3 X-2.6142 Y-0.05 I1.0123 J1.7826         Entry arc (X < 0, off-material)
   G1 X81.4378                                 Main cut: -2.6142 → 81.4378
   G3 X82.4502 Y0.2174 J2.05                   Exit arc (X > 0, on-material)

Calculation:
   Linear  = min(110.375, 81.4378) - max(0, -2.6142) = 81.438"
   Entry   = off-material                              +0"
   Exit    = on-material                               +1.136"
   TOTAL   = 82.574"  ✓
```

### Example 2: RIGHT RABBET IN, Through at Top (S5, G57)

```
G-code:
   #527 = 110.375                              sheetX = 110.375
   G3 X9.3123 Y-0.05 I1.0123 J1.7826          Entry arc (X > 0, on-material)
   G1 X114.4894                                Main cut: 9.3123 → 114.4894
   G3 X115.5013 Y0.2174 I-0.0003 J2.0499      Exit arc (X > sheetX, off-material)

Calculation:
   Linear  = min(110.375, 114.4894) - max(0, 9.3123) = 101.063"
   Entry   = on-material                               +1.136"
   Exit    = off-material (past sheetX, through-rabbeting) +0"
   TOTAL   = 102.199"  ✓
```

### Example 3: LEFT RABBET OUT (S7, G57)

```
G-code:
   #527 = 88.625                               sheetX = 88.625
   G3 X-2.6142 Y-0.05 I1.0123 J1.7826         Entry arc (X < 0, off-material)
   G1 X83.5626                                 Main cut: -2.6142 → 83.5626
   G3 X84.575 Y0.2174 J2.05                    Exit arc (X > 0, on-material)

Calculation:
   Linear  = min(88.625, 83.5626) - max(0, -2.6142) = 83.563"
   Entry   = off-material                              +0"
   Exit    = on-material                               +1.136"
   TOTAL   = 84.699"  ✓
```

---

## Assumptions (When This Method Is Valid)

This constant (1.136") holds as long as these values remain fixed:

| Parameter | Value |
|---|---|
| Tool diameter | 0.5" |
| Tool radius | 0.25" |
| Rabbeting insertion radius (feature) | 2.3" |
| Rabbeting width | 0.3" |
| Arc center Y (derived) | 2.0" |

If any of these change, recalculate the constant using:

```
R_feature = rabbeting_insertion_radius          (currently 2.3")
cy        = arc_center_Y                        (currently 2.0")

Arc constant = R_feature x cos(arcsin(-cy / R_feature))
             = 2.3 x cos(arcsin(-2.0 / 2.3))
             = 2.3 x 0.4937
             = 1.136"
```

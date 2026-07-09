# Calculating Rabbet Cut Length from G-Code

This document explains, step by step, how to determine the length of material actually cut during a rabbeting operation from the G-code toolpath. The method accounts for tool geometry, insertion arcs, and material boundaries.

---

## Inputs

| Input | Source | Example Value |
|-------|--------|---------------|
| **Tool diameter** | G-code header comment `(T001 D=0.5 ...)` | 0.5" |
| **Sheet X size** | G-code variable `#527` | 110.375" |
| **Work offset** | G57 or G59 in the operation block | G57 |

Derived:
- **Tool radius** = Tool diameter / 2 = **0.25"**
- **Material X bounds** (G57): X = [0, sheetX] = [0, 110.375]
- **Material X bounds** (G59): X = [-sheetX, 0]

---

## Toolpath Structure

A typical rabbeting toolpath has five segments in order:

```
1. Lead-in ramp    (G1, diagonal — X and Y both change)
2. Entry arc       (G3, curves tool into cutting depth)
3. Main straight   (G1, long linear cut along X at constant Y)
4. Exit arc        (G3, curves tool out of cutting depth)
5. Lead-out ramp   (G1, diagonal — X and Y both change)
```

The material surface is at **Y = 0**. During the main cut, the tool center sits at Y = -0.05 (slightly below the surface). The ramps approach/depart at Y > 0 (above the surface). The arcs transition between these.

---

## Which Segments Contribute to Cut Length?

| Segment | Contributes? | Why |
|---------|-------------|-----|
| Lead-in ramp | **No** | Diagonal move approaching the material; both X and Y change significantly |
| Entry arc | **Yes** (partially) | The insertion curve defines where the rabbet feature begins on the material surface |
| Main straight | **Yes** | The primary cut along the stile; only the X portion within material bounds counts |
| Exit arc | **Yes** (partially) | The insertion curve defines where the rabbet feature ends on the material surface |
| Lead-out ramp | **No** | Diagonal move departing the material |

**Key rule:** A linear segment is a "ramp" (excluded) when both |dX| > 0.01 and |dY| > 0.01.

---

## Step-by-Step Calculation

### Step 1: Extract the Material Boundary

From the G-code header:
```
N10 #527= 110.375   (X SHEET SIZE)
```
For **G57**: material spans X = [0, 110.375].  
For **G59**: material spans X = [-110.375, 0].

### Step 2: Identify Each Segment

Parse the G-code lines for the operation. Track modal G-codes — a motion code (G0/G1/G2/G3) remains active on subsequent lines even if not explicitly stated.

### Step 3: Calculate the Main Straight Cut

For the main G1 linear move, the cut length on material is the **X-axis projection** clamped to the material bounds:

```
matDist = min(sheetX, endX) - max(0, startX)
```

If the result is negative, the segment is entirely off-material (matDist = 0).

### Step 4: Calculate Arc Contributions Using the Feature Arc

This is the critical insight. The tool center follows an arc of radius **R_tool**, but the actual rabbet edge on the material surface is cut by the tool's outer edge, which traces an arc of radius:

```
R_feature = R_tool + tool_radius
```

The rabbet feature begins/ends where this **feature arc** intersects the material surface at **Y = 0**.

#### 4a. Find the arc center and tool radius

From the G-code arc command `G3 Xend Yend Ii Jj`:
- Arc center: **(startX + I, startY + J)**
- Tool path radius: **R_tool = sqrt(I² + J²)**

#### 4b. Compute the feature arc radius

```
R_feature = R_tool + tool_radius
```

#### 4c. Find where the feature arc crosses Y = 0

The feature arc centered at (cx, cy) with radius R_feature intersects Y = 0 when:

```
cy + R_feature * sin(a) = 0
sin(a) = -cy / R_feature
```

This gives two candidate X intersections:

```
a_intersect = arcsin(-cy / R_feature)

X_int1 = cx + R_feature * cos(a_intersect)
X_int2 = cx + R_feature * cos(pi - a_intersect)
```

Pick the intersection that falls within or near the arc's X range.

#### 4d. Compute the arc's material cut distance

The arc's cut length on material is the X span from the feature boundary to the arc endpoint deeper in the material, clamped to material bounds:

```
fxClamped    = clamp(featureEndX, 0, sheetX)
startClamped = clamp(arcStartX, 0, sheetX)
endClamped   = clamp(arcEndX, 0, sheetX)

matArcXDist = max( |fxClamped - startClamped|, |fxClamped - endClamped| )
```

Using `max()` of both distances handles both entry arcs (feature boundary near the start) and exit arcs (feature boundary near the end).

### Step 5: Handle Through-Rabbeting

When the rabbet extends through the full top or bottom of the stile, there is **no insertion arc** at that end. Instead, the toolpath runs straight past the material edge and continues 2" beyond.

In this case, the exit/entry arc will be located entirely beyond the material boundary. The clamping logic naturally handles this:
- Both the arc start and end clamp to the material edge (e.g., sheetX)
- matArcXDist = 0 (the arc contributes nothing)
- The main straight cut's clamping already stops at the material edge

### Step 6: Sum All Contributions

```
Total cut on material = main_straight_matDist + entry_arc_matDist + exit_arc_matDist
```

---

## Worked Example 1: Non-Through Rabbeting (LEFT RABBET OUT)

**G-code** (from `1-S5-IBUS789123.txt`, Setup 1):

```gcode
N80 G57                                          ; Work offset G57, material X=[0, 110.375]
N85 G0 X-4.0613 Y0.4643                          ; Rapid to start position
N100 G1 Z0.25                                    ; Plunge to cutting depth
N110 X-3.6265 Y0.2174 F200.                      ; Lead-in ramp (diagonal)
N115 G3 X-2.6142 Y-0.05 I1.0123 J1.7826          ; Entry arc
N120 G1 X81.4378                                  ; Main straight cut
N125 G3 X82.4502 Y0.2174 J2.05                   ; Exit arc
N130 G1 X82.8848 Y0.4643                          ; Lead-out ramp (diagonal)
```

**Known values:**
- Tool diameter = 0.5", tool radius = 0.25"
- Sheet X = 110.375"
- Material bounds (G57) = [0, 110.375]
- Expected cut on material: **82.574"**

---

### Lead-in ramp (N110): EXCLUDED

(-4.0613, 0.4643) -> (-3.6265, 0.2174)

|dX| = 0.4348, |dY| = 0.2469. Both > 0.01 -> **ramp, excluded**.

---

### Entry arc (N115): 0" on material

G3 from (-3.6265, 0.2174) to (-2.6142, -0.05), I=1.0123, J=1.7826

**Arc center:**
```
cx = -3.6265 + 1.0123 = -2.6142
cy =  0.2174 + 1.7826 =  2.0
```

**R_tool:**
```
R_tool = sqrt(1.0123² + 1.7826²) = sqrt(1.025 + 3.178) = sqrt(4.203) = 2.05
```

**R_feature:**
```
R_feature = 2.05 + 0.25 = 2.30
```

**Feature arc Y=0 intersection:**
```
sin(a) = -2.0 / 2.3 = -0.8696
a_intersect = arcsin(-0.8696) = -1.054 rad

X_int1 = -2.6142 + 2.3 * cos(-1.054) = -2.6142 + 1.136 = -1.478
X_int2 = -2.6142 + 2.3 * cos(pi + 1.054) = -2.6142 - 1.136 = -3.750
```

Both intersections are X < 0, which is outside the material bounds [0, 110.375].

After clamping everything to [0, 110.375]:
```
fxClamped = 0, startClamped = 0, endClamped = 0
matArcXDist = max(|0-0|, |0-0|) = 0"
```

**Entry arc contribution: 0"** (entirely off-material)

---

### Main straight cut (N120): 81.438"

G1 from (-2.6142, -0.05) to (81.4378, -0.05)

|dY| = 0 -> not a ramp.

```
matDist = min(110.375, 81.4378) - max(0, -2.6142)
        = 81.4378 - 0
        = 81.438"
```

---

### Exit arc (N125): 1.136"

G3 from (81.4378, -0.05) to (82.4502, 0.2174), I=0, J=2.05

**Arc center:**
```
cx = 81.4378 + 0     = 81.4378
cy = -0.05   + 2.05  = 2.0
```

**R_tool = 2.05, R_feature = 2.30**

**Feature arc Y=0 intersection:**
```
sin(a) = -2.0 / 2.3 = -0.8696
a_intersect = -1.054 rad

X_int1 = 81.4378 + 2.3 * cos(-1.054) = 81.4378 + 1.136 = 82.574
X_int2 = 81.4378 - 1.136 = 80.302
```

X_int1 = 82.574 falls near the arc range [81.438, 82.450] -> **featureEndX = 82.574**

Clamped to [0, 110.375]:
```
fxClamped    = 82.574
startClamped = 81.438
endClamped   = 82.450
```

```
d1 = |82.574 - 81.438| = 1.136
d2 = |82.574 - 82.450| = 0.124
matArcXDist = max(1.136, 0.124) = 1.136"
```

---

### Lead-out ramp (N130): EXCLUDED

(82.4502, 0.2174) -> (82.8848, 0.4643)

|dX| = 0.4346, |dY| = 0.2469. Both > 0.01 -> **ramp, excluded**.

---

### Total

```
Cut on material = 0 + 81.438 + 1.136 + 0
                = 82.574"  ✓
```

---

## Worked Example 2: Through-Rabbeting at Top (RIGHT RABBET IN)

**G-code** (from `1-S5-IBUS789123.txt`, Setup 2):

```gcode
N255 G57                                                ; Work offset G57
N260 G0 X7.8652 Y0.4643                                 ; Rapid to start
N280 Z0.25                                               ; Plunge
N285 X8.3 Y0.2174 F200.                                  ; Lead-in ramp
N290 G3 X9.3123 Y-0.05 I1.0123 J1.7826                   ; Entry arc (feature insertion)
N295 G1 X114.4894                                         ; Main straight cut
N300 G3 X115.5013 Y0.2174 I-0.0003 J2.0499                ; Exit arc (NO feature insertion — through-rabbeting)
N305 G1 X115.5014                                         ; Tiny linear move
N310 X115.9364 Y0.4643                                    ; Lead-out ramp
```

**Known values:**
- Sheet X = 110.375", material bounds = [0, 110.375]
- The rabbet extends through the top of the stile (through-rabbeting)
- Expected cut on material: **102.199"**

---

### Lead-in ramp (N285): EXCLUDED

|dX| = 0.435, |dY| = 0.247 -> ramp.

---

### Entry arc (N290): 1.136"

G3 from (8.3, 0.2174) to (9.3123, -0.05), I=1.0123, J=1.7826

```
cx = 8.3 + 1.0123   = 9.3123
cy = 0.2174 + 1.7826 = 2.0
R_tool = 2.05, R_feature = 2.30
```

**Feature arc Y=0 intersection:**
```
sin(a) = -2.0 / 2.3 = -0.8696

X_int1 = 9.3123 + 2.3 * cos(-1.054) = 9.3123 + 1.136 = 10.448
X_int2 = 9.3123 - 1.136 = 8.176
```

X_int2 = 8.176 falls near the arc range [8.3, 9.3123] -> **featureEndX = 8.176**

```
fxClamped    = 8.176
startClamped = 8.3
endClamped   = 9.3123

d1 = |8.176 - 8.3|    = 0.124     (distance to arc start)
d2 = |8.176 - 9.3123| = 1.136     (distance to arc end)
matArcXDist = max(0.124, 1.136) = 1.136"
```

Note: for **entry arcs**, the feature boundary (8.176) is near the arc start, and the arc end (9.3123) is deeper in the material. `max()` correctly picks the larger span.

---

### Main straight cut (N295): 101.063"

G1 from (9.3123, -0.05) to (114.4894, -0.05)

```
matDist = min(110.375, 114.4894) - max(0, 9.3123)
        = 110.375 - 9.3123
        = 101.063"
```

Note: the toolpath extends to X=114.49 (past the material edge at 110.375), but we clamp to the material boundary. This is the through-rabbeting — the tool exits through the top of the stile.

---

### Exit arc (N300): 0" (through-rabbeting)

G3 from (114.4894, -0.05) to (115.5013, 0.2174), I=-0.0003, J=2.0499

```
cx = 114.4894 + (-0.0003) = 114.4891
cy = -0.05 + 2.0499       = 2.0
R_tool = 2.05, R_feature = 2.30
```

**Feature arc Y=0 intersection:**
```
X_int1 = 114.4891 + 1.136 = 115.625
X_int2 = 114.4891 - 1.136 = 113.353
```

X_int1 = 115.625 is near the arc range -> featureEndX = 115.625

Clamped to [0, 110.375]:
```
fxClamped    = 110.375    (clamped from 115.625)
startClamped = 110.375    (clamped from 114.4894)
endClamped   = 110.375    (clamped from 115.5013)
```

```
d1 = |110.375 - 110.375| = 0
d2 = |110.375 - 110.375| = 0
matArcXDist = 0"
```

The entire exit arc is beyond the material boundary. The arc is simply a lead-out curve, not a feature insertion. **This is the hallmark of through-rabbeting.**

---

### Lead-out ramp (N310): EXCLUDED

|dX| = 0.435, |dY| = 0.247 -> ramp.

---

### Total

```
Cut on material = 1.136 + 101.063 + 0
                = 102.199"  ✓
```

---

## Shortcut: The Arc Constant

Because the tool diameter (0.5"), insertion radius (2.3"), and rabbeting width (0.3") are fixed, every insertion arc contributes the **same X distance** to the cut on material:

```
R_feature = 2.30"
cy        = 2.0"

Feature arc Y=0 crossing:
    cos(a) = sqrt(1 - (cy / R_feature)²) = sqrt(1 - (2.0/2.3)²) = 0.4937

Arc constant = R_feature × cos(a) = 2.3 × 0.4937 = 1.136"
```

This means the cut length can be simplified to:

```
Cut on material = main_linear_X_on_material + (1.136" × number_of_insertion_arcs)
```

| Scenario | Arcs | Formula |
|----------|------|---------|
| Both ends through-rabbeting | 0 | linear only |
| One end through, one insertion | 1 | linear + 1.136 |
| Both ends have insertion arcs | 2 | linear + 2.272 |

This shortcut is valid as long as the tool diameter, insertion radius, and rabbeting width remain unchanged.

---

## Summary of the Algorithm

```
FOR each operation in the G-code:
    FOR each segment:
        IF segment is G0 (rapid):
            skip (no cutting)

        IF segment is G1 (linear):
            IF |dX| > 0.01 AND |dY| > 0.01:
                classify as ramp → 0" material contribution
            ELSE IF |dX| < 0.0001:
                classify as pure Y move → 0" contribution
            ELSE:
                matDist = clamp(endX, lo, hi) - clamp(startX, lo, hi)
                if matDist < 0: matDist = 0

        IF segment is G2/G3 (arc):
            Compute arc center (cx, cy) and R_tool from I, J
            R_feature = R_tool + tool_radius
            Find feature arc intersection with Y=0
            Pick the intersection near the arc's X range
            Clamp featureEndX, arcStartX, arcEndX to material bounds
            matArcXDist = max(|featureX - startX|, |featureX - endX|)

    Total = sum of all segment contributions
```

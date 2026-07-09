"""
Testing Suite Viewer — Desktop app for comparing expected vs actual parameter outputs.
Uses tkinter (built into Python, no external dependencies).

Supports:
  - Door scenarios (3X8X_DV_*) with expected_output.csv
  - Stile scenarios (3X86_SV_*) with 3X86 Stile expected outputs CSV
  - 3X82 Stile scenarios (3X82_SV_*) with the 3X82 CSV

Features:
  - Compare expected vs actual outputs per scenario
  - Upload scenario generation CSVs (input data for test JSON generation)
  - Upload expected output CSVs (validation data for output comparison)
  - Run scenario generation scripts to produce test JSON files

Usage:
  python test_viewer.py
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
REPO_ROOT = BASE_DIR.parent

# Directories
EXPECTED_OUTPUT_DIR = BASE_DIR / "expected_output"
SCENARIO_CSV_DIR = BASE_DIR  # Scenario generation CSVs live in testing_suite root
ORDER_DROPBOX = REPO_ROOT / "S2S File Test" / "order_dropbox"

# Generator scripts mapped by component type keyword
GENERATOR_SCRIPTS = {
    "3X8X Door": {
        "script": BASE_DIR / "generate_door_jsons.py",
        "output_dir": BASE_DIR / "door_validation_tests",
        "csv_var": "csv_path",
    },
    "3X82 Stile": {
        "script": BASE_DIR / "generate_stile_jsons.py",
        "output_dir": BASE_DIR / "stile_validation_tests",
        "csv_var": "csv_path",
    },
    "3X86 Stile": {
        "script": BASE_DIR / "generate_3X86_stile_jsons.py",
        "output_dir": BASE_DIR / "stile_validation_tests",
        "csv_var": "csv_path",
    },
}

# Test suites: each entry defines a test category
TEST_SUITES = {
    "Door (3X8X_DV)": {
        "expected_csv": EXPECTED_OUTPUT_DIR / "3X8X Door inputs & outputs v10 macro_enabled 2026_02_12(ValidationOutputs).csv",
        "scenario_csv": BASE_DIR / "3X8X Door inputs & outputs v10 macro_enabled 2026_02_12(ValidationScenarios vFin ).csv",
        "actual_dirs": [
            REPO_ROOT / "S2S File Test" / "output" / "parameters",
            BASE_DIR / "actual_output",
        ],
        "scenario_prefix": "3X8X_DV_",
        "actual_file_pattern": "D1_all_parameters.json",
        "param_name_mapping": {
            "ceiling_clearance": "component_ceiling_clearance",
        },
        "scenario_json_dir": BASE_DIR / "door_validation_tests",
    },
    "Stile 3X82 (3X82_SV)": {
        "expected_csv": EXPECTED_OUTPUT_DIR / "3X82 Stile inputs & outputs v15 macro_enabled 2026_02_26(ValidationOutputs)(1).csv",
        "scenario_csv": BASE_DIR / "3X82 Stile inputs & outputs v15 macro_enabled 2026_02_26(ValidationScenarios vFin)(3).csv",
        "actual_dirs": [
            REPO_ROOT / "S2S File Test" / "output" / "parameters",
        ],
        "scenario_prefix": "3X82_SV_",
        "actual_file_pattern": "S1_all_parameters.json",
        "param_name_mapping": {},
        "scenario_json_dir": BASE_DIR / "stile_validation_tests",
    },
    "Stile 3X86 (3X86_SV)": {
        "expected_csv": EXPECTED_OUTPUT_DIR / "3X86 Stile inputs & outputs v08 macro_enabled 2026_03_12(ValidationOutputs).csv",
        "scenario_csv": BASE_DIR / "3X86 Stile inputs & outputs v08 macro_enabled 2026_03_12(ValidationScenario vFin).csv",
        "actual_dirs": [
            REPO_ROOT / "S2S File Test" / "output" / "parameters",
        ],
        "scenario_prefix": "3X86_SV_",
        "actual_file_pattern": "S1_all_parameters.json",
        "param_name_mapping": {},
        "scenario_json_dir": BASE_DIR / "stile_validation_tests",
    },
}

TOLERANCE = 0.0001

# Persistence file for user-created suites
CUSTOM_SUITES_FILE = BASE_DIR / "custom_suites.json"

# Built-in suite names (cannot be deleted)
_BUILTIN_SUITE_NAMES = set(TEST_SUITES.keys())


def _load_custom_suites() -> dict:
    """Load user-created suites from JSON config file."""
    if not CUSTOM_SUITES_FILE.exists():
        return {}
    try:
        with open(CUSTOM_SUITES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        suites = {}
        for name, cfg in raw.items():
            suites[name] = {
                "expected_csv": Path(cfg["expected_csv"]),
                "actual_dirs": [Path(p) for p in cfg["actual_dirs"]],
                "scenario_prefix": cfg["scenario_prefix"],
                "actual_file_pattern": cfg["actual_file_pattern"],
                "param_name_mapping": cfg.get("param_name_mapping", {}),
                "scenario_json_dir": Path(cfg["scenario_json_dir"]),
            }
            # Register generator script if provided
            gen_script = cfg.get("generator_script", "")
            if gen_script:
                GENERATOR_SCRIPTS[name] = {
                    "script": Path(gen_script),
                    "output_dir": Path(cfg["scenario_json_dir"]),
                    "csv_var": "csv_path",
                }
        return suites
    except Exception:
        return {}


def _save_custom_suites(suites: dict):
    """Save user-created suites to JSON config file."""
    raw = {}
    for name, cfg in suites.items():
        entry = {
            "expected_csv": str(cfg["expected_csv"]),
            "actual_dirs": [str(p) for p in cfg["actual_dirs"]],
            "scenario_prefix": cfg["scenario_prefix"],
            "actual_file_pattern": cfg["actual_file_pattern"],
            "param_name_mapping": cfg.get("param_name_mapping", {}),
            "scenario_json_dir": str(cfg["scenario_json_dir"]),
        }
        if cfg.get("generator_script"):
            entry["generator_script"] = str(cfg["generator_script"])
        raw[name] = entry
    with open(CUSTOM_SUITES_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)


# Merge any saved custom suites into TEST_SUITES at startup
TEST_SUITES.update(_load_custom_suites())

# ─── Data Loading ────────────────────────────────────────────────────────────

def load_expected(csv_path: Path) -> dict:
    """Load expected CSV -> {scenario: {param: value}}"""
    data = {}
    if not csv_path.exists():
        return data
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = [c for c in reader.fieldnames if c != "Scenario"]
        for row in reader:
            scenario = row.get("Scenario", "").strip()
            if scenario:
                data[scenario] = {col: row[col] for col in columns}
    return data


def load_actual_json(json_path: Path) -> dict:
    """Load actual JSON -> {param_name: value}"""
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    flat = {}
    for param_name, param_data in raw.get("user_parameters", {}).items():
        if isinstance(param_data, dict) and "value" in param_data:
            flat[param_name] = param_data["value"]
    return flat


def find_actual_file(scenario: str, actual_dirs: list, pattern: str):
    """Find the actual output JSON for a scenario.
    When multiple directories contain the same scenario, return the newest file."""
    best = None
    best_mtime = -1
    for d in actual_dirs:
        candidate = d / scenario / pattern
        if candidate.exists():
            mtime = candidate.stat().st_mtime
            if mtime > best_mtime:
                best = candidate
                best_mtime = mtime
    return best


def compare_values(expected_val, actual_val, tolerance=TOLERANCE):
    """Return 'pass', 'fail', or 'missing'."""
    if actual_val is None or actual_val == "N/A":
        return "missing"
    if expected_val is None or expected_val == "" or expected_val == "N/A":
        return "skip"
    try:
        exp_f = float(expected_val)
        act_f = float(actual_val)
        return "pass" if abs(exp_f - act_f) < tolerance else "fail"
    except (ValueError, TypeError):
        return "pass" if str(expected_val).strip() == str(actual_val).strip() else "fail"


def run_comparison(suite_cfg: dict):
    """
    Run full comparison for a suite.
    Returns:
        scenarios: dict of {scenario_name: {
            "status": "pass"|"fail"|"missing",
            "params": [{name, expected, actual, result}, ...]
            "pass_count": int, "fail_count": int, "missing_count": int
        }}
    """
    expected = load_expected(suite_cfg["expected_csv"])
    if not expected:
        return {}

    scenarios = {}
    for scenario_name, expected_params in expected.items():
        actual_path = find_actual_file(
            scenario_name, suite_cfg["actual_dirs"], suite_cfg["actual_file_pattern"]
        )
        actual_flat = load_actual_json(actual_path) if actual_path else {}
        mapping = suite_cfg.get("param_name_mapping", {})

        params = []
        pass_count = fail_count = missing_count = skip_count = 0

        for param_name, expected_val in expected_params.items():
            actual_key = mapping.get(param_name, param_name)
            actual_val = actual_flat.get(actual_key)
            result = compare_values(expected_val, actual_val)

            if result == "pass":
                pass_count += 1
            elif result == "fail":
                fail_count += 1
            elif result == "missing":
                missing_count += 1
            else:
                skip_count += 1

            params.append({
                "name": param_name,
                "expected": expected_val,
                "actual": actual_val if actual_val is not None else "---",
                "result": result,
            })

        if not actual_path:
            status = "no_output"
        elif fail_count > 0:
            status = "fail"
        elif missing_count > 0:
            status = "partial"
        else:
            status = "pass"

        scenarios[scenario_name] = {
            "status": status,
            "params": params,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "missing_count": missing_count,
            "skip_count": skip_count,
        }

    return scenarios


def csv_preview(csv_path: Path, max_rows: int = 5) -> str:
    """Return a short text preview of a CSV file."""
    if not csv_path.exists():
        return "(file not found)"
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            lines = []
            for i, row in enumerate(reader):
                if i >= max_rows + 1:
                    break
                lines.append(row)
        if not lines:
            return "(empty file)"
        header = lines[0]
        n_cols = len(header)
        info = f"{n_cols} columns"
        # Count total rows
        with open(csv_path, "r", encoding="utf-8") as f:
            total = sum(1 for _ in f) - 1
        info += f", {total} data rows"
        col_sample = ", ".join(header[:6])
        if len(header) > 6:
            col_sample += f" ... (+{len(header)-6} more)"
        return f"{info}\nColumns: {col_sample}"
    except Exception as e:
        return f"(error reading: {e})"


# ─── UI ──────────────────────────────────────────────────────────────────────

class TestViewerApp:
    # Colors
    BG = "#1e1e2e"
    BG_SECONDARY = "#272737"
    BG_HEADER = "#313147"
    FG = "#cdd6f4"
    FG_DIM = "#6c7086"
    ACCENT = "#89b4fa"
    GREEN = "#a6e3a1"
    RED = "#f38ba8"
    YELLOW = "#f9e2af"
    ORANGE = "#fab387"
    SURFACE = "#313147"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Testing Suite Viewer")
        self.root.geometry("1400x900")
        self.root.configure(bg=self.BG)
        self.root.minsize(1000, 600)

        self.scenarios = {}
        self.filtered_scenarios = []
        self.current_suite = None
        self.current_filter = "all"

        self._setup_styles()
        self._build_ui()

        # Track which suites are user-created (not built-in)
        self._custom_suites = {k: v for k, v in TEST_SUITES.items() if k not in _BUILTIN_SUITE_NAMES}

        # Auto-load first suite
        first_suite = list(TEST_SUITES.keys())[0]
        self.suite_var.set(first_suite)
        self._on_suite_change()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Notebook (tabs) styling
        style.configure("Dark.TNotebook", background=self.BG, borderwidth=0)
        style.configure("Dark.TNotebook.Tab",
                         background=self.BG_SECONDARY,
                         foreground=self.FG_DIM,
                         font=("Segoe UI", 10),
                         padding=[12, 6])
        style.map("Dark.TNotebook.Tab",
                   background=[("selected", self.BG_HEADER)],
                   foreground=[("selected", self.FG)])

        # Treeview styling
        style.configure("Custom.Treeview",
                         background=self.BG,
                         foreground=self.FG,
                         fieldbackground=self.BG,
                         font=("Consolas", 10),
                         rowheight=24)
        style.configure("Custom.Treeview.Heading",
                         background=self.BG_HEADER,
                         foreground=self.FG,
                         font=("Segoe UI", 10, "bold"),
                         relief=tk.FLAT)
        style.map("Custom.Treeview",
                   background=[("selected", self.ACCENT)],
                   foreground=[("selected", "#1e1e2e")])

        # File list treeview
        style.configure("FileList.Treeview",
                         background=self.BG,
                         foreground=self.FG,
                         fieldbackground=self.BG,
                         font=("Consolas", 9),
                         rowheight=22)
        style.configure("FileList.Treeview.Heading",
                         background=self.BG_HEADER,
                         foreground=self.FG,
                         font=("Segoe UI", 9, "bold"),
                         relief=tk.FLAT)
        style.map("FileList.Treeview",
                   background=[("selected", self.ACCENT)],
                   foreground=[("selected", "#1e1e2e")])

    def _make_button(self, parent, text, command, color=None, width=None):
        """Helper to create a styled button."""
        bg = color or self.ACCENT
        btn = tk.Button(parent, text=text, font=("Segoe UI", 9),
                        bg=bg, fg="#1e1e2e", relief=tk.FLAT,
                        padx=10, pady=4, command=command, cursor="hand2")
        if width:
            btn.config(width=width)
        return btn

    def _make_section_label(self, parent, text):
        """Helper to create a section header label."""
        lbl = tk.Label(parent, text=text, font=("Segoe UI", 11, "bold"),
                       bg=self.BG, fg=self.FG, anchor="w")
        return lbl

    def _build_ui(self):
        # ── Top bar ──
        top = tk.Frame(self.root, bg=self.BG_HEADER, pady=8, padx=12)
        top.pack(fill=tk.X)

        tk.Label(top, text="Testing Suite Viewer", font=("Segoe UI", 14, "bold"),
                 bg=self.BG_HEADER, fg=self.FG).pack(side=tk.LEFT)

        # ── Tabbed notebook ──
        self.notebook = ttk.Notebook(self.root, style="Dark.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Tab 1: Comparison
        self.comparison_tab = tk.Frame(self.notebook, bg=self.BG)
        self.notebook.add(self.comparison_tab, text="  Comparison  ")

        # Tab 2: Manage CSVs
        self.manage_tab = tk.Frame(self.notebook, bg=self.BG)
        self.notebook.add(self.manage_tab, text="  Manage CSVs  ")

        # Tab 3: Execute Tests
        self.execute_tab = tk.Frame(self.notebook, bg=self.BG)
        self.notebook.add(self.execute_tab, text="  Execute Tests  ")

        self._build_comparison_tab()
        self._build_manage_tab()
        self._build_execute_tab()

        # Status bar
        self.status_bar = tk.Label(self.root, text="Ready", font=("Segoe UI", 9),
                                    bg=self.BG_HEADER, fg=self.FG_DIM, anchor="w", padx=8, pady=3)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    # ── Comparison Tab ───────────────────────────────────────────────────────

    def _build_comparison_tab(self):
        tab = self.comparison_tab

        # Controls bar
        controls = tk.Frame(tab, bg=self.BG, pady=6, padx=12)
        controls.pack(fill=tk.X)

        # Suite selector
        tk.Label(controls, text="Suite:", font=("Segoe UI", 10),
                 bg=self.BG, fg=self.FG_DIM).pack(side=tk.LEFT, padx=(0, 5))
        self.suite_var = tk.StringVar()
        self.suite_combo = ttk.Combobox(controls, textvariable=self.suite_var,
                                        values=list(TEST_SUITES.keys()), state="readonly", width=25)
        self.suite_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.suite_combo.bind("<<ComboboxSelected>>", lambda e: self._on_suite_change())

        self._make_button(controls, "Refresh", self._on_suite_change).pack(side=tk.LEFT, padx=(0, 8))
        self._make_button(controls, "+ New Suite", self._create_new_suite, color=self.GREEN).pack(side=tk.LEFT, padx=(0, 4))
        self.delete_suite_btn = self._make_button(controls, "Delete Suite", self._delete_current_suite, color=self.RED)
        self.delete_suite_btn.pack(side=tk.LEFT, padx=(0, 20))

        # Summary label
        self.summary_label = tk.Label(controls, text="Select a suite to begin",
                                       font=("Segoe UI", 10), bg=self.BG, fg=self.FG_DIM)
        self.summary_label.pack(side=tk.LEFT, padx=(10, 0))

        # CSV info bar (shows active CSVs for the selected suite)
        csv_info_frame = tk.Frame(tab, bg=self.BG_HEADER, padx=12, pady=4)
        csv_info_frame.pack(fill=tk.X)
        self.csv_info_expected = tk.Label(csv_info_frame, text="",
                                           font=("Segoe UI", 9), bg=self.BG_HEADER,
                                           fg=self.FG_DIM, anchor="w")
        self.csv_info_expected.pack(fill=tk.X)
        self.csv_info_scenario = tk.Label(csv_info_frame, text="",
                                           font=("Segoe UI", 9), bg=self.BG_HEADER,
                                           fg=self.FG_DIM, anchor="w")
        self.csv_info_scenario.pack(fill=tk.X)

        # Filter buttons
        filter_frame = tk.Frame(controls, bg=self.BG)
        filter_frame.pack(side=tk.RIGHT)

        self.filter_buttons = {}
        for label, key, color in [
            ("All", "all", self.FG),
            ("Pass", "pass", self.GREEN),
            ("Fail", "fail", self.RED),
            ("Partial", "partial", self.YELLOW),
            ("No Output", "no_output", self.FG_DIM),
        ]:
            btn = tk.Button(filter_frame, text=label, font=("Segoe UI", 9),
                            bg=self.BG_SECONDARY, fg=color, relief=tk.FLAT, padx=8, pady=2,
                            command=lambda k=key: self._set_filter(k), cursor="hand2")
            btn.pack(side=tk.LEFT, padx=2)
            self.filter_buttons[key] = btn

        # Main content (paned)
        paned = tk.PanedWindow(tab, orient=tk.HORIZONTAL, bg=self.BG,
                                sashwidth=4, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Left: scenario list
        left_panel = tk.Frame(paned, bg=self.BG_SECONDARY)
        paned.add(left_panel, width=320)

        # Search
        search_frame = tk.Frame(left_panel, bg=self.BG_SECONDARY, pady=4, padx=4)
        search_frame.pack(fill=tk.X)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        search_entry = tk.Entry(search_frame, textvariable=self.search_var,
                                 font=("Segoe UI", 10), bg=self.BG, fg=self.FG,
                                 insertbackground=self.FG, relief=tk.FLAT)
        search_entry.pack(fill=tk.X, padx=4, pady=4)

        # Scenario listbox
        list_frame = tk.Frame(left_panel, bg=self.BG_SECONDARY)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        self.scenario_listbox = tk.Listbox(
            list_frame, font=("Consolas", 10), bg=self.BG, fg=self.FG,
            selectbackground=self.ACCENT, selectforeground="#1e1e2e",
            relief=tk.FLAT, highlightthickness=0, activestyle="none"
        )
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                  command=self.scenario_listbox.yview)
        self.scenario_listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.scenario_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scenario_listbox.bind("<<ListboxSelect>>", self._on_scenario_select)

        # Right: parameter detail
        right_panel = tk.Frame(paned, bg=self.BG)
        paned.add(right_panel)

        self.detail_header = tk.Label(right_panel, text="Select a scenario",
                                       font=("Segoe UI", 12, "bold"),
                                       bg=self.BG, fg=self.FG, anchor="w", padx=8, pady=6)
        self.detail_header.pack(fill=tk.X)

        self.detail_summary = tk.Label(right_panel, text="",
                                        font=("Segoe UI", 10),
                                        bg=self.BG, fg=self.FG_DIM, anchor="w", padx=8)
        self.detail_summary.pack(fill=tk.X)

        # Detail filter
        detail_filter_frame = tk.Frame(right_panel, bg=self.BG, padx=8, pady=4)
        detail_filter_frame.pack(fill=tk.X)

        self.detail_filter_var = tk.StringVar(value="all")
        for label, val in [("All", "all"), ("Failures Only", "fail"), ("Missing Only", "missing")]:
            rb = tk.Radiobutton(detail_filter_frame, text=label, variable=self.detail_filter_var,
                                value=val, font=("Segoe UI", 9), bg=self.BG, fg=self.FG_DIM,
                                selectcolor=self.BG_SECONDARY, activebackground=self.BG,
                                activeforeground=self.FG, indicatoron=True,
                                command=self._refresh_detail)
            rb.pack(side=tk.LEFT, padx=(0, 12))

        # Parameter table
        tree_frame = tk.Frame(right_panel, bg=self.BG)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        columns = ("parameter", "expected", "actual", "result")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                  style="Custom.Treeview")
        self.tree.heading("parameter", text="Parameter")
        self.tree.heading("expected", text="Expected")
        self.tree.heading("actual", text="Actual")
        self.tree.heading("result", text="Result")

        self.tree.column("parameter", width=280, minwidth=150)
        self.tree.column("expected", width=120, minwidth=80, anchor="e")
        self.tree.column("actual", width=120, minwidth=80, anchor="e")
        self.tree.column("result", width=80, minwidth=60, anchor="center")

        tree_scroll = tk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.tag_configure("pass", foreground=self.GREEN)
        self.tree.tag_configure("fail", foreground=self.RED)
        self.tree.tag_configure("missing", foreground=self.YELLOW)
        self.tree.tag_configure("skip", foreground=self.FG_DIM)

    # ── Manage CSVs Tab ──────────────────────────────────────────────────────

    def _build_manage_tab(self):
        tab = self.manage_tab

        # Two-column layout using PanedWindow
        paned = tk.PanedWindow(tab, orient=tk.HORIZONTAL, bg=self.BG,
                                sashwidth=4, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # ── Left column: Scenario Generation CSVs ──
        left = tk.Frame(paned, bg=self.BG)
        paned.add(left, width=650)

        self._make_section_label(left, "Scenario Generation CSVs (Input Data)").pack(
            fill=tk.X, padx=8, pady=(8, 2))
        tk.Label(left, text="These CSVs define the input parameters for each test scenario.\n"
                 "They are fed into generator scripts to produce individual JSON test files.",
                 font=("Segoe UI", 9), bg=self.BG, fg=self.FG_DIM, anchor="w",
                 justify=tk.LEFT).pack(fill=tk.X, padx=8, pady=(0, 8))

        # Upload button row
        gen_btn_frame = tk.Frame(left, bg=self.BG)
        gen_btn_frame.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._make_button(gen_btn_frame, "Upload Scenario CSV...",
                          self._upload_scenario_csv, width=22).pack(side=tk.LEFT, padx=(0, 8))
        self._make_button(gen_btn_frame, "Run Selected Generator",
                          self._run_generator, color=self.GREEN, width=22).pack(side=tk.LEFT)

        # File list
        gen_list_frame = tk.Frame(left, bg=self.BG)
        gen_list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        gen_cols = ("filename", "rows", "modified")
        self.gen_tree = ttk.Treeview(gen_list_frame, columns=gen_cols, show="headings",
                                      style="FileList.Treeview", height=8)
        self.gen_tree.heading("filename", text="Filename")
        self.gen_tree.heading("rows", text="Rows")
        self.gen_tree.heading("modified", text="Last Modified")
        self.gen_tree.column("filename", width=380, minwidth=200)
        self.gen_tree.column("rows", width=60, minwidth=40, anchor="e")
        self.gen_tree.column("modified", width=150, minwidth=100)

        gen_scroll = tk.Scrollbar(gen_list_frame, orient=tk.VERTICAL, command=self.gen_tree.yview)
        self.gen_tree.configure(yscrollcommand=gen_scroll.set)
        gen_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.gen_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.gen_tree.bind("<<TreeviewSelect>>", self._on_gen_csv_select)

        # Preview area
        tk.Label(left, text="Preview", font=("Segoe UI", 10, "bold"),
                 bg=self.BG, fg=self.FG, anchor="w").pack(fill=tk.X, padx=8, pady=(4, 2))
        self.gen_preview = tk.Text(left, font=("Consolas", 9), bg=self.BG_SECONDARY,
                                    fg=self.FG, height=6, relief=tk.FLAT, wrap=tk.WORD,
                                    state=tk.DISABLED)
        self.gen_preview.pack(fill=tk.X, padx=8, pady=(0, 8))

        # ── Right column: Expected Output CSVs ──
        right = tk.Frame(paned, bg=self.BG)
        paned.add(right)

        self._make_section_label(right, "Expected Output CSVs (Validation Data)").pack(
            fill=tk.X, padx=8, pady=(8, 2))
        tk.Label(right, text="These CSVs define the expected parameter values for each scenario.\n"
                 "They are used by the Comparison tab to validate actual Fusion outputs.",
                 font=("Segoe UI", 9), bg=self.BG, fg=self.FG_DIM, anchor="w",
                 justify=tk.LEFT).pack(fill=tk.X, padx=8, pady=(0, 8))

        # Upload button row
        exp_btn_frame = tk.Frame(right, bg=self.BG)
        exp_btn_frame.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._make_button(exp_btn_frame, "Upload Expected Output CSV...",
                          self._upload_expected_csv, width=26).pack(side=tk.LEFT, padx=(0, 8))
        self._make_button(exp_btn_frame, "Set as Active for Suite...",
                          self._set_active_expected, color=self.ORANGE, width=22).pack(side=tk.LEFT)

        # File list
        exp_list_frame = tk.Frame(right, bg=self.BG)
        exp_list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        exp_cols = ("filename", "scenarios", "modified", "active_for")
        self.exp_tree = ttk.Treeview(exp_list_frame, columns=exp_cols, show="headings",
                                      style="FileList.Treeview", height=8)
        self.exp_tree.heading("filename", text="Filename")
        self.exp_tree.heading("scenarios", text="Scenarios")
        self.exp_tree.heading("modified", text="Last Modified")
        self.exp_tree.heading("active_for", text="Active For")
        self.exp_tree.column("filename", width=300, minwidth=150)
        self.exp_tree.column("scenarios", width=70, minwidth=40, anchor="e")
        self.exp_tree.column("modified", width=140, minwidth=100)
        self.exp_tree.column("active_for", width=120, minwidth=80)

        exp_scroll = tk.Scrollbar(exp_list_frame, orient=tk.VERTICAL, command=self.exp_tree.yview)
        self.exp_tree.configure(yscrollcommand=exp_scroll.set)
        exp_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.exp_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.exp_tree.bind("<<TreeviewSelect>>", self._on_exp_csv_select)

        # Preview area
        tk.Label(right, text="Preview", font=("Segoe UI", 10, "bold"),
                 bg=self.BG, fg=self.FG, anchor="w").pack(fill=tk.X, padx=8, pady=(4, 2))
        self.exp_preview = tk.Text(right, font=("Consolas", 9), bg=self.BG_SECONDARY,
                                    fg=self.FG, height=6, relief=tk.FLAT, wrap=tk.WORD,
                                    state=tk.DISABLED)
        self.exp_preview.pack(fill=tk.X, padx=8, pady=(0, 8))

        # Output log
        tk.Label(tab, text="Output Log", font=("Segoe UI", 10, "bold"),
                 bg=self.BG, fg=self.FG, anchor="w").pack(fill=tk.X, padx=16, pady=(0, 2))
        self.log_text = tk.Text(tab, font=("Consolas", 9), bg=self.BG_SECONDARY,
                                 fg=self.FG, height=6, relief=tk.FLAT, wrap=tk.WORD,
                                 state=tk.DISABLED)
        self.log_text.pack(fill=tk.X, padx=16, pady=(0, 8))

        # Load file lists
        self._refresh_gen_csv_list()
        self._refresh_exp_csv_list()

    def _log(self, msg: str):
        """Append a message to the output log."""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _count_csv_rows(self, path: Path) -> int:
        """Count data rows in a CSV (excluding header)."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return max(0, sum(1 for _ in f) - 1)
        except Exception:
            return 0

    def _count_csv_scenarios(self, path: Path) -> int:
        """Count rows that have a Scenario column value."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if "Scenario" not in (reader.fieldnames or []):
                    return self._count_csv_rows(path)
                return sum(1 for row in reader if row.get("Scenario", "").strip())
        except Exception:
            return 0

    def _file_modified(self, path: Path) -> str:
        """Return human-readable modification time."""
        try:
            ts = path.stat().st_mtime
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "?"

    # ── Scenario Generation CSV methods ──────────────────────────────────────

    def _refresh_gen_csv_list(self):
        """Refresh the scenario generation CSV file list."""
        for item in self.gen_tree.get_children():
            self.gen_tree.delete(item)

        # Find all CSVs in the testing_suite root that look like scenario generators
        for f in sorted(SCENARIO_CSV_DIR.glob("*.csv")):
            if f.name.startswith("."):
                continue
            # Skip comparison_results.csv and files in subdirs
            if f.name == "comparison_results.csv":
                continue
            rows = self._count_csv_rows(f)
            modified = self._file_modified(f)
            self.gen_tree.insert("", tk.END, iid=str(f),
                                  values=(f.name, rows, modified))

    def _on_gen_csv_select(self, event):
        """Show preview when a scenario CSV is selected."""
        sel = self.gen_tree.selection()
        if not sel:
            return
        path = Path(sel[0])
        preview = csv_preview(path, max_rows=5)
        self.gen_preview.config(state=tk.NORMAL)
        self.gen_preview.delete("1.0", tk.END)
        self.gen_preview.insert("1.0", f"{path.name}\n\n{preview}")
        self.gen_preview.config(state=tk.DISABLED)

    def _upload_scenario_csv(self):
        """Upload a CSV to be used for scenario generation."""
        file_path = filedialog.askopenfilename(
            title="Select Scenario Generation CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=str(Path.home() / "Downloads")
        )
        if not file_path:
            return

        src = Path(file_path)
        dest = SCENARIO_CSV_DIR / src.name

        if dest.exists():
            overwrite = messagebox.askyesno(
                "File Exists",
                f"'{src.name}' already exists in the testing suite.\n\nOverwrite it?"
            )
            if not overwrite:
                return

        try:
            shutil.copy2(src, dest)
            self._log(f"Uploaded scenario CSV: {src.name} -> {dest}")
            self.status_bar.config(text=f"Uploaded {src.name}")
            self._refresh_gen_csv_list()
        except Exception as e:
            messagebox.showerror("Upload Error", f"Failed to copy file:\n{e}")

    def _run_generator(self):
        """Run the appropriate generator script for the selected CSV."""
        sel = self.gen_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select a scenario CSV first.")
            return

        csv_path = Path(sel[0])
        csv_name = csv_path.name.lower()

        # Auto-detect which generator to use based on filename
        generator = None
        for key, cfg in GENERATOR_SCRIPTS.items():
            # Match by keywords in the filename
            keywords = key.lower().split()
            if all(kw in csv_name for kw in keywords):
                generator = (key, cfg)
                break

        if not generator:
            # Build unified choice list: all GENERATOR_SCRIPTS + custom suites without one
            choices = list(GENERATOR_SCRIPTS.keys())
            for suite_name in TEST_SUITES:
                if suite_name not in choices:
                    choices.append(suite_name)

            if not choices:
                messagebox.showinfo("No Options",
                                    "No generator scripts or suites are configured.")
                return

            dialog = GeneratorPickerDialog(self.root, choices)
            if dialog.result is None:
                return

            picked = dialog.result
            if picked in GENERATOR_SCRIPTS:
                generator = (picked, GENERATOR_SCRIPTS[picked])
            else:
                # Custom suite with no generator — prompt user to browse for a script
                script_path = filedialog.askopenfilename(
                    title=f"Select Generator Script for '{picked}'",
                    filetypes=[("Python files", "*.py"), ("All files", "*.*")],
                    initialdir=str(BASE_DIR)
                )
                if not script_path:
                    return

                suite_cfg = TEST_SUITES[picked]
                gen_cfg = {
                    "script": Path(script_path),
                    "output_dir": suite_cfg.get("scenario_json_dir", BASE_DIR),
                    "csv_var": "csv_path",
                }
                GENERATOR_SCRIPTS[picked] = gen_cfg
                generator = (picked, gen_cfg)

                # Persist the generator script into the custom suite config
                if picked in self._custom_suites:
                    self._custom_suites[picked]["generator_script"] = Path(script_path)
                    _save_custom_suites(self._custom_suites)
                    self._log(f"Saved generator script for '{picked}': {Path(script_path).name}")

        gen_name, gen_cfg = generator
        script = gen_cfg["script"]

        if not script.exists():
            messagebox.showerror("Script Not Found", f"Generator script not found:\n{script}")
            return

        self._log(f"Running {gen_name} generator...")
        self._log(f"  Script: {script.name}")
        self._log(f"  CSV: {csv_path.name}")
        self.root.update_idletasks()

        try:
            # Run the generator script, overriding csv_path via a wrapper
            # We create a small wrapper that sets csv_path then runs the script
            wrapper_code = f"""
import sys
csv_path = r"{csv_path}"
# Execute the generator script with our csv_path
with open(r"{script}", "r") as f:
    lines = f.readlines()
# Replace the hardcoded csv_path line in the script
new_lines = []
replaced = False
for line in lines:
    if not replaced and line.strip().startswith("csv_path"):
        new_lines.append('csv_path = r"' + csv_path + '"\\n')
        replaced = True
    else:
        new_lines.append(line)
code = "".join(new_lines)
exec(code)
"""
            result = subprocess.run(
                [sys.executable, "-c", wrapper_code],
                capture_output=True, text=True, timeout=60,
                cwd=str(BASE_DIR)
            )

            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    self._log(f"  {line}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    self._log(f"  [stderr] {line}")

            if result.returncode == 0:
                self._log(f"Generator completed successfully.")
                self.status_bar.config(text=f"Generated test JSONs from {csv_path.name}")
            else:
                self._log(f"Generator failed with exit code {result.returncode}")
                messagebox.showwarning("Generator Error",
                                        f"Script exited with code {result.returncode}.\nCheck the output log.")
        except subprocess.TimeoutExpired:
            self._log("Generator timed out after 60s")
            messagebox.showwarning("Timeout", "Generator script timed out after 60 seconds.")
        except Exception as e:
            self._log(f"Error running generator: {e}")
            messagebox.showerror("Error", f"Failed to run generator:\n{e}")

    # ── Expected Output CSV methods ──────────────────────────────────────────

    def _refresh_exp_csv_list(self):
        """Refresh the expected output CSV file list."""
        for item in self.exp_tree.get_children():
            self.exp_tree.delete(item)

        if not EXPECTED_OUTPUT_DIR.exists():
            EXPECTED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Build reverse map: which suites use which CSV
        active_map = {}
        for suite_name, cfg in TEST_SUITES.items():
            csv_path = cfg["expected_csv"]
            if csv_path.exists():
                resolved = str(csv_path.resolve())
                if resolved not in active_map:
                    active_map[resolved] = []
                active_map[resolved].append(suite_name)

        for f in sorted(EXPECTED_OUTPUT_DIR.glob("*.csv")):
            if f.name.startswith("."):
                continue
            scenarios = self._count_csv_scenarios(f)
            modified = self._file_modified(f)
            resolved = str(f.resolve())
            active_for = ", ".join(active_map.get(resolved, []))
            self.exp_tree.insert("", tk.END, iid=str(f),
                                  values=(f.name, scenarios, modified, active_for))

    def _on_exp_csv_select(self, event):
        """Show preview when an expected output CSV is selected."""
        sel = self.exp_tree.selection()
        if not sel:
            return
        path = Path(sel[0])
        preview = csv_preview(path, max_rows=5)
        self.exp_preview.config(state=tk.NORMAL)
        self.exp_preview.delete("1.0", tk.END)
        self.exp_preview.insert("1.0", f"{path.name}\n\n{preview}")
        self.exp_preview.config(state=tk.DISABLED)

    def _upload_expected_csv(self):
        """Upload a CSV to be used as expected output for validation."""
        file_path = filedialog.askopenfilename(
            title="Select Expected Output CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=str(Path.home() / "Downloads")
        )
        if not file_path:
            return

        src = Path(file_path)
        dest = EXPECTED_OUTPUT_DIR / src.name

        if dest.exists():
            overwrite = messagebox.askyesno(
                "File Exists",
                f"'{src.name}' already exists in expected_output.\n\nOverwrite it?"
            )
            if not overwrite:
                return

        try:
            shutil.copy2(src, dest)
            self._log(f"Uploaded expected output CSV: {src.name} -> {dest}")
            self.status_bar.config(text=f"Uploaded {src.name} to expected_output/")
            self._refresh_exp_csv_list()
        except Exception as e:
            messagebox.showerror("Upload Error", f"Failed to copy file:\n{e}")

    def _set_active_expected(self):
        """Set the selected expected output CSV as the active one for a suite."""
        sel = self.exp_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select an expected output CSV first.")
            return

        csv_path = Path(sel[0])
        suite_names = list(TEST_SUITES.keys())

        dialog = SuitePickerDialog(self.root, suite_names, csv_path.name)
        if dialog.result is None:
            return

        suite_name = dialog.result
        TEST_SUITES[suite_name]["expected_csv"] = csv_path

        self._log(f"Set '{csv_path.name}' as active expected output for '{suite_name}'")
        self.status_bar.config(text=f"'{csv_path.name}' now active for {suite_name}")
        self._refresh_exp_csv_list()

        # If this suite is currently loaded, refresh comparison
        if self.suite_var.get() == suite_name:
            self._on_suite_change()

    # ── Execute Tests Tab ──────────────────────────────────────────────────

    def _build_execute_tab(self):
        tab = self.execute_tab

        # Controls bar
        controls = tk.Frame(tab, bg=self.BG, pady=8, padx=12)
        controls.pack(fill=tk.X)

        tk.Label(controls, text="Suite:", font=("Segoe UI", 10),
                 bg=self.BG, fg=self.FG_DIM).pack(side=tk.LEFT, padx=(0, 5))
        self.exec_suite_var = tk.StringVar()
        self.exec_suite_combo = ttk.Combobox(controls, textvariable=self.exec_suite_var,
                                              values=list(TEST_SUITES.keys()), state="readonly", width=25)
        self.exec_suite_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.exec_suite_combo.bind("<<ComboboxSelected>>", lambda e: self._exec_load_scenarios())

        self._make_button(controls, "Reload", self._exec_load_scenarios).pack(side=tk.LEFT, padx=(0, 20))

        # Dropbox path display
        tk.Label(controls, text="Dropbox:", font=("Segoe UI", 9),
                 bg=self.BG, fg=self.FG_DIM).pack(side=tk.LEFT, padx=(10, 4))
        tk.Label(controls, text=str(ORDER_DROPBOX), font=("Consolas", 9),
                 bg=self.BG, fg=self.ACCENT).pack(side=tk.LEFT)

        # Summary + action buttons bar
        action_bar = tk.Frame(tab, bg=self.BG, padx=12, pady=4)
        action_bar.pack(fill=tk.X)

        self.exec_summary_label = tk.Label(action_bar, text="Select a suite to load scenarios",
                                            font=("Segoe UI", 10), bg=self.BG, fg=self.FG_DIM)
        self.exec_summary_label.pack(side=tk.LEFT)

        btn_frame = tk.Frame(action_bar, bg=self.BG)
        btn_frame.pack(side=tk.RIGHT)

        self._make_button(btn_frame, "Rerun Failed",
                          self._exec_rerun_failed, color=self.RED, width=14).pack(side=tk.LEFT, padx=(0, 8))
        self._make_button(btn_frame, "Copy Selected to Dropbox",
                          self._exec_copy_selected, color=self.ACCENT, width=24).pack(side=tk.LEFT, padx=(0, 8))
        self._make_button(btn_frame, "Copy ALL to Dropbox",
                          self._exec_copy_all, color=self.GREEN, width=20).pack(side=tk.LEFT)

        # Selection helpers bar
        sel_bar = tk.Frame(tab, bg=self.BG, padx=12, pady=2)
        sel_bar.pack(fill=tk.X)

        self._make_button(sel_bar, "Select All",
                          self._exec_select_all, color=self.BG_SECONDARY, width=10).pack(side=tk.LEFT, padx=(0, 4))
        self._make_button(sel_bar, "Deselect All",
                          self._exec_deselect_all, color=self.BG_SECONDARY, width=10).pack(side=tk.LEFT, padx=(0, 4))
        self._make_button(sel_bar, "Invert Selection",
                          self._exec_invert_selection, color=self.BG_SECONDARY, width=14).pack(side=tk.LEFT, padx=(0, 4))
        self._make_button(sel_bar, "Select Failed",
                          self._exec_select_failed, color=self.RED, width=12).pack(side=tk.LEFT, padx=(0, 4))
        self._make_button(sel_bar, "Select Missing",
                          self._exec_select_missing, color=self.YELLOW, width=14).pack(side=tk.LEFT, padx=(0, 16))

        # Range entry
        tk.Label(sel_bar, text="Select range:", font=("Segoe UI", 9),
                 bg=self.BG, fg=self.FG_DIM).pack(side=tk.LEFT, padx=(0, 4))
        self.exec_range_var = tk.StringVar()
        range_entry = tk.Entry(sel_bar, textvariable=self.exec_range_var,
                                font=("Consolas", 10), bg=self.BG_SECONDARY, fg=self.FG,
                                insertbackground=self.FG, relief=tk.FLAT, width=24)
        range_entry.pack(side=tk.LEFT, padx=(0, 4))
        self._make_button(sel_bar, "Apply",
                          self._exec_apply_range, color=self.BG_SECONDARY, width=6).pack(side=tk.LEFT)

        tk.Label(sel_bar, text="(e.g. 1-10, 15, 20-25)", font=("Segoe UI", 8),
                 bg=self.BG, fg=self.FG_DIM).pack(side=tk.LEFT, padx=(6, 0))

        # Scenario list with checkboxes (Treeview with check column)
        list_frame = tk.Frame(tab, bg=self.BG, padx=12)
        list_frame.pack(fill=tk.BOTH, expand=True)

        exec_cols = ("selected", "scenario", "size", "modified")
        self.exec_tree = ttk.Treeview(list_frame, columns=exec_cols, show="headings",
                                       style="FileList.Treeview")
        self.exec_tree.heading("selected", text="Sel")
        self.exec_tree.heading("scenario", text="Scenario JSON")
        self.exec_tree.heading("size", text="Size")
        self.exec_tree.heading("modified", text="Last Modified")
        self.exec_tree.column("selected", width=40, minwidth=40, anchor="center")
        self.exec_tree.column("scenario", width=300, minwidth=150)
        self.exec_tree.column("size", width=80, minwidth=50, anchor="e")
        self.exec_tree.column("modified", width=150, minwidth=100)

        exec_scroll = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.exec_tree.yview)
        self.exec_tree.configure(yscrollcommand=exec_scroll.set)
        exec_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.exec_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Toggle selection on click
        self.exec_tree.bind("<ButtonRelease-1>", self._exec_toggle_selection)

        # Track selected state: {iid: bool}
        self._exec_selected = {}

        # Execute log
        tk.Label(tab, text="Execution Log", font=("Segoe UI", 10, "bold"),
                 bg=self.BG, fg=self.FG, anchor="w").pack(fill=tk.X, padx=12, pady=(8, 2))
        self.exec_log = tk.Text(tab, font=("Consolas", 9), bg=self.BG_SECONDARY,
                                 fg=self.FG, height=8, relief=tk.FLAT, wrap=tk.WORD,
                                 state=tk.DISABLED)
        self.exec_log.pack(fill=tk.X, padx=12, pady=(0, 8))

    def _exec_log_msg(self, msg: str):
        """Append a message to the execute log."""
        self.exec_log.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.exec_log.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.exec_log.see(tk.END)
        self.exec_log.config(state=tk.DISABLED)

    def _exec_load_scenarios(self):
        """Load scenario JSONs for the selected suite into the list."""
        suite_name = self.exec_suite_var.get()
        if not suite_name:
            return

        cfg = TEST_SUITES.get(suite_name)
        if not cfg:
            return

        json_dir = cfg.get("scenario_json_dir")
        prefix = cfg.get("scenario_prefix", "")

        for item in self.exec_tree.get_children():
            self.exec_tree.delete(item)
        self._exec_selected.clear()

        if not json_dir or not json_dir.exists():
            self.exec_summary_label.config(
                text=f"No scenario JSON directory found for {suite_name}")
            return

        # Find all JSONs matching the prefix
        json_files = sorted([
            f for f in json_dir.glob("*.json")
            if f.stem.startswith(prefix) and not f.stem.endswith("_combined")
        ])

        for f in json_files:
            size_bytes = f.stat().st_size
            if size_bytes >= 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes} B"
            modified = self._file_modified(f)
            iid = str(f)
            self.exec_tree.insert("", tk.END, iid=iid,
                                   values=("[ ]", f.name, size_str, modified))
            self._exec_selected[iid] = False

        total = len(json_files)
        self.exec_summary_label.config(text=f"{total} scenario JSONs found for {suite_name}")
        self.status_bar.config(text=f"Loaded {total} scenarios from {json_dir.name}/")

    def _exec_toggle_selection(self, event):
        """Toggle the selection checkbox for a clicked row."""
        item = self.exec_tree.identify_row(event.y)
        if not item or item not in self._exec_selected:
            return

        self._exec_selected[item] = not self._exec_selected[item]
        current_vals = list(self.exec_tree.item(item, "values"))
        current_vals[0] = "[X]" if self._exec_selected[item] else "[ ]"
        self.exec_tree.item(item, values=current_vals)
        self._exec_update_selected_count()

    def _exec_update_selected_count(self):
        """Update the summary label with the selected count."""
        selected = sum(1 for v in self._exec_selected.values() if v)
        total = len(self._exec_selected)
        suite = self.exec_suite_var.get() or "?"
        self.exec_summary_label.config(
            text=f"{total} scenarios  |  {selected} selected for {suite}")

    def _exec_select_all(self):
        for iid in self._exec_selected:
            self._exec_selected[iid] = True
            vals = list(self.exec_tree.item(iid, "values"))
            vals[0] = "[X]"
            self.exec_tree.item(iid, values=vals)
        self._exec_update_selected_count()

    def _exec_deselect_all(self):
        for iid in self._exec_selected:
            self._exec_selected[iid] = False
            vals = list(self.exec_tree.item(iid, "values"))
            vals[0] = "[ ]"
            self.exec_tree.item(iid, values=vals)
        self._exec_update_selected_count()

    def _exec_invert_selection(self):
        for iid in self._exec_selected:
            self._exec_selected[iid] = not self._exec_selected[iid]
            vals = list(self.exec_tree.item(iid, "values"))
            vals[0] = "[X]" if self._exec_selected[iid] else "[ ]"
            self.exec_tree.item(iid, values=vals)
        self._exec_update_selected_count()

    def _exec_parse_range(self, range_str: str) -> set:
        """Parse a range string like '1-10, 15, 20-25' into a set of ints."""
        numbers = set()
        for part in range_str.replace(" ", "").split(","):
            if not part:
                continue
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    for n in range(int(start), int(end) + 1):
                        numbers.add(n)
                except (ValueError, TypeError):
                    pass
            else:
                try:
                    numbers.add(int(part))
                except (ValueError, TypeError):
                    pass
        return numbers

    def _exec_apply_range(self):
        """Select scenarios matching the range entry (by scenario number suffix)."""
        range_str = self.exec_range_var.get().strip()
        if not range_str:
            return

        target_nums = self._exec_parse_range(range_str)
        if not target_nums:
            messagebox.showinfo("Invalid Range",
                                "Could not parse range. Use format like: 1-10, 15, 20-25")
            return

        # First deselect all
        self._exec_deselect_all()

        # Select matching scenarios by their numeric suffix
        selected = 0
        for iid in self._exec_selected:
            path = Path(iid)
            # Extract the number from e.g. "3X8X_DV_0042" -> 42
            stem = path.stem
            parts = stem.rsplit("_", 1)
            if len(parts) == 2:
                try:
                    num = int(parts[1])
                    if num in target_nums:
                        self._exec_selected[iid] = True
                        vals = list(self.exec_tree.item(iid, "values"))
                        vals[0] = "[X]"
                        self.exec_tree.item(iid, values=vals)
                        selected += 1
                except (ValueError, TypeError):
                    pass

        self._exec_update_selected_count()
        self._exec_log_msg(f"Range '{range_str}' matched {selected} scenario(s)")

    def _exec_get_failed_scenarios(self) -> set:
        """Get scenario names that failed or partially failed in the comparison results."""
        suite_name = self.exec_suite_var.get()
        if not suite_name:
            return set()

        cfg = TEST_SUITES.get(suite_name)
        if not cfg:
            return set()

        # Run comparison for this suite to get current pass/fail status
        scenarios = run_comparison(cfg)
        failed = set()
        for name, info in scenarios.items():
            if info["status"] in ("fail", "partial", "no_output"):
                failed.add(name)
        return failed

    def _exec_get_missing_scenarios(self) -> set:
        """Get scenario names that have no actual output."""
        suite_name = self.exec_suite_var.get()
        if not suite_name:
            return set()

        cfg = TEST_SUITES.get(suite_name)
        if not cfg:
            return set()

        scenarios = run_comparison(cfg)
        missing = set()
        for name, info in scenarios.items():
            if info["status"] == "no_output":
                missing.add(name)
        return missing

    def _exec_select_missing(self):
        """Select only scenarios that have no actual output."""
        suite_name = self.exec_suite_var.get()
        if not suite_name:
            messagebox.showinfo("No Suite", "Select a suite first.")
            return

        if not self._exec_selected:
            messagebox.showinfo("No Scenarios", "Load scenarios first.")
            return

        missing_names = self._exec_get_missing_scenarios()
        if not missing_names:
            self._exec_log_msg(f"No missing scenarios found for {suite_name}")
            messagebox.showinfo("No Missing", f"All scenarios have output for {suite_name}.")
            return

        self._exec_deselect_all()

        selected = 0
        for iid in self._exec_selected:
            stem = Path(iid).stem
            if stem in missing_names:
                self._exec_selected[iid] = True
                vals = list(self.exec_tree.item(iid, "values"))
                vals[0] = "[X]"
                self.exec_tree.item(iid, values=vals)
                selected += 1

        self._exec_update_selected_count()
        self._exec_log_msg(f"Selected {selected} missing-output scenario(s) from {len(missing_names)} total missing")

    def _exec_select_failed(self):
        """Select only scenarios that failed in comparison results."""
        suite_name = self.exec_suite_var.get()
        if not suite_name:
            messagebox.showinfo("No Suite", "Select a suite first.")
            return

        if not self._exec_selected:
            messagebox.showinfo("No Scenarios", "Load scenarios first.")
            return

        failed_names = self._exec_get_failed_scenarios()
        if not failed_names:
            self._exec_log_msg(f"No failed scenarios found for {suite_name}")
            messagebox.showinfo("No Failures", f"All scenarios passed for {suite_name}.")
            return

        # Deselect all first
        self._exec_deselect_all()

        # Select scenarios whose filename stem matches a failed scenario name
        selected = 0
        for iid in self._exec_selected:
            stem = Path(iid).stem
            if stem in failed_names:
                self._exec_selected[iid] = True
                vals = list(self.exec_tree.item(iid, "values"))
                vals[0] = "[X]"
                self.exec_tree.item(iid, values=vals)
                selected += 1

        self._exec_update_selected_count()
        self._exec_log_msg(f"Selected {selected} failed/partial/no-output scenario(s) from {len(failed_names)} total failures")

    def _exec_rerun_failed(self):
        """One-click: find failed scenarios, copy their JSONs to dropbox."""
        suite_name = self.exec_suite_var.get()
        if not suite_name:
            messagebox.showinfo("No Suite", "Select a suite first.")
            return

        if not self._exec_selected:
            messagebox.showinfo("No Scenarios", "Load scenarios first.")
            return

        failed_names = self._exec_get_failed_scenarios()
        if not failed_names:
            self._exec_log_msg(f"No failed scenarios found for {suite_name}")
            messagebox.showinfo("No Failures", f"All scenarios passed for {suite_name}.")
            return

        # Find matching iids
        failed_iids = [iid for iid in self._exec_selected if Path(iid).stem in failed_names]
        if not failed_iids:
            self._exec_log_msg("Failed scenarios found in comparison but no matching JSONs in loaded list")
            return

        confirm = messagebox.askyesno(
            "Rerun Failed Tests",
            f"Copy {len(failed_iids)} failed/partial/no-output scenario JSON(s) to dropbox?\n\n"
            f"Failed: {len(failed_names)} scenarios\n"
            f"Dropbox: {ORDER_DROPBOX}\n\n"
            f"The folder monitor will begin processing them."
        )
        if not confirm:
            return

        # Also visually select them
        self._exec_deselect_all()
        for iid in failed_iids:
            self._exec_selected[iid] = True
            vals = list(self.exec_tree.item(iid, "values"))
            vals[0] = "[X]"
            self.exec_tree.item(iid, values=vals)
        self._exec_update_selected_count()

        self._exec_do_copy(failed_iids)

    def _exec_copy_all(self):
        """Copy ALL scenario JSONs to the dropbox folder."""
        if not self._exec_selected:
            messagebox.showinfo("No Scenarios", "Load a suite first.")
            return

        total = len(self._exec_selected)
        confirm = messagebox.askyesno(
            "Copy All to Dropbox",
            f"Copy all {total} scenario JSONs to the dropbox folder?\n\n"
            f"Dropbox: {ORDER_DROPBOX}\n\n"
            f"The folder monitor will begin processing them."
        )
        if not confirm:
            return

        self._exec_do_copy(list(self._exec_selected.keys()))

    def _exec_copy_selected(self):
        """Copy only selected scenario JSONs to the dropbox folder."""
        selected_iids = [iid for iid, sel in self._exec_selected.items() if sel]
        if not selected_iids:
            messagebox.showinfo("No Selection", "Select at least one scenario first.")
            return

        count = len(selected_iids)
        confirm = messagebox.askyesno(
            "Copy Selected to Dropbox",
            f"Copy {count} selected scenario JSON(s) to the dropbox folder?\n\n"
            f"Dropbox: {ORDER_DROPBOX}\n\n"
            f"The folder monitor will begin processing them."
        )
        if not confirm:
            return

        self._exec_do_copy(selected_iids)

    def _exec_do_copy(self, iids: list):
        """Actually copy the specified scenario JSONs to the dropbox folder."""
        if not ORDER_DROPBOX.exists():
            ORDER_DROPBOX.mkdir(parents=True, exist_ok=True)

        copied = 0
        errors = 0
        self._exec_log_msg(f"Copying {len(iids)} scenario(s) to {ORDER_DROPBOX}...")
        self.root.update_idletasks()

        for iid in iids:
            src = Path(iid)
            dest = ORDER_DROPBOX / src.name
            try:
                shutil.copy2(src, dest)
                copied += 1
            except Exception as e:
                self._exec_log_msg(f"  ERROR copying {src.name}: {e}")
                errors += 1

        self._exec_log_msg(f"Done: {copied} copied, {errors} error(s)")
        self.status_bar.config(text=f"Copied {copied} scenario JSON(s) to dropbox")

        if errors > 0:
            messagebox.showwarning("Copy Errors",
                                    f"{errors} file(s) failed to copy. Check the execution log.")

    # ── Suite Management ────────────────────────────────────────────────────

    def _refresh_suite_combos(self):
        """Update all suite comboboxes with the current TEST_SUITES keys."""
        suite_names = list(TEST_SUITES.keys())
        self.suite_combo["values"] = suite_names
        self.exec_suite_combo["values"] = suite_names

    def _create_new_suite(self):
        """Open dialog to create a new test suite."""
        dialog = NewSuiteDialog(self.root)
        if dialog.result is None:
            return

        name, cfg = dialog.result
        if name in TEST_SUITES:
            messagebox.showerror("Duplicate Name",
                                 f"A suite named '{name}' already exists.")
            return

        TEST_SUITES[name] = cfg
        self._custom_suites[name] = cfg

        # Register generator script if provided
        if cfg.get("generator_script"):
            GENERATOR_SCRIPTS[name] = {
                "script": cfg["generator_script"],
                "output_dir": cfg["scenario_json_dir"],
                "csv_var": "csv_path",
            }

        _save_custom_suites(self._custom_suites)

        self._refresh_suite_combos()
        self.suite_var.set(name)
        self._on_suite_change()
        self._refresh_exp_csv_list()
        self._log(f"Created new suite: {name}")
        self.status_bar.config(text=f"Created suite '{name}'")

    def _delete_current_suite(self):
        """Delete the currently selected suite (custom suites only)."""
        suite_name = self.suite_var.get()
        if not suite_name:
            return

        if suite_name in _BUILTIN_SUITE_NAMES:
            messagebox.showinfo("Cannot Delete",
                                f"'{suite_name}' is a built-in suite and cannot be deleted.")
            return

        confirm = messagebox.askyesno(
            "Delete Suite",
            f"Delete the custom suite '{suite_name}'?\n\n"
            f"This only removes the suite definition.\n"
            f"CSV files and test data are NOT deleted."
        )
        if not confirm:
            return

        del TEST_SUITES[suite_name]
        self._custom_suites.pop(suite_name, None)
        GENERATOR_SCRIPTS.pop(suite_name, None)
        _save_custom_suites(self._custom_suites)

        self._refresh_suite_combos()

        # Switch to first available suite
        remaining = list(TEST_SUITES.keys())
        if remaining:
            self.suite_var.set(remaining[0])
            self._on_suite_change()
        else:
            self.scenarios = {}
            self.scenario_listbox.delete(0, tk.END)

        self._refresh_exp_csv_list()
        self._log(f"Deleted suite: {suite_name}")
        self.status_bar.config(text=f"Deleted suite '{suite_name}'")

    # ── Comparison Tab Logic ─────────────────────────────────────────────────

    def _on_suite_change(self, *_):
        suite_name = self.suite_var.get()
        if not suite_name:
            return

        self.status_bar.config(text=f"Loading {suite_name}...")
        self.root.update_idletasks()

        cfg = TEST_SUITES[suite_name]
        self.scenarios = run_comparison(cfg)
        self.current_suite = suite_name
        self.current_filter = "all"

        total = len(self.scenarios)
        passed = sum(1 for s in self.scenarios.values() if s["status"] == "pass")
        failed = sum(1 for s in self.scenarios.values() if s["status"] == "fail")
        partial = sum(1 for s in self.scenarios.values() if s["status"] == "partial")
        no_out = sum(1 for s in self.scenarios.values() if s["status"] == "no_output")

        self.summary_label.config(
            text=f"{total} scenarios  |  "
                 f"Pass: {passed}  |  Fail: {failed}  |  Partial: {partial}  |  No output: {no_out}"
        )

        # Update CSV info bar
        expected_csv = cfg.get("expected_csv")
        scenario_csv = cfg.get("scenario_csv")
        exp_name = Path(expected_csv).name if expected_csv and Path(expected_csv).exists() else (f"{Path(expected_csv).name}  [MISSING]" if expected_csv else "N/A")
        scn_name = Path(scenario_csv).name if scenario_csv and Path(scenario_csv).exists() else (f"{Path(scenario_csv).name}  [MISSING]" if scenario_csv else "N/A")
        exp_color = self.FG_DIM if (expected_csv and Path(expected_csv).exists()) else self.RED
        scn_color = self.FG_DIM if (scenario_csv and Path(scenario_csv).exists()) else self.RED
        self.csv_info_expected.config(text=f"Expected Output CSV:  {exp_name}", fg=exp_color)
        self.csv_info_scenario.config(text=f"Scenario Gen CSV:       {scn_name}", fg=scn_color)

        counts = {"all": total, "pass": passed, "fail": failed,
                  "partial": partial, "no_output": no_out}
        labels = {"all": "All", "pass": "Pass", "fail": "Fail",
                  "partial": "Partial", "no_output": "No Output"}
        for key, btn in self.filter_buttons.items():
            btn.config(text=f"{labels[key]} ({counts[key]})")

        self._apply_filter()
        self.status_bar.config(text=f"Loaded {total} scenarios from {suite_name}")

    def _set_filter(self, filter_key):
        self.current_filter = filter_key
        for key, btn in self.filter_buttons.items():
            if key == filter_key:
                btn.config(bg=self.SURFACE, relief=tk.SUNKEN)
            else:
                btn.config(bg=self.BG_SECONDARY, relief=tk.FLAT)
        self._apply_filter()

    def _apply_filter(self):
        search_text = self.search_var.get().strip().lower()
        self.scenario_listbox.delete(0, tk.END)
        self.filtered_scenarios = []

        status_symbols = {"pass": ">>>", "fail": "X", "partial": "!", "no_output": "---"}

        for name in sorted(self.scenarios.keys()):
            info = self.scenarios[name]

            if self.current_filter != "all" and info["status"] != self.current_filter:
                continue
            if search_text and search_text not in name.lower():
                continue

            symbol = status_symbols.get(info["status"], "?")
            display = f"{symbol}  {name}  ({info['fail_count']}F {info['missing_count']}M)"
            self.scenario_listbox.insert(tk.END, display)
            self.filtered_scenarios.append(name)

            idx = self.scenario_listbox.size() - 1
            color_map = {"pass": self.GREEN, "fail": self.RED,
                         "partial": self.YELLOW, "no_output": self.FG_DIM}
            self.scenario_listbox.itemconfig(idx, fg=color_map.get(info["status"], self.FG))

    def _on_scenario_select(self, event):
        selection = self.scenario_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.filtered_scenarios):
            return
        scenario_name = self.filtered_scenarios[idx]
        self._show_scenario(scenario_name)

    def _show_scenario(self, scenario_name: str):
        self._current_scenario = scenario_name
        info = self.scenarios.get(scenario_name)
        if not info:
            return

        status_text = {
            "pass": "ALL PASS", "fail": "HAS FAILURES",
            "partial": "PARTIAL (missing params)", "no_output": "NO OUTPUT FILE"
        }
        self.detail_header.config(
            text=f"{scenario_name}  --  {status_text.get(info['status'], '?')}")
        self.detail_summary.config(
            text=f"{info['pass_count']} pass  |  {info['fail_count']} fail  |  "
                 f"{info['missing_count']} missing  |  {info['skip_count']} skipped"
        )
        self._refresh_detail()

    def _refresh_detail(self):
        if not hasattr(self, "_current_scenario"):
            return
        info = self.scenarios.get(self._current_scenario)
        if not info:
            return

        detail_filter = self.detail_filter_var.get()

        for item in self.tree.get_children():
            self.tree.delete(item)

        for p in info["params"]:
            if detail_filter == "fail" and p["result"] != "fail":
                continue
            if detail_filter == "missing" and p["result"] != "missing":
                continue

            result_display = {"pass": "PASS", "fail": "FAIL", "missing": "---", "skip": "."}.get(
                p["result"], "?")

            exp_display = p["expected"] if p["expected"] else "---"
            act_display = str(p["actual"]) if p["actual"] is not None else "---"

            self.tree.insert("", tk.END,
                             values=(p["name"], exp_display, act_display, result_display),
                             tags=(p["result"],))


# ─── Dialogs ─────────────────────────────────────────────────────────────────

class GeneratorPickerDialog(tk.Toplevel):
    """Dialog to pick which generator script or suite to use."""

    def __init__(self, parent, choices):
        super().__init__(parent)
        self.title("Select Generator")
        # Scale height to fit all choices
        height = 100 + len(choices) * 44
        self.geometry(f"400x{height}")
        self.configure(bg=TestViewerApp.BG)
        self.transient(parent)
        self.grab_set()
        self.result = None

        tk.Label(self, text="Which generator should be used\nfor this CSV?",
                 font=("Segoe UI", 10), bg=TestViewerApp.BG,
                 fg=TestViewerApp.FG, justify=tk.CENTER).pack(pady=(16, 12))

        for choice in choices:
            has_gen = choice in GENERATOR_SCRIPTS
            bg = TestViewerApp.ACCENT if has_gen else TestViewerApp.ORANGE
            label = choice if has_gen else f"{choice}  (browse for script...)"
            tk.Button(self, text=label, font=("Segoe UI", 10),
                      bg=bg, fg="#1e1e2e", relief=tk.FLAT,
                      padx=16, pady=6, width=32, cursor="hand2",
                      command=lambda c=choice: self._select(c)).pack(pady=4)

        tk.Button(self, text="Cancel", font=("Segoe UI", 9),
                  bg=TestViewerApp.BG_SECONDARY, fg=TestViewerApp.FG_DIM,
                  relief=tk.FLAT, padx=12, pady=4, cursor="hand2",
                  command=self.destroy).pack(pady=(8, 4))

        self.wait_window()

    def _select(self, choice):
        self.result = choice
        self.destroy()


class SuitePickerDialog(tk.Toplevel):
    """Dialog to pick which suite an expected CSV should be active for."""

    def __init__(self, parent, suite_names, csv_name):
        super().__init__(parent)
        self.title("Set Active Suite")
        self.geometry("400x220")
        self.configure(bg=TestViewerApp.BG)
        self.transient(parent)
        self.grab_set()
        self.result = None

        tk.Label(self, text=f"Set '{csv_name}' as active\nexpected output for which suite?",
                 font=("Segoe UI", 10), bg=TestViewerApp.BG,
                 fg=TestViewerApp.FG, justify=tk.CENTER).pack(pady=(16, 12))

        for name in suite_names:
            tk.Button(self, text=name, font=("Segoe UI", 10),
                      bg=TestViewerApp.ACCENT, fg="#1e1e2e", relief=tk.FLAT,
                      padx=16, pady=6, width=30, cursor="hand2",
                      command=lambda n=name: self._select(n)).pack(pady=4)

        tk.Button(self, text="Cancel", font=("Segoe UI", 9),
                  bg=TestViewerApp.BG_SECONDARY, fg=TestViewerApp.FG_DIM,
                  relief=tk.FLAT, padx=12, pady=4, cursor="hand2",
                  command=self.destroy).pack(pady=(8, 4))

        self.wait_window()

    def _select(self, name):
        self.result = name
        self.destroy()


class NewSuiteDialog(tk.Toplevel):
    """Dialog to create a new test suite with all required configuration."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Create New Test Suite")
        self.geometry("600x650")
        self.configure(bg=TestViewerApp.BG)
        self.transient(parent)
        self.grab_set()
        self.result = None

        pad = {"padx": 16, "pady": (0, 2)}
        entry_pad = {"padx": 16, "pady": (0, 10)}

        tk.Label(self, text="Create New Test Suite",
                 font=("Segoe UI", 13, "bold"),
                 bg=TestViewerApp.BG, fg=TestViewerApp.FG).pack(pady=(16, 12))

        # Suite Name
        tk.Label(self, text="Suite Display Name  (e.g. 'Panel 3X82 (3X82_PV)')",
                 font=("Segoe UI", 9), bg=TestViewerApp.BG,
                 fg=TestViewerApp.FG_DIM, anchor="w").pack(fill=tk.X, **pad)
        self.name_var = tk.StringVar()
        tk.Entry(self, textvariable=self.name_var, font=("Segoe UI", 10),
                 bg=TestViewerApp.BG_SECONDARY, fg=TestViewerApp.FG,
                 insertbackground=TestViewerApp.FG, relief=tk.FLAT).pack(
            fill=tk.X, **entry_pad)

        # Scenario Prefix
        tk.Label(self, text="Scenario Prefix  (e.g. '3X82_PV_'  — must end with underscore)",
                 font=("Segoe UI", 9), bg=TestViewerApp.BG,
                 fg=TestViewerApp.FG_DIM, anchor="w").pack(fill=tk.X, **pad)
        self.prefix_var = tk.StringVar()
        tk.Entry(self, textvariable=self.prefix_var, font=("Segoe UI", 10),
                 bg=TestViewerApp.BG_SECONDARY, fg=TestViewerApp.FG,
                 insertbackground=TestViewerApp.FG, relief=tk.FLAT).pack(
            fill=tk.X, **entry_pad)

        # Actual File Pattern
        tk.Label(self, text="Actual Output File Pattern  (e.g. 'D1_all_parameters.json' or 'S1_all_parameters.json')",
                 font=("Segoe UI", 9), bg=TestViewerApp.BG,
                 fg=TestViewerApp.FG_DIM, anchor="w").pack(fill=tk.X, **pad)
        self.pattern_var = tk.StringVar(value="S1_all_parameters.json")
        tk.Entry(self, textvariable=self.pattern_var, font=("Segoe UI", 10),
                 bg=TestViewerApp.BG_SECONDARY, fg=TestViewerApp.FG,
                 insertbackground=TestViewerApp.FG, relief=tk.FLAT).pack(
            fill=tk.X, **entry_pad)

        # Expected Output CSV
        tk.Label(self, text="Expected Output CSV  (select from expected_output/ or browse)",
                 font=("Segoe UI", 9), bg=TestViewerApp.BG,
                 fg=TestViewerApp.FG_DIM, anchor="w").pack(fill=tk.X, **pad)
        csv_frame = tk.Frame(self, bg=TestViewerApp.BG)
        csv_frame.pack(fill=tk.X, **entry_pad)
        self.csv_var = tk.StringVar()
        tk.Entry(csv_frame, textvariable=self.csv_var, font=("Segoe UI", 10),
                 bg=TestViewerApp.BG_SECONDARY, fg=TestViewerApp.FG,
                 insertbackground=TestViewerApp.FG, relief=tk.FLAT).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Button(csv_frame, text="Browse...", font=("Segoe UI", 9),
                  bg=TestViewerApp.ACCENT, fg="#1e1e2e", relief=tk.FLAT,
                  padx=8, cursor="hand2",
                  command=self._browse_csv).pack(side=tk.LEFT)

        # Actual Output Directories
        tk.Label(self, text="Actual Output Directories  (one per line — where scenario output folders live)",
                 font=("Segoe UI", 9), bg=TestViewerApp.BG,
                 fg=TestViewerApp.FG_DIM, anchor="w").pack(fill=tk.X, **pad)
        self.dirs_text = tk.Text(self, font=("Consolas", 9),
                                  bg=TestViewerApp.BG_SECONDARY,
                                  fg=TestViewerApp.FG, height=3, relief=tk.FLAT,
                                  insertbackground=TestViewerApp.FG)
        # Pre-fill with common actual dirs
        default_dirs = str(REPO_ROOT / "S2S File Test" / "output" / "parameters") + "\n" + str(BASE_DIR / "actual_output")
        self.dirs_text.insert("1.0", default_dirs)
        self.dirs_text.pack(fill=tk.X, **entry_pad)

        # Scenario JSON Directory
        tk.Label(self, text="Scenario JSON Directory  (where generated test JSONs are stored)",
                 font=("Segoe UI", 9), bg=TestViewerApp.BG,
                 fg=TestViewerApp.FG_DIM, anchor="w").pack(fill=tk.X, **pad)
        json_dir_frame = tk.Frame(self, bg=TestViewerApp.BG)
        json_dir_frame.pack(fill=tk.X, **entry_pad)
        self.json_dir_var = tk.StringVar(value=str(BASE_DIR / "stile_validation_tests"))
        tk.Entry(json_dir_frame, textvariable=self.json_dir_var, font=("Segoe UI", 10),
                 bg=TestViewerApp.BG_SECONDARY, fg=TestViewerApp.FG,
                 insertbackground=TestViewerApp.FG, relief=tk.FLAT).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Button(json_dir_frame, text="Browse...", font=("Segoe UI", 9),
                  bg=TestViewerApp.ACCENT, fg="#1e1e2e", relief=tk.FLAT,
                  padx=8, cursor="hand2",
                  command=self._browse_json_dir).pack(side=tk.LEFT)

        # Generator Script (optional)
        tk.Label(self, text="Generator Script  (optional — Python script to generate test JSONs from a CSV)",
                 font=("Segoe UI", 9), bg=TestViewerApp.BG,
                 fg=TestViewerApp.FG_DIM, anchor="w").pack(fill=tk.X, **pad)
        gen_frame = tk.Frame(self, bg=TestViewerApp.BG)
        gen_frame.pack(fill=tk.X, **entry_pad)
        self.gen_script_var = tk.StringVar()
        tk.Entry(gen_frame, textvariable=self.gen_script_var, font=("Segoe UI", 10),
                 bg=TestViewerApp.BG_SECONDARY, fg=TestViewerApp.FG,
                 insertbackground=TestViewerApp.FG, relief=tk.FLAT).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Button(gen_frame, text="Browse...", font=("Segoe UI", 9),
                  bg=TestViewerApp.ACCENT, fg="#1e1e2e", relief=tk.FLAT,
                  padx=8, cursor="hand2",
                  command=self._browse_gen_script).pack(side=tk.LEFT)

        # Buttons
        btn_frame = tk.Frame(self, bg=TestViewerApp.BG)
        btn_frame.pack(pady=(16, 12))

        tk.Button(btn_frame, text="Create Suite", font=("Segoe UI", 10, "bold"),
                  bg=TestViewerApp.GREEN, fg="#1e1e2e", relief=tk.FLAT,
                  padx=20, pady=6, cursor="hand2",
                  command=self._create).pack(side=tk.LEFT, padx=(0, 12))
        tk.Button(btn_frame, text="Cancel", font=("Segoe UI", 10),
                  bg=TestViewerApp.BG_SECONDARY, fg=TestViewerApp.FG_DIM,
                  relief=tk.FLAT, padx=16, pady=6, cursor="hand2",
                  command=self.destroy).pack(side=tk.LEFT)

        self.wait_window()

    def _browse_csv(self):
        path = filedialog.askopenfilename(
            title="Select Expected Output CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=str(EXPECTED_OUTPUT_DIR)
        )
        if path:
            self.csv_var.set(path)

    def _browse_json_dir(self):
        path = filedialog.askdirectory(
            title="Select Scenario JSON Directory",
            initialdir=str(BASE_DIR)
        )
        if path:
            self.json_dir_var.set(path)

    def _browse_gen_script(self):
        path = filedialog.askopenfilename(
            title="Select Generator Script",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")],
            initialdir=str(BASE_DIR)
        )
        if path:
            self.gen_script_var.set(path)

    def _create(self):
        name = self.name_var.get().strip()
        prefix = self.prefix_var.get().strip()
        pattern = self.pattern_var.get().strip()
        csv_path = self.csv_var.get().strip()
        json_dir = self.json_dir_var.get().strip()
        gen_script = self.gen_script_var.get().strip()
        dirs_raw = self.dirs_text.get("1.0", tk.END).strip()

        # Validation
        if not name:
            messagebox.showwarning("Missing Field", "Suite name is required.", parent=self)
            return
        if not prefix:
            messagebox.showwarning("Missing Field", "Scenario prefix is required.", parent=self)
            return
        if not pattern:
            messagebox.showwarning("Missing Field", "Actual file pattern is required.", parent=self)
            return
        if not csv_path:
            messagebox.showwarning("Missing Field", "Expected output CSV is required.", parent=self)
            return

        actual_dirs = []
        for line in dirs_raw.splitlines():
            line = line.strip()
            if line:
                actual_dirs.append(Path(line))

        if not actual_dirs:
            messagebox.showwarning("Missing Field",
                                   "At least one actual output directory is required.", parent=self)
            return

        cfg = {
            "expected_csv": Path(csv_path),
            "actual_dirs": actual_dirs,
            "scenario_prefix": prefix,
            "actual_file_pattern": pattern,
            "param_name_mapping": {},
            "scenario_json_dir": Path(json_dir) if json_dir else BASE_DIR,
        }
        if gen_script:
            cfg["generator_script"] = Path(gen_script)

        self.result = (name, cfg)
        self.destroy()


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()

    # Try to set DPI awareness on Windows
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = TestViewerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

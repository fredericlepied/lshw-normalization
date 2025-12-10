# Hardware Normalization Utilities

Python utilities for normalizing and validating lshw JSON files for ElasticSearch ingestion.

## Overview

These utilities help ensure lshw hardware inventory JSON files have consistent types across all files, making them suitable for ElasticSearch ingestion without type conflicts.

## Utilities

### 1. `analyze_lshw.py` - Type Analysis Tool

Analyzes multiple lshw JSON files to detect type inconsistencies.

**Usage:**
```bash
python3 analyze_lshw.py <files or directories> [-o output_report.txt]
```

**Features:**
- Detects fields with inconsistent types across files
- Identifies numeric values stored as strings
- Identifies boolean values stored as strings
- Identifies fields missing in some files
- Generates detailed reports in text and JSON formats

**Example:**
```bash
python3 analyze_lshw.py samples/ -o analysis_report.txt
```

**Output:**
- Human-readable report (specified with `-o`)
- Detailed JSON analysis (`analysis_details.json`)

### 2. `normalize_lshw.py` - Type Normalization Tool

Normalizes lshw JSON files by converting types to their proper representations.

**Usage:**
```bash
python3 normalize_lshw.py <files or directories> [options]
```

**Options:**
- `-o, --output-dir DIR` - Output directory for normalized files (default: overwrite input)
- `--suffix SUFFIX` - Suffix to add to output filenames (default: `.normalized`)
- `--strict` - Fail on any normalization errors (default: log warnings and continue)

**Features:**
- Converts numeric strings to integers/floats
- Converts boolean strings ("yes"/"no", "true"/"false") to booleans
- Normalizes `logicalname` field to always be an array
- Keeps `physid` and `version` as strings for consistency
- Preserves field structure and nesting

**Example:**
```bash
# Normalize files in-place
python3 normalize_lshw.py samples/*.json

# Normalize to output directory
python3 normalize_lshw.py samples/ -o normalized_samples --suffix ""
```

**Statistics Tracked:**
- Files processed and modified
- Numeric conversions performed
- Boolean conversions performed
- Array normalizations performed

### 3. `validate_lshw.py` - Type Validation Tool

Validates lshw JSON files against expected type schemas.

**Usage:**
```bash
python3 validate_lshw.py <files or directories> [options]
```

**Options:**
- `-o, --output FILE` - Output file for detailed validation report (JSON)
- `--strict` - Treat warnings as errors

**Features:**
- Validates field types against expected schemas
- Identifies remaining type inconsistencies
- Provides detailed error and warning reports
- Generates pass/fail status for each file

**Example:**
```bash
python3 validate_lshw.py normalized_samples/ -o validation_report.json
```

## Workflow

### Recommended Workflow

1. **Analyze** your files to understand type issues:
   ```bash
   python3 analyze_lshw.py samples/ -o analysis_report.txt
   ```

2. **Normalize** the files:
   ```bash
   python3 normalize_lshw.py samples/ -o normalized_samples --suffix ""
   ```

3. **Validate** the normalized files:
   ```bash
   python3 validate_lshw.py normalized_samples/ -o validation_report.json
   ```

## Test Results

Testing on 53 sample files:

### Before Normalization
- **Files failing validation:** 53/53 (100%)
- **Total errors:** ~12,000+
- **Total warnings:** ~11,000+

### After Normalization
- **Files passing validation:** 53/53 (100% ✓)
- **Total errors:** 0 (100% reduction)
- **Total warnings:** 0 (100% reduction)
- **Conversions performed:**
  - Numeric conversions: 10,423
  - Boolean conversions: 21,085
  - Array normalizations: 844

All files now pass validation successfully!

## Type Normalization Rules

### Numeric Fields
The following fields are converted from strings to numbers:
- `latency`, `cores`, `enabledcores`, `microcode`, `threads`
- `level`, `ansiversion`, `size`, `capacity`, `width`, `clock`
- `depth`, `FATs`, `logicalsectorsize`, `sectorsize`

### Boolean Fields
The following fields are converted from strings to booleans:
- Configuration: `claimed`, `disabled`, `broadcast`, `link`, `multicast`, `slave`
- Media: `removable`, `audio`, `dvd`
- String values converted: "yes"/"no", "true"/"false", "1"/"0"
- Descriptive capability strings: Converted to booleans based on content
  - Strings with negative indicators (" no ", "not ", "none", "disabled", "unsupported") → `false`
  - Other descriptive strings (e.g., "Audio CD playback", "support is removable") → `true`

### Special Cases
- **`physid`**: Kept as string for consistency (can be hex values like "0a")
- **`version`**: Kept as string for consistency (can be numeric or alphanumeric)
- **`logicalname`**: Normalized to always be an array (even if single value)
- **Capabilities**: Descriptive strings in capabilities are intelligently converted to booleans

## ElasticSearch Compatibility

These utilities ensure:
1. **Type consistency** - Same fields always have the same type
2. **Proper numeric types** - Numbers are stored as integers/floats, not strings
3. **Proper boolean types** - Booleans are stored as true/false, not "yes"/"no"
4. **Array consistency** - Fields that can be arrays are always arrays

This prevents ElasticSearch mapping conflicts that occur when the same field has different types across documents.

## Requirements

- Python 3.6+
- No external dependencies (uses only standard library)

## File Formats

### Input
- lshw JSON output files (generated with `lshw -json`)

### Output
- Normalized JSON files with corrected types
- Analysis reports (text and JSON)
- Validation reports (JSON)

## License

These utilities are provided as-is for normalizing lshw hardware inventory data.

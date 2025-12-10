#!/usr/bin/env python3
"""
Validate lshw JSON files for type consistency and ElasticSearch compatibility.

This script validates that lshw files:
1. Have consistent types for the same fields
2. Use proper numeric types (not strings) for numeric fields
3. Use proper boolean types (not strings) for boolean fields
4. Don't have unexpected type variations
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Optional
from collections import defaultdict


class LshwValidator:
    def __init__(self, reference_schema: Optional[Dict] = None):
        """
        Initialize validator.

        Args:
            reference_schema: Optional pre-defined schema to validate against
        """
        self.reference_schema = reference_schema
        self.errors = []
        self.warnings = []
        self.files_validated = 0
        self.files_passed = 0

        # Define expected types for known fields
        self.expected_types = {
            # Numeric fields
            "latency": (int, float),
            "cores": (int,),
            "enabledcores": (int,),
            "microcode": (int, str),  # Can be int or string like "218104848"
            "threads": (int,),
            "level": (int,),
            "ansiversion": (int, str),
            "size": (int, float),
            "capacity": (int, float),
            "width": (int,),
            "clock": (int, float),
            "depth": (int,),
            "FATs": (int,),
            "logicalsectorsize": (int,),
            "sectorsize": (int,),

            # Boolean fields
            "claimed": (bool,),
            "disabled": (bool,),
            "broadcast": (bool,),
            "link": (bool,),
            "multicast": (bool,),
            "slave": (bool,),
            "removable": (bool,),
            "audio": (bool,),
            "dvd": (bool,),

            # String fields (but can be numeric strings)
            "physid": (str,),
            "version": (str,),

            # Array fields
            "logicalname": (list, str),  # Can be string or list
            "children": (list,),
        }

    def get_type_name(self, value: Any) -> str:
        """Get a readable type name for a value."""
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, list):
            return "array"
        elif isinstance(value, dict):
            return "object"
        else:
            return type(value).__name__

    def check_type(self, value: Any, field_name: str, expected_types: tuple, path: str) -> bool:
        """
        Check if value matches expected types.

        Returns:
            True if type is correct, False otherwise
        """
        if value is None:
            # Null is acceptable for optional fields
            return True

        if not isinstance(value, expected_types):
            actual_type = self.get_type_name(value)
            expected_names = " or ".join(t.__name__ for t in expected_types)
            self.errors.append({
                "path": path,
                "field": field_name,
                "expected_type": expected_names,
                "actual_type": actual_type,
                "value": str(value)[:50]  # Truncate long values
            })
            return False

        return True

    def validate_string_as_boolean(self, value: Any, field_name: str, path: str) -> bool:
        """Check if a string value should be a boolean."""
        if isinstance(value, str):
            lower_val = value.lower().strip()
            if lower_val in ("true", "false", "yes", "no", "1", "0"):
                self.warnings.append({
                    "path": path,
                    "field": field_name,
                    "issue": "string_boolean",
                    "value": value,
                    "suggestion": "Convert to boolean type"
                })
                return False
        return True

    def validate_string_as_numeric(self, value: Any, field_name: str, path: str) -> bool:
        """Check if a string value should be numeric."""
        if isinstance(value, str) and field_name in self.expected_types:
            expected = self.expected_types[field_name]
            if (int in expected or float in expected):
                try:
                    # Try to parse as number
                    int(value) if int in expected else float(value)
                    self.warnings.append({
                        "path": path,
                        "field": field_name,
                        "issue": "string_numeric",
                        "value": value,
                        "suggestion": "Convert to numeric type"
                    })
                    return False
                except (ValueError, TypeError):
                    pass
        return True

    def validate_node(self, node: Any, path: str = "hardware.data") -> bool:
        """Recursively validate a node in the JSON structure."""
        is_valid = True

        if isinstance(node, dict):
            for key, value in node.items():
                field_path = f"{path}.{key}"

                # Check expected types for known fields
                if key in self.expected_types:
                    expected_types = self.expected_types[key]
                    if not self.check_type(value, key, expected_types, field_path):
                        is_valid = False

                # Check for boolean strings
                if key in ["broadcast", "link", "multicast", "slave", "claimed", "disabled"]:
                    if not self.validate_string_as_boolean(value, key, field_path):
                        is_valid = False

                # Check for numeric strings in known numeric fields
                if key in ["latency", "cores", "enabledcores", "threads", "level",
                          "size", "capacity", "width", "clock", "depth"]:
                    if not self.validate_string_as_numeric(value, key, field_path):
                        is_valid = False

                # Recursively validate nested structures
                if isinstance(value, dict):
                    if not self.validate_node(value, field_path):
                        is_valid = False
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, (dict, list)):
                            if not self.validate_node(item, f"{field_path}[{i}]"):
                                is_valid = False

        elif isinstance(node, list):
            for i, item in enumerate(node):
                if isinstance(item, (dict, list)):
                    if not self.validate_node(item, f"{path}[{i}]"):
                        is_valid = False

        return is_valid

    def validate_file(self, file_path: Path) -> bool:
        """
        Validate a single lshw JSON file.

        Returns:
            True if file is valid, False otherwise
        """
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            self.files_validated += 1

            # Clear previous errors/warnings for this file
            file_errors_start = len(self.errors)
            file_warnings_start = len(self.warnings)

            # Validate the data
            is_valid = self.validate_node(data)

            # Count errors/warnings for this file
            file_errors = len(self.errors) - file_errors_start
            file_warnings = len(self.warnings) - file_warnings_start

            if is_valid and file_errors == 0:
                self.files_passed += 1
                status = "✓ PASS"
            else:
                status = f"✗ FAIL ({file_errors} errors, {file_warnings} warnings)"

            print(f"{status}: {file_path.name}")

            return is_valid and file_errors == 0

        except json.JSONDecodeError as e:
            print(f"✗ FAIL: {file_path.name} - Invalid JSON: {e}", file=sys.stderr)
            self.errors.append({
                "file": str(file_path),
                "error": f"Invalid JSON: {e}"
            })
            return False

        except Exception as e:
            print(f"✗ FAIL: {file_path.name} - Error: {e}", file=sys.stderr)
            self.errors.append({
                "file": str(file_path),
                "error": str(e)
            })
            return False

    def print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 80)
        print("Validation Summary")
        print("=" * 80)
        print(f"Files validated: {self.files_validated}")
        print(f"Files passed: {self.files_passed}")
        print(f"Files failed: {self.files_validated - self.files_passed}")
        print(f"Total errors: {len(self.errors)}")
        print(f"Total warnings: {len(self.warnings)}")

        if self.errors:
            print("\n" + "=" * 80)
            print("Errors (showing first 20)")
            print("=" * 80)
            for i, error in enumerate(self.errors[:20]):
                print(f"\n{i+1}. Path: {error.get('path', 'N/A')}")
                print(f"   Field: {error.get('field', 'N/A')}")
                print(f"   Expected: {error.get('expected_type', 'N/A')}")
                print(f"   Actual: {error.get('actual_type', 'N/A')}")
                if 'value' in error:
                    print(f"   Value: {error['value']}")

        if self.warnings:
            print("\n" + "=" * 80)
            print("Warnings (showing first 20)")
            print("=" * 80)
            for i, warning in enumerate(self.warnings[:20]):
                print(f"\n{i+1}. Path: {warning.get('path', 'N/A')}")
                print(f"   Issue: {warning.get('issue', 'N/A')}")
                print(f"   Value: {warning.get('value', 'N/A')}")
                print(f"   Suggestion: {warning.get('suggestion', 'N/A')}")

    def save_report(self, output_file: Path):
        """Save detailed validation report to JSON file."""
        report = {
            "summary": {
                "files_validated": self.files_validated,
                "files_passed": self.files_passed,
                "files_failed": self.files_validated - self.files_passed,
                "total_errors": len(self.errors),
                "total_warnings": len(self.warnings),
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\nDetailed report saved to: {output_file}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate lshw JSON files for type consistency"
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="Path to lshw JSON files or directories containing them"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file for detailed validation report (JSON)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors"
    )

    args = parser.parse_args()

    # Collect all JSON files
    json_files = []
    for path in args.files:
        if path.is_file() and path.suffix == ".json":
            json_files.append(path)
        elif path.is_dir():
            json_files.extend(path.glob("*.json"))

    if not json_files:
        print("No JSON files found!", file=sys.stderr)
        return 1

    print(f"Validating {len(json_files)} files...\n")

    validator = LshwValidator()

    for file_path in json_files:
        validator.validate_file(file_path)

    validator.print_summary()

    if args.output:
        validator.save_report(args.output)

    # Determine exit code
    has_failures = validator.files_validated != validator.files_passed
    has_warnings = len(validator.warnings) > 0

    if has_failures:
        return 1
    elif args.strict and has_warnings:
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())

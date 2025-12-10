#!/usr/bin/env python3
"""
Analyze lshw JSON files to detect type inconsistencies across multiple samples.

This script scans all provided lshw JSON files and identifies:
1. Fields with inconsistent types across files
2. Numeric fields that are sometimes strings
3. Boolean fields with inconsistent representation
4. Missing or null fields
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, List, Set, Union


class LshwAnalyzer:
    def __init__(self):
        # Track field types across all files
        self.field_types: Dict[str, Set[str]] = defaultdict(set)
        # Track which files have which fields
        self.field_occurrences: Dict[str, int] = defaultdict(int)
        # Track total files processed
        self.total_files = 0
        # Track paths where inconsistencies are found
        self.inconsistent_fields: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

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
            # Check if string looks like a number
            try:
                int(value)
                return "string(numeric)"
            except (ValueError, TypeError):
                try:
                    float(value)
                    return "string(numeric)"
                except (ValueError, TypeError):
                    # Check if it looks like a boolean
                    if value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
                        return "string(boolean)"
                    return "string"
        elif isinstance(value, list):
            return "array"
        elif isinstance(value, dict):
            return "object"
        else:
            return type(value).__name__

    def analyze_node(self, node: Any, path: str = "hardware.data"):
        """Recursively analyze a node in the JSON structure."""
        if isinstance(node, dict):
            for key, value in node.items():
                field_path = f"{path}.{key}"

                # Track field occurrence
                self.field_occurrences[field_path] += 1

                # Track field type
                type_name = self.get_type_name(value)
                self.field_types[field_path].add(type_name)

                # Recursively analyze nested structures
                if isinstance(value, dict):
                    self.analyze_node(value, field_path)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            self.analyze_node(item, field_path)
                        elif isinstance(item, (str, int, float, bool)):
                            # Track array element types
                            elem_type = self.get_type_name(item)
                            self.field_types[f"{field_path}[]"].add(elem_type)

        elif isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    self.analyze_node(item, path)

    def analyze_file(self, file_path: Path):
        """Analyze a single lshw JSON file."""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            self.total_files += 1
            self.analyze_node(data)
            return True
        except json.JSONDecodeError as e:
            print(f"Error parsing {file_path}: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Error processing {file_path}: {e}", file=sys.stderr)
            return False

    def identify_issues(self) -> Dict[str, Any]:
        """Identify type inconsistencies and potential issues."""
        issues = {
            "type_inconsistencies": [],
            "numeric_as_string": [],
            "boolean_as_string": [],
            "missing_in_some_files": [],
            "always_null": [],
        }

        for field_path, types in self.field_types.items():
            occurrences = self.field_occurrences[field_path]

            # Type inconsistencies (same field with different types)
            if len(types) > 1:
                # Filter out null as it's common for optional fields
                non_null_types = [t for t in types if t != "null"]
                if len(non_null_types) > 1:
                    issues["type_inconsistencies"].append({
                        "field": field_path,
                        "types": sorted(list(types)),
                        "occurrences": occurrences,
                        "percentage": round(occurrences / self.total_files * 100, 2)
                    })

            # Numeric fields stored as strings
            if "string(numeric)" in types:
                issues["numeric_as_string"].append({
                    "field": field_path,
                    "types": sorted(list(types)),
                    "occurrences": occurrences,
                    "percentage": round(occurrences / self.total_files * 100, 2)
                })

            # Boolean fields stored as strings
            if "string(boolean)" in types:
                issues["boolean_as_string"].append({
                    "field": field_path,
                    "types": sorted(list(types)),
                    "occurrences": occurrences,
                    "percentage": round(occurrences / self.total_files * 100, 2)
                })

            # Fields missing in some files (appears in less than 90% of files)
            if occurrences < self.total_files * 0.9 and occurrences > 1:
                issues["missing_in_some_files"].append({
                    "field": field_path,
                    "occurrences": occurrences,
                    "percentage": round(occurrences / self.total_files * 100, 2)
                })

            # Fields that are always null
            if types == {"null"}:
                issues["always_null"].append({
                    "field": field_path,
                    "occurrences": occurrences
                })

        # Sort by severity
        for key in issues:
            if isinstance(issues[key], list):
                issues[key].sort(key=lambda x: x.get("occurrences", 0), reverse=True)

        return issues

    def generate_report(self, output_file: Path = None):
        """Generate a detailed report of the analysis."""
        issues = self.identify_issues()

        report = []
        report.append("=" * 80)
        report.append("LSHW JSON Type Analysis Report")
        report.append("=" * 80)
        report.append(f"\nTotal files analyzed: {self.total_files}")
        report.append(f"Total unique field paths: {len(self.field_types)}")
        report.append("")

        # Type Inconsistencies
        if issues["type_inconsistencies"]:
            report.append("\n" + "=" * 80)
            report.append("TYPE INCONSISTENCIES (HIGH PRIORITY)")
            report.append("=" * 80)
            report.append(f"Found {len(issues['type_inconsistencies'])} fields with inconsistent types:\n")
            for item in issues["type_inconsistencies"][:20]:  # Show top 20
                report.append(f"  Field: {item['field']}")
                report.append(f"    Types found: {', '.join(item['types'])}")
                report.append(f"    Occurrences: {item['occurrences']} ({item['percentage']}%)")
                report.append("")

        # Numeric as String
        if issues["numeric_as_string"]:
            report.append("\n" + "=" * 80)
            report.append("NUMERIC VALUES AS STRINGS (MEDIUM PRIORITY)")
            report.append("=" * 80)
            report.append(f"Found {len(issues['numeric_as_string'])} fields with numeric strings:\n")
            for item in issues["numeric_as_string"][:20]:  # Show top 20
                report.append(f"  Field: {item['field']}")
                report.append(f"    Types found: {', '.join(item['types'])}")
                report.append(f"    Occurrences: {item['occurrences']} ({item['percentage']}%)")
                report.append("")

        # Boolean as String
        if issues["boolean_as_string"]:
            report.append("\n" + "=" * 80)
            report.append("BOOLEAN VALUES AS STRINGS (MEDIUM PRIORITY)")
            report.append("=" * 80)
            report.append(f"Found {len(issues['boolean_as_string'])} fields with boolean strings:\n")
            for item in issues["boolean_as_string"][:20]:  # Show top 20
                report.append(f"  Field: {item['field']}")
                report.append(f"    Types found: {', '.join(item['types'])}")
                report.append(f"    Occurrences: {item['occurrences']} ({item['percentage']}%)")
                report.append("")

        # Missing in Some Files
        if issues["missing_in_some_files"]:
            report.append("\n" + "=" * 80)
            report.append("FIELDS MISSING IN SOME FILES (LOW PRIORITY)")
            report.append("=" * 80)
            report.append(f"Found {len(issues['missing_in_some_files'])} fields not present in all files:\n")
            for item in issues["missing_in_some_files"][:20]:  # Show top 20
                report.append(f"  Field: {item['field']}")
                report.append(f"    Present in: {item['occurrences']}/{self.total_files} files ({item['percentage']}%)")
                report.append("")

        report.append("\n" + "=" * 80)
        report.append("SUMMARY")
        report.append("=" * 80)
        report.append(f"Type inconsistencies: {len(issues['type_inconsistencies'])}")
        report.append(f"Numeric as string: {len(issues['numeric_as_string'])}")
        report.append(f"Boolean as string: {len(issues['boolean_as_string'])}")
        report.append(f"Missing in some files: {len(issues['missing_in_some_files'])}")
        report.append(f"Always null: {len(issues['always_null'])}")
        report.append("")

        report_text = "\n".join(report)

        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_text)
            print(f"Report written to: {output_file}")
        else:
            print(report_text)

        # Also save detailed JSON for use by normalization script
        details_file = output_file.parent / "analysis_details.json" if output_file else Path("analysis_details.json")
        with open(details_file, 'w') as f:
            json.dump({
                "total_files": self.total_files,
                "issues": issues,
                "field_types": {k: list(v) for k, v in self.field_types.items()}
            }, f, indent=2)
        print(f"Detailed analysis saved to: {details_file}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze lshw JSON files for type inconsistencies"
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
        help="Output file for the report (default: print to stdout)"
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

    print(f"Analyzing {len(json_files)} files...")

    analyzer = LshwAnalyzer()
    success_count = 0

    for file_path in json_files:
        if analyzer.analyze_file(file_path):
            success_count += 1

    print(f"Successfully analyzed {success_count}/{len(json_files)} files\n")

    # Generate report
    analyzer.generate_report(args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())

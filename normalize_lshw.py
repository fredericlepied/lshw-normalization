#!/usr/bin/env python3
"""
Normalize DCI lshw JSON files for consistent type handling in ElasticSearch.

This script processes DCI format files: {"hardware": {"node": "...", "data": {...}}}

It performs:
1. Validates files are in DCI lshw format (hardware.data has 'id' and 'class' fields)
2. Converts numeric strings to proper numbers
3. Converts boolean strings to proper booleans
4. Ensures consistent types for the same fields
5. Handles logicalname field (can be string or array, normalizes to always array)
6. Optionally copies original files to output directory (removing 'dci-extra.' prefix)
7. Skips invalid files (not real DCI lshw output) and reports them
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Union
import re
import shutil


class LshwNormalizer:
    def __init__(self, strict: bool = False):
        """
        Initialize normalizer.

        Args:
            strict: If True, fail on any normalization errors. If False, log warnings and continue.
        """
        self.strict = strict
        self.stats = {
            "files_processed": 0,
            "files_modified": 0,
            "files_skipped": 0,
            "numeric_conversions": 0,
            "boolean_conversions": 0,
            "array_normalizations": 0,
            "errors": [],
            "skipped_files": [],
        }

        # Define fields that should always be numeric (based on analysis)
        self.numeric_fields = {
            "latency", "cores", "enabledcores", "microcode", "threads",
            "level", "ansiversion", "size", "capacity", "width", "clock",
            "units", "depth", "FATs", "logicalsectorsize", "sectorsize",
        }

        # Define fields that should always be boolean (based on analysis)
        self.boolean_fields = {
            "claimed", "disabled", "boot", "broadcast", "link", "multicast",
            "slave", "removable", "audio", "dvd",
        }

        # Fields in capabilities that are typically boolean
        self.capability_boolean_patterns = [
            "pci", "pciexpress", "pm", "msi", "msix", "bus_master", "cap_list",
            "rom", "fb", "pnp", "upgrade", "shadowing", "cdboot", "bootselect",
            "edd", "usb", "netboot", "acpi", "biosbootspecification", "uefi",
            "escd", "virtualmachine", "smp", "vsyscall32", "gpt-1_00",
            "partitioned", "partitioned:gpt", "nofs", "fat", "initialized",
            "journaled", "extended_attributes", "large_files", "huge_files",
            "dir_nlink", "recover", "extents", "ethernet", "physical",
            "removable", "audio", "dvd",  # Media capabilities
        ]

    def is_valid_lshw(self, data: Any) -> bool:
        """
        Check if the JSON data is a valid DCI lshw output.

        Valid format: {"hardware": {"node": "...", "data": {...lshw output...}}}
        The lshw output inside must have "id" and "class" fields.

        Returns:
            True if valid DCI lshw output, False otherwise
        """
        if not isinstance(data, dict):
            return False

        # Check for DCI wrapped format
        if "hardware" not in data:
            return False

        hardware = data["hardware"]
        if not isinstance(hardware, dict):
            return False

        if "data" not in hardware:
            return False

        lshw_data = hardware["data"]
        if not isinstance(lshw_data, dict):
            return False

        # Check that the lshw data has required fields
        return "id" in lshw_data and "class" in lshw_data

    def normalize_boolean(self, value: Any) -> bool:
        """Convert various boolean representations to actual boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lower_val = value.lower().strip()
            if lower_val in ("true", "yes", "1", "on"):
                self.stats["boolean_conversions"] += 1
                return True
            elif lower_val in ("false", "no", "0", "off"):
                self.stats["boolean_conversions"] += 1
                return False
        # If it's a number, treat 0 as False, anything else as True
        if isinstance(value, (int, float)):
            return value != 0
        # Return as-is if we can't convert
        return value

    def normalize_numeric(self, value: Any, field_name: str = "") -> Union[int, float, str]:
        """Convert numeric strings to numbers."""
        if isinstance(value, (int, float)):
            return value

        if isinstance(value, str):
            # Try to convert to int first
            try:
                result = int(value)
                self.stats["numeric_conversions"] += 1
                return result
            except (ValueError, TypeError):
                pass

            # Try to convert to float
            try:
                result = float(value)
                self.stats["numeric_conversions"] += 1
                return result
            except (ValueError, TypeError):
                pass

        # Return as-is if we can't convert
        return value

    def normalize_logicalname(self, value: Any) -> List[str]:
        """Normalize logicalname to always be an array."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            self.stats["array_normalizations"] += 1
            return [value]
        return value

    def normalize_node(self, node: Any, path: str = "root") -> Any:
        """Recursively normalize a node in the JSON structure."""
        if isinstance(node, dict):
            normalized = {}
            for key, value in node.items():
                field_path = f"{path}.{key}"

                # Handle configuration fields
                if key == "configuration" and isinstance(value, dict):
                    normalized[key] = self.normalize_configuration(value, field_path)
                # Handle capabilities fields (often have boolean values)
                elif key == "capabilities" and isinstance(value, dict):
                    normalized[key] = self.normalize_capabilities(value, field_path)
                # Handle logicalname (can be string or array, normalize to array)
                elif key == "logicalname":
                    normalized[key] = self.normalize_logicalname(value)
                # Handle physid (sometimes numeric string, keep as string for consistency)
                elif key == "physid":
                    # Keep as string for consistency
                    normalized[key] = str(value) if value is not None else value
                # Handle version (can be numeric or string, keep as string for consistency)
                elif key == "version":
                    # Keep as string for consistency
                    normalized[key] = str(value) if value is not None else value
                # Handle known boolean fields
                elif key in self.boolean_fields:
                    normalized[key] = self.normalize_boolean(value)
                # Handle known numeric fields
                elif key in self.numeric_fields:
                    normalized[key] = self.normalize_numeric(value, key)
                # Recursively handle nested objects and arrays
                elif isinstance(value, dict):
                    normalized[key] = self.normalize_node(value, field_path)
                elif isinstance(value, list):
                    normalized[key] = [
                        self.normalize_node(item, f"{field_path}[{i}]")
                        if isinstance(item, (dict, list))
                        else item
                        for i, item in enumerate(value)
                    ]
                else:
                    normalized[key] = value

            return normalized

        elif isinstance(node, list):
            return [
                self.normalize_node(item, f"{path}[{i}]")
                if isinstance(item, (dict, list))
                else item
                for i, item in enumerate(node)
            ]

        return node

    def normalize_configuration(self, config: Dict[str, Any], path: str) -> Dict[str, Any]:
        """Normalize configuration object."""
        normalized = {}
        for key, value in config.items():
            # Boolean configuration fields
            if key in self.boolean_fields:
                normalized[key] = self.normalize_boolean(value)
            # Numeric configuration fields
            elif key in self.numeric_fields:
                normalized[key] = self.normalize_numeric(value, key)
            # Keep other fields as-is
            else:
                normalized[key] = value

        return normalized

    def normalize_capabilities(self, capabilities: Dict[str, Any], path: str) -> Dict[str, Any]:
        """Normalize capabilities object."""
        normalized = {}
        for key, value in capabilities.items():
            # Check if this capability should be boolean
            if key in self.capability_boolean_patterns or isinstance(value, bool):
                # If value is currently a string, try to normalize to boolean
                if isinstance(value, str):
                    lower_val = value.lower().strip()
                    # Check for explicit yes/no/true/false
                    if lower_val in ("true", "false", "yes", "no", "1", "0"):
                        normalized[key] = self.normalize_boolean(value)
                    else:
                        # For descriptive strings, check for negative indicators
                        # If it contains "no", "not", "none", "disabled", "unsupported" -> False
                        # Otherwise, presence of descriptive text means capability exists -> True
                        negative_words = [' no ', 'not ', 'none', 'disabled', 'unsupported', 'unavailable']
                        if any(neg in lower_val for neg in negative_words):
                            normalized[key] = False
                            self.stats["boolean_conversions"] += 1
                        else:
                            # Descriptive string means capability is present
                            normalized[key] = True
                            self.stats["boolean_conversions"] += 1
                else:
                    # Already a boolean or other type
                    normalized[key] = value
            else:
                normalized[key] = value

        return normalized

    def normalize_file(self, input_path: Path, output_path: Path = None) -> bool:
        """
        Normalize a single lshw JSON file.

        Args:
            input_path: Path to input file
            output_path: Path to output file (if None, overwrites input)

        Returns:
            True if file was modified, False otherwise, None if file was skipped
        """
        try:
            with open(input_path, 'r') as f:
                original_data = json.load(f)

            # Validate that this is a real lshw output
            if not self.is_valid_lshw(original_data):
                skip_msg = f"Skipping {input_path.name}: Not a valid lshw output (missing 'id' or 'class' fields)"
                self.stats["files_skipped"] += 1
                self.stats["skipped_files"].append(str(input_path))
                print(skip_msg, file=sys.stderr)
                return None

            # Normalize the DCI wrapped format
            # Extract and normalize the lshw data inside hardware.data
            normalized_lshw = self.normalize_node(original_data["hardware"]["data"])

            # Reconstruct the DCI wrapper
            normalized_data = {
                "hardware": {
                    "node": original_data["hardware"].get("node"),
                    "data": normalized_lshw,
                    "error": original_data["hardware"].get("error", "")
                }
            }

            # Check if anything changed
            modified = json.dumps(original_data, sort_keys=True) != json.dumps(normalized_data, sort_keys=True)

            # Write output
            output_file = output_path or input_path
            with open(output_file, 'w') as f:
                json.dump(normalized_data, f, indent=2, ensure_ascii=False)

            self.stats["files_processed"] += 1
            if modified:
                self.stats["files_modified"] += 1

            return modified

        except json.JSONDecodeError as e:
            error_msg = f"Error parsing {input_path}: {e}"
            self.stats["errors"].append(error_msg)
            if self.strict:
                raise
            else:
                print(error_msg, file=sys.stderr)
                return False

        except Exception as e:
            error_msg = f"Error processing {input_path}: {e}"
            self.stats["errors"].append(error_msg)
            if self.strict:
                raise
            else:
                print(error_msg, file=sys.stderr)
                return False

    def print_stats(self):
        """Print normalization statistics."""
        print("\n" + "=" * 80)
        print("Normalization Statistics")
        print("=" * 80)
        print(f"Files processed: {self.stats['files_processed']}")
        print(f"Files modified: {self.stats['files_modified']}")
        print(f"Files skipped (invalid lshw): {self.stats['files_skipped']}")
        print(f"Numeric conversions: {self.stats['numeric_conversions']}")
        print(f"Boolean conversions: {self.stats['boolean_conversions']}")
        print(f"Array normalizations: {self.stats['array_normalizations']}")

        if self.stats["skipped_files"]:
            print(f"\nSkipped files ({len(self.stats['skipped_files'])}):")
            for skipped in self.stats["skipped_files"][:10]:  # Show first 10 skipped
                print(f"  - {skipped}")
            if len(self.stats["skipped_files"]) > 10:
                print(f"  ... and {len(self.stats['skipped_files']) - 10} more")

        if self.stats["errors"]:
            print(f"\nErrors encountered: {len(self.stats['errors'])}")
            for error in self.stats["errors"][:10]:  # Show first 10 errors
                print(f"  - {error}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Normalize lshw JSON files for ElasticSearch ingestion"
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="Path to lshw JSON files or directories containing them"
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        help="Output directory for normalized files (default: overwrite input files)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any normalization errors (default: log warnings and continue)"
    )
    parser.add_argument(
        "--suffix",
        default="",
        help="Suffix to add to output filenames when using output directory (default: empty, no suffix)"
    )
    parser.add_argument(
        "--copy-originals",
        action="store_true",
        help="Copy original files to output directory first (removes 'dci-extra.' prefix from filenames)"
    )

    args = parser.parse_args()

    # Create output directory if specified
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all JSON files
    json_files = []
    for path in args.files:
        if path.is_file() and path.suffix == ".json":
            json_files.append(path)
        elif path.is_dir():
            json_files.extend(path.rglob("*.json"))

    if not json_files:
        print("No JSON files found!", file=sys.stderr)
        return 1

    # Copy original files to output directory if requested
    if args.copy_originals and args.output_dir:
        print(f"Copying {len(json_files)} original files to {args.output_dir}...")
        for input_file in json_files:
            # Remove 'dci-extra.' prefix from filename
            original_name = input_file.name
            if original_name.startswith("dci-extra."):
                output_name = original_name[10:]  # Remove 'dci-extra.' prefix (10 chars)
            else:
                output_name = original_name

            output_path = args.output_dir / output_name
            shutil.copy2(input_file, output_path)
            print(f"  Copied: {input_file.name} -> {output_name}")

    print(f"\nNormalizing {len(json_files)} files...")

    normalizer = LshwNormalizer(strict=args.strict)

    for input_file in json_files:
        if args.output_dir:
            # Keep original filename (don't remove prefix for normalized files)
            if args.suffix:
                base_name = input_file.stem
                output_file = args.output_dir / f"{base_name}{args.suffix}.json"
            else:
                output_file = args.output_dir / input_file.name
        else:
            output_file = None  # Overwrite input

        print(f"Processing: {input_file.name}...")
        normalizer.normalize_file(input_file, output_file)

    normalizer.print_stats()

    return 0 if not normalizer.stats["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())

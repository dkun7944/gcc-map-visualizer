#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GCC Map File Visualizer
Analyzes and visualizes memory usage from GCC linker map files
"""

import re
import sys
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import argparse


class MapFileParser:
    """Parser for GCC map files"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.sections = defaultdict(list)
        self.total_sizes = defaultdict(int)
        self.section_addresses = {}  # section_name -> (vma_addr, size, lma_addr)
        self.archive_members = []

    def parse(self):
        """Parse the map file"""
        with open(self.filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        current_section = None
        i = 0

        while i < len(lines):
            line = lines[i]

            # Detect MAIN section headers (no leading spaces)
            # e.g., ".text           0x00280180    0x383c8 load address 0x08001180"
            main_section_match = re.match(r'^(\.\w+[\w.]*)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)', line)
            if main_section_match and not line.startswith(' '):
                section_name = main_section_match.group(1)
                vma_address = int(main_section_match.group(2), 16)
                size = int(main_section_match.group(3), 16)
                current_section = section_name

                # Extract load address if present
                lma_address = vma_address
                load_match = re.search(r'load address (0x[0-9a-fA-F]+)', line)
                if load_match:
                    lma_address = int(load_match.group(1), 16)

                # Store the main section info
                if size > 0:
                    self.total_sizes[section_name] = size
                    self.section_addresses[section_name] = {
                        'vma': vma_address,
                        'lma': lma_address,
                        'size': size
                    }

                i += 1
                continue

            # Parse individual symbols/objects within sections
            if current_section:
                # Match patterns like: " .text          0x00280180  0x7c  file.o"
                # or                  " .text.function  0x00280180  0x7c  file.o"
                symbol_match = re.match(r'^\s+(\.\w+[\w.]*)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(.+)$', line)
                if symbol_match:
                    subsection = symbol_match.group(1)
                    address = int(symbol_match.group(2), 16)
                    size = int(symbol_match.group(3), 16)
                    source_file = symbol_match.group(4).strip()

                    if size > 0:
                        self.sections[current_section].append({
                            'subsection': subsection,
                            'address': address,
                            'size': size,
                            'file': source_file
                        })

            i += 1

    def get_summary(self) -> Dict[str, int]:
        """Get summary of section sizes"""
        return dict(self.total_sizes)

    def get_top_contributors(self, section: str, limit: int = 10) -> List[Dict]:
        """Get top contributors to a section"""
        if section not in self.sections:
            return []

        # Group by source file
        file_sizes = defaultdict(int)
        for item in self.sections[section]:
            file_sizes[item['file']] += item['size']

        # Sort by size
        sorted_files = sorted(file_sizes.items(), key=lambda x: x[1], reverse=True)
        return [{'file': f, 'size': s} for f, s in sorted_files[:limit]]

    def get_all_contributors(self, section: str) -> List[Dict]:
        """Get all contributors to a section with details"""
        if section not in self.sections:
            return []

        items = self.sections[section]
        sorted_items = sorted(items, key=lambda x: x['size'], reverse=True)
        return sorted_items


class Visualizer:
    """Terminal-based visualizer for memory usage"""

    # ANSI color codes
    COLORS = {
        'reset': '\033[0m',
        'bold': '\033[1m',
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
    }

    @staticmethod
    def format_size(size: int) -> str:
        """Format size in human-readable format"""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.2f}KB"
        else:
            return f"{size / (1024 * 1024):.2f}MB"

    @staticmethod
    def color(text: str, color: str, bold: bool = False) -> str:
        """Apply color to text"""
        prefix = Visualizer.COLORS.get(color, '')
        if bold:
            prefix = Visualizer.COLORS['bold'] + prefix
        return f"{prefix}{text}{Visualizer.COLORS['reset']}"

    @staticmethod
    def draw_bar(value: int, max_value: int, width: int = 50) -> str:
        """Draw a horizontal bar chart"""
        if max_value == 0:
            return ""

        filled = int((value / max_value) * width)
        bar = "#" * filled + "-" * (width - filled)
        return bar

    @staticmethod
    def print_section_summary(parser: MapFileParser):
        """Print summary of all sections"""
        summary = parser.get_summary()

        if not summary:
            print(Visualizer.color("No sections found in map file", 'red'))
            return

        total_size = sum(summary.values())
        sorted_sections = sorted(summary.items(), key=lambda x: x[1], reverse=True)

        print(Visualizer.color("\n=== Memory Usage Summary ===\n", 'magenta'))
        print(f"{'Section':<20} {'Size':<15} {'Percentage':<12} {'Visual'}")
        print("-" * 100)

        max_size = max(summary.values()) if summary else 1

        for section, size in sorted_sections:
            percentage = (size / total_size * 100) if total_size > 0 else 0
            bar = Visualizer.draw_bar(size, max_size, width=40)

            # Color code by size
            if percentage > 30:
                color = 'red'
            elif percentage > 10:
                color = 'yellow'
            else:
                color = 'green'

            size_str = Visualizer.format_size(size)
            colored_size = Visualizer.color(f"{size_str:<15}", color)

            print(f"{section:<20} {colored_size} {percentage:>6.2f}%      {bar}")

        print("-" * 100)
        print(f"{'TOTAL':<20} {Visualizer.format_size(total_size)}")
        print()

    @staticmethod
    def print_top_contributors(parser: MapFileParser, section: str, limit: int = 20):
        """Print top contributors to a section"""
        contributors = parser.get_top_contributors(section, limit)

        if not contributors:
            print(Visualizer.color(f"No data found for section: {section}", 'red'))
            return

        total = sum(c['size'] for c in contributors)

        print(Visualizer.color(f"\n=== Top {limit} Contributors to {section} ===\n", 'cyan', bold=True))
        print(f"{'Rank':<6} {'Size':<15} {'Percentage':<12} {'File'}")
        print("-" * 100)

        for i, contrib in enumerate(contributors, 1):
            size = contrib['size']
            percentage = (size / total * 100) if total > 0 else 0

            # Shorten long file paths
            file_name = contrib['file']
            if len(file_name) > 70:
                file_name = "..." + file_name[-67:]

            # Color by rank
            if i <= 3:
                color = 'red'
            elif i <= 10:
                color = 'yellow'
            else:
                color = 'white'

            rank_str = Visualizer.color(f"#{i:<5}", color)
            size_str = Visualizer.color(f"{Visualizer.format_size(size):<15}", color)
            percent_str = Visualizer.color(f"{percentage:>6.2f}%", color)

            print(f"{rank_str} {size_str} {percent_str}      {file_name}")

        print()

    @staticmethod
    def print_detailed_breakdown(parser: MapFileParser, section: str, limit: int = 50):
        """Print detailed breakdown of a section"""
        items = parser.get_all_contributors(section)

        if not items:
            print(Visualizer.color(f"No data found for section: {section}", 'red'))
            return

        items = items[:limit]

        print(Visualizer.color(f"\n=== Detailed Breakdown of {section} (Top {limit}) ===\n", 'cyan', bold=True))
        print(f"{'Address':<12} {'Size':<15} {'Subsection':<30} {'Source File'}")
        print("-" * 120)

        for item in items:
            addr_str = f"0x{item['address']:08x}"
            size_str = Visualizer.format_size(item['size'])
            subsection = item['subsection']
            if len(subsection) > 28:
                subsection = subsection[:25] + "..."

            file_name = item['file']
            if len(file_name) > 50:
                file_name = "..." + file_name[-47:]

            print(f"{addr_str:<12} {size_str:<15} {subsection:<30} {file_name}")

        print()

    @staticmethod
    def print_memory_map(parser: MapFileParser, use_vma: bool = True):
        """Print visual memory map showing physical layout

        Args:
            parser: MapFileParser instance
            use_vma: If True, show runtime addresses (VMA). If False, show load addresses (LMA)
        """
        if not parser.section_addresses:
            print(Visualizer.color("No memory layout information found", 'red'))
            return

        # Collect all sections
        all_sections = []

        for name, info in parser.section_addresses.items():
            # Choose VMA or LMA based on parameter
            addr = info['vma'] if use_vma else info['lma']

            section = {
                'name': name,
                'start': addr,
                'end': addr + info['size'],
                'size': info['size'],
                'vma': info['vma'],
                'lma': info['lma']
            }

            all_sections.append(section)

        # Sort all sections by address
        if not all_sections:
            return

        all_sections = sorted(all_sections, key=lambda x: x['start'])

        print(Visualizer.color(f"\n{'=' * 80}", 'magenta'))
        print(Visualizer.color(f"Memory Layout", 'magenta'))
        print(Visualizer.color(f"{'=' * 80}\n", 'magenta'))

        sections = all_sections

        # Calculate total region span
        region_start = sections[0]['start']
        region_end = sections[-1]['end']
        region_total = region_end - region_start

        print(f"Region: 0x{region_start:08x} - 0x{region_end:08x} (span: {Visualizer.format_size(region_total)})\n")

        # Print each section with gaps
        prev_end = region_start
        total_used = 0
        total_gaps = 0

        for i, section in enumerate(sections):
            # Check for gap
            if section['start'] > prev_end:
                gap_size = section['start'] - prev_end
                total_gaps += gap_size
                gap_str = Visualizer.format_size(gap_size)

                # Visual representation of gap
                gap_bar = "." * min(40, max(1, int(40 * gap_size / region_total)))

                print(Visualizer.color(f"  [GAP]", 'magenta'))
                print(f"    0x{prev_end:08x} - 0x{section['start']:08x}  ({Visualizer.color(gap_str, 'yellow')})")
                print(f"    {gap_bar}")
                print()

            # Print section
            total_used += section['size']
            size_str = Visualizer.format_size(section['size'])

            # Visual bar
            bar_width = min(60, max(1, int(60 * section['size'] / region_total)))
            bar = "#" * bar_width

            # Color by size
            if section['size'] > 100 * 1024:  # > 100KB
                color = 'red'
            elif section['size'] > 10 * 1024:  # > 10KB
                color = 'yellow'
            else:
                color = 'green'

            print(f"  [{section['name']}]")
            print(f"    0x{section['start']:08x} - 0x{section['end']:08x}  ({Visualizer.color(size_str, color)})")

            # Show alternate address if different
            if use_vma and section['vma'] != section['lma']:
                print(f"    LMA: 0x{section['lma']:08x} (loaded from Flash)")
            elif not use_vma and section['vma'] != section['lma']:
                print(f"    VMA: 0x{section['vma']:08x} (runs in RAM)")

            print(f"    {bar}")
            print()

            prev_end = section['end']

        # Summary
        print("-" * 80)
        print(f"Total Used: {Visualizer.color(Visualizer.format_size(total_used), 'green')}")
        print(f"Total Gaps: {Visualizer.color(Visualizer.format_size(total_gaps), 'yellow')}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Visualize GCC map file memory usage'
    )

    parser.add_argument('mapfile', help='Path to the GCC map file')

    args = parser.parse_args()

    # Parse map file
    print(f"Parsing {args.mapfile}...")
    map_parser = MapFileParser(args.mapfile)
    map_parser.parse()

    # Show everything
    Visualizer.print_section_summary(map_parser)
    Visualizer.print_memory_map(map_parser)


if __name__ == '__main__':
    main()

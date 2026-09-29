#!/usr/bin/env python2
# -*- coding: ascii -*-
"""Decode AMS FIFO messages. Compatible with Python 2.7 and Python 3.

Usage: python2 decode_fifo.py [irun.log] [-o OUTPUT_DIRECTORY]
Output defaults to the input log directory. Existing CSV files are preserved.
Columns are space-padded for a monospace font. Opens the output in gedit.
data_signed_22 is the 22-bit payload interpreted as a signed value. For
non-PPG types it is only a numeric interpretation of the payload, not a
type-specific measurement.
how to run: python decode_fifo.py irun.log
"""
from __future__ import print_function

import argparse
import errno
import os
import re
import sys
import subprocess


FIFO_RE = re.compile(
    r"AMS\s+MSG\s*:\s*FIFO\s+Data\s+(\d+)\s*,\s*"
    r"32\s*'\s*h\s*([0-9a-fxz_]+)(?![a-z0-9_])", re.I)
NAME_RE = re.compile(r'^fifo_data_(\d+)\.csv$')
TYPE_NAMES = ['PPG', 'PPGA', 'BGC DAC', 'Reserved',
              'Reserved', 'Reserved', 'Status/Event', 'Test']
HEADER = ['log_index', 'fifo_data', 'type',
          'type_name', 'slot', 'ch', 'channel',
          'gain', 'data [21:0]', 'data_signed_22']


def decode_word(word, log_index):
    data = word & 0x3FFFFF
    type_code = (word >> 29) & 7
    ch = (word >> 25) & 1
    signed = data - 0x400000 if data & 0x200000 else data
    return [log_index, "32'h%08X" % word, type_code,
            TYPE_NAMES[type_code], (word >> 26) & 7, ch, ch + 1,
            (word >> 22) & 7, "22'h%06X" % data, signed]


def create_output(directory):
    # Use max(existing suffix) + 1; do not reuse gaps or overwrite files.
    numbers = [int(m.group(1)) for m in
               (NAME_RE.match(name) for name in os.listdir(directory)) if m]
    number = max(numbers) + 1 if numbers else 0
    while True:
        path = os.path.join(directory, 'fifo_data_%d.csv' % number)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                number += 1
                continue
            raise
        if sys.version_info[0] == 2:
            output = os.fdopen(fd, 'w')
        else:
            output = os.fdopen(fd, 'w', newline='')
        return path, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log_file', nargs='?', default='irun.log')
    parser.add_argument('-o', '--output-dir', help='Default: input log directory')
    args = parser.parse_args()
    log_path = os.path.abspath(args.log_file)
    directory = os.path.abspath(args.output_dir) if args.output_dir else os.path.dirname(log_path)
    count = 0
    skipped = 0
    try:
        with open(log_path, 'rb') as source:
            if not os.path.isdir(directory):
                os.makedirs(directory)
            rows = []
            widths = [len(name) for name in HEADER]
            for line_number, raw_line in enumerate(source, 1):
                # Latin-1 accepts any log bytes; only ASCII fields are used.
                line = raw_line.decode('latin-1')
                for match in FIFO_RE.finditer(line):
                    token = match.group(2).replace('_', '')
                    if 'x' in token.lower() or 'z' in token.lower() or len(token) > 8:
                        skipped += 1
                        print('Warning: invalid or unknown FIFO value on line %d: %s'
                              % (line_number, token), file=sys.stderr)
                        continue
                    row = [str(value) for value in
                           decode_word(int(token, 16), int(match.group(1)))]
                    rows.append(row)
                    widths = [max(width, len(value))
                              for width, value in zip(widths, row)]
                    count += 1
            path, output = create_output(directory)
            with output:
                # Fields contain no commas, quotes or newlines. Keep CSV
                # delimiters while padding every column to its maximum width.
                output.write(', '.join(value.ljust(width) for value, width
                                       in zip(HEADER, widths)) + '\n')
                for row in rows:
                    output.write(', '.join(value.ljust(width) for value, width
                                           in zip(row, widths)) + '\n')
        print('Output: %s' % path)
        print('Decoded rows: %d; skipped values: %d' % (count, skipped))
        if count == 0:
            print('Warning: no valid FIFO data found.', file=sys.stderr)
    except (IOError, OSError) as exc:
        print('Error: %s' % exc, file=sys.stderr)
        return 1
    try:
        subprocess.Popen(['gedit', path])
    except OSError as exc:
        print('Warning: CSV saved, but could not launch gedit: %s' % exc,
              file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())

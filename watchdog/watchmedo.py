#!/usr/bin/env python
# -*- coding: utf-8 -*-
# watchmedo.py: Shell file monitoring utilities.
#
# Copyright (C) 2010 Gora Khargosh <gora.khargosh@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


import os
import os.path
import sys
import yaml
import time
import uuid
import logging

from argh import arg, alias, ArghParser
from watchdog import Observer, VERSION_STRING
from watchdog.utils import read_text_file, load_class, absolute_path, get_parent_dir_path
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


logging.basicConfig(level=logging.DEBUG)


CURRENT_DIR_PATH = absolute_path(os.getcwd())
DEFAULT_TRICKS_FILE_NAME = 'tricks.yaml'
DEFAULT_TRICKS_FILE_PATH = os.path.join(CURRENT_DIR_PATH, DEFAULT_TRICKS_FILE_NAME)

CONFIG_KEY_TRICKS = 'tricks'
CONFIG_KEY_PYTHON_PATH = 'python-path'

def path_split(path_spec, separator=os.path.sep):
    """Splits a path specification separated by an OS-dependent separator
    (: on Unix and ; on Windows, for examples)."""
    return list(path_spec.split(separator))


def add_to_sys_path(paths, index=0):
    """Adds specified paths at specified index into the sys.path list."""
    for path in paths[::-1]:
        sys.path.insert(index, path)


def load_config(tricks_file):
    """Loads the YAML configuration from the specified file."""
    content = read_text_file(tricks_file)
    config = yaml.load(content)
    return config


def check_trick_has_key(trick_name, trick, key):
    if key not in trick:
        logging.warn("Key `%s' not found for trick `%s'. Typo or missing?", key, trick_name)


def parse_patterns(patterns_spec, ignore_patterns_spec):
    """Parses pattern argument specs and returns a two-tuple of (patterns, ignore_patterns)."""
    separator = ';'
    patterns = patterns_spec.split(separator)
    ignore_patterns = ignore_patterns_spec.split(separator)
    if ignore_patterns == ['']:
        ignore_patterns = []
    return (patterns, ignore_patterns)


def observe_with(observer, identifier, event_handler, paths, recursive):
    """Single observer given an identifier, event handler, and directories
    to watch."""
    observer.schedule(identifier, event_handler, paths, recursive)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.unschedule(identifier)
        observer.stop()
    observer.join()


def schedule_tricks(observer, tricks, watch_path):
    """Schedules tricks with the specified observer and for the given watch
    path."""
    for trick in tricks:
        for trick_name, trick_value in trick.items():
            check_trick_has_key(trick_name, trick_value, 'kwargs')
            check_trick_has_key(trick_name, trick_value, 'args')

            trick_kwargs = trick_value.get('kwargs', {})
            trick_args = trick_value.get('args', ())

            TrickClass = load_class(trick_name)
            trick_event_handler = TrickClass(*trick_args, **trick_kwargs)

            unique_identifier = uuid.uuid1().hex
            observer.schedule(unique_identifier, trick_event_handler, [watch_path], recursive=True)


@alias('tricks')
@arg('files', nargs='*', help='perform tricks from given file')
@arg('--python-path', default='.', help='string of paths separated by %s to add to the python path' % os.path.sep)
def tricks_from(args):
    add_to_sys_path(path_split(args.python_path))
    observers = []
    for tricks_file in args.files:
        observer = Observer()

        if not os.path.exists(tricks_file):
            raise IOError("cannot find tricks file: %s" % tricks_file)

        config = load_config(tricks_file)

        if CONFIG_KEY_TRICKS not in config:
            raise KeyError("No `%s' key specified in %s." % (CONFIG_KEY_TRICKS, input_file))
        tricks = config[CONFIG_KEY_TRICKS]

        if CONFIG_KEY_PYTHON_PATH in config:
            add_to_sys_path(config[CONFIG_KEY_PYTHON_PATH])

        dir_path = get_parent_dir_path(tricks_file)
        schedule_tricks(observer, tricks, dir_path)
        observer.start()
        observers.append(observer)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for o in observers:
            o.unschedule()
            o.stop()
    for o in observers:
        o.join()




@alias('generate-yaml')
@arg('trick_paths', nargs='*', help='Dotted paths for all the tricks you want to generate')
@arg('--python-path', default='.', help='string of paths separated by %s to add to the python path' % os.path.sep)
@arg('--append-to-file', default=None, help='appends the generated tricks YAML to a file; if not specified, prints to standard output')
@arg('-a', '--append-only', dest='append_only', default=False, help='if --append-to-file is not specified, produces output for appending instead of a complete tricks yaml file.')
def tricks_generate_yaml(args):
    python_paths = path_split(args.python_path)
    add_to_sys_path(python_paths)
    output = StringIO()

    for trick_path in args.trick_paths:
        TrickClass = load_class(trick_path)
        output.write(TrickClass.generate_yaml())

    content = output.getvalue()
    output.close()

    header = yaml.dump({CONFIG_KEY_PYTHON_PATH: python_paths}) + "%s:\n" % CONFIG_KEY_TRICKS
    if args.append_to_file is None:
        # Output to standard output.
        if not args.append_only:
            content = header + content
        sys.stdout.write(content)
    else:
        if not os.path.exists(args.append_to_file):
            content = header + content
        output = open(args.append_to_file, 'ab')
        output.write(content)
        output.close()


@arg('directories', nargs='*', default='.', help='directories to watch.')
@arg('-p', '--pattern', '--patterns', dest='patterns', default='*', help='matches event paths with these patterns (separated by ;).')
@arg('-i', '--ignore-pattern', '--ignore-patterns', dest='ignore_patterns', default='', help='ignores event paths with these patterns (separated by ;).')
@arg('-D', '--ignore-directories', dest='ignore_directories', default=False, help='ignores events for directories')
@arg('-R', '--recursive', dest='recursive', default=False, help='monitors the directories recursively')
@arg('--debug-force-polling', default=False, help='[debug flag] forces using the polling observer implementation.')
@arg('--debug-force-kqueue', default=False, help='[debug flag] forces using the kqueue observer implementation.')
@arg('--debug-force-win32', default=False, help='[debug flag] forces using the win32 observer implementation.')
@arg('--debug-force-win32ioc', default=False, help='[debug flag] forces using the win32 IOC observer implementation.')
@arg('--debug-force-fsevents', default=False, help='[debug flag] forces using the fsevents observer implementation.')
@arg('--debug-force-inotify', default=False, help='[debug flag] forces using the inotify observer implementation.')
def log(args):
    from watchdog.tricks import LoggerTrick
    patterns, ignore_patterns = parse_patterns(args.patterns, args.ignore_patterns)
    event_handler = LoggerTrick(patterns=patterns,
                                ignore_patterns=ignore_patterns,
                                ignore_directories=args.ignore_directories)
    if args.debug_force_polling:
        from watchdog.observers.polling_observer import PollingObserver as Observer
    elif args.debug_force_kqueue:
        from watchdog.observers.kqueue_observer import KqueueObserver as Observer
    elif args.debug_force_win32:
        from watchdog.observers.win32_observer import Win32Observer as Observer
    elif args.debug_force_win32ioc:
        from watchdog.observers.win32ioc_observer import Win32IOCObserver as Observer
    elif args.debug_force_inotify:
        from watchdog.observers.inotify_observer import InotifyObserver as Observer
    elif args.debug_force_fsevents:
        from watchdog.observers.fsevents_observer import FSEventsObserver as Observer
    else:
        from watchdog import Observer
    observer = Observer()
    observe_with(observer, 'logger', event_handler, args.directories, args.recursive)


#@alias('shell-command')
@arg('directories', nargs='*', default='.', help='directories to watch')
@arg('-c', '--command', dest='command', default=None, help='''shell command executed in response
to matching events. These interpolation variables are available to your
command string:

${watch_src_path}    - event source path;
${watch_dest_path}   - event destination path (for moved events);
${watch_event_type}  - event type;
${watch_object}      - `file` or `directory`.

Note:
Please ensure you do not use double quotes (") to quote your command
string. That will force your shell to interpolate before the command is
processed by this subcommand.

Example option usage:
--command='echo "${watch_src_path}"'
''')
@arg('-p', '--pattern', '--patterns', dest='patterns', default='*', help='matches event paths with these patterns (separated by ;).')
@arg('-i', '--ignore-pattern', '--ignore-patterns', dest='ignore_patterns', default='', help='ignores event paths with these patterns (separated by ;).')
@arg('-D', '--ignore-directories', dest='ignore_directories', default=False, help='ignores events for directories')
@arg('-R', '--recursive', dest='recursive', default=False, help='monitors the directories recursively')
def shell_command(args):
    from watchdog.tricks import ShellCommandTrick

    if not args.command:
        args.command = None

    patterns, ignore_patterns = parse_patterns(args.patterns, args.ignore_patterns)
    #watch_directories = path_split(args.watch_directories)
    event_handler = ShellCommandTrick(shell_command=args.command,
                                      patterns=patterns,
                                      ignore_patterns=ignore_patterns,
                                      ignore_directories=args.ignore_directories)
    observe_with(Observer(), 'shell-command', event_handler, args.directories, args.recursive)


epilog="""Copyright (C) 2010 Gora Khargosh <gora.khargosh@gmail.com>.

Licensed under the terms of the MIT license. Please see LICENSE in the
source code for more information."""

parser = ArghParser(epilog=epilog)
parser.add_commands([tricks_from,
                     tricks_generate_yaml,
                     log,
                     shell_command])
parser.add_argument('--version', action='version', version='%(prog)s ' + VERSION_STRING)


def main():
    """Entry-point function."""
    parser.dispatch()


if __name__ == '__main__':
    main()


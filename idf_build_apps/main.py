# SPDX-FileCopyrightText: 2022 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

import re

from . import LOGGER
from .app import App
from .finder import _find_apps
from .manifest.manifest import Manifest
from .utils import get_parallel_start_stop, BuildError

try:
    from typing import TextIO
except ImportError:
    pass


def find_apps(
    paths,
    target,
    build_system='cmake',
    recursive=False,
    exclude_list=None,
    work_dir=None,
    build_dir='build',
    config_rules_str=None,
    build_log_path=None,
    size_json_path=None,
    check_warnings=False,
    preserve=True,
    manifest_files=None,
):  # type: (list[str] | str, str, str, bool, list[str] | None, str | None, str, list[str] | None, str | None, str | None, bool, bool, list[str] | str | None) -> list[App]
    if manifest_files:
        if isinstance(manifest_files, str):
            manifest_files = [manifest_files]

        rules = set()
        for _manifest_file in manifest_files:
            LOGGER.info('Loading manifest file: %s', _manifest_file)
            rules.update(Manifest.from_file(_manifest_file).rules)
        manifest = Manifest(rules)
        App.MANIFEST = manifest

    apps = []
    if isinstance(paths, str):
        paths = [paths]

    for path in paths:
        apps.extend(
            _find_apps(
                path,
                target,
                build_system=build_system,
                recursive=recursive,
                exclude_list=exclude_list or [],
                work_dir=work_dir,
                build_dir=build_dir or 'build',
                config_rules_str=config_rules_str,
                build_log_path=build_log_path,
                size_json_path=size_json_path,
                check_warnings=check_warnings,
                preserve=preserve,
            )
        )
    apps.sort()

    LOGGER.info('Found %d apps:', len(apps))
    return apps


def build_apps(
    apps,
    build_verbose=False,
    parallel_count=1,
    parallel_index=1,
    dry_run=False,
    keep_going=False,
    collect_size_info=None,
    ignore_warning_strs=None,
    ignore_warning_file=None,
):  # type: (list[App], bool, int, int, bool, bool, TextIO | None, list[str] | None, TextIO | None) -> int
    ignore_warnings_regexes = []
    if ignore_warning_strs:
        for s in ignore_warning_strs:
            ignore_warnings_regexes.append(re.compile(re.escape(s)))
    if ignore_warning_file:
        for s in ignore_warning_file:
            ignore_warnings_regexes.append(re.compile(s.strip()))
    App.IGNORE_WARNS_REGEXES = ignore_warnings_regexes

    start, stop = get_parallel_start_stop(len(apps), parallel_count, parallel_index)
    LOGGER.info(
        'Total %s apps. running build for app %s-%s', len(apps), start + 1, stop
    )

    failed_apps = []
    exit_code = 0
    for i, app in enumerate(apps):
        if i < start or i >= stop:
            continue

        # attrs
        app.dry_run = dry_run
        app.index = i
        app.verbose = build_verbose

        LOGGER.debug('=> Building app %s: %s', i, repr(app))
        try:
            app.build()
            if collect_size_info:
                app.collect_size_json(collect_size_info)
        except BuildError as e:
            LOGGER.error(str(e))
            if keep_going:
                failed_apps.append(app)
                exit_code = 1
            else:
                return 1

    return exit_code
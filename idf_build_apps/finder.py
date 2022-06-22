# SPDX-FileCopyrightText: 2022 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

import logging
import os.path
import re
from pathlib import Path

from idf_build_apps.app import App, CMakeApp
from idf_build_apps.utils import ConfigRule, dict_from_sdkconfig, config_rules_from_str


def _get_apps_from_path(
    path,
    target,
    build_system='cmake',
    work_dir=None,
    build_dir='build',
    build_log_path=None,
    config_rules=None,
    preserve=True,
):  # type: (str, str, str, str, str, str, list[ConfigRule], bool) -> list[App]
    """
    Get the list of buildable apps under the given path.

    :param path: app directory (can be / usually will be a relative path)
    :param target: the value of IDF_TARGET passed to the script. Used to filter out configurations with a different
        CONFIG_IDF_TARGET value.
    :param build_system: name of the build system, index into BUILD_SYSTEMS dictionary
    :param work_dir: directory where the app should be copied before building. May contain env variables and
        placeholders.
    :param build_dir: directory where the build will be done, relative to the work_dir. May contain placeholders.
    :param build_log_path: path of the build log. May contain placeholders. May be None, in which case the log should
        go into stdout/stderr.
    :param config_rules: mapping of sdkconfig file name patterns to configuration names
    :param preserve: determine if the built binary will be uploaded as artifacts.
    :return: list of Apps
    """

    if build_system == 'cmake':
        app_cls = CMakeApp
    else:
        raise ValueError('Only Support CMake for now')

    if not app_cls.is_app(path):
        logging.debug('Skipping, %s is not an app', path)
        return []

    supported_targets = app_cls.enable_build_targets(path)
    if target not in supported_targets:
        logging.debug(
            'Skipping, %s only supports targets: %s', path, ', '.join(supported_targets)
        )
        return []

    apps = []
    default_config_name = ''
    for rule in config_rules:
        if not rule.file_name:
            default_config_name = rule.config_name
            continue

        sdkconfig_paths = Path(path).glob(rule.file_name)
        sdkconfig_paths = sorted([str(p) for p in sdkconfig_paths])
        for sdkconfig_path in sdkconfig_paths:
            # Check if the sdkconfig file specifies IDF_TARGET, and if it is matches the --target argument.
            sdkconfig_dict = dict_from_sdkconfig(sdkconfig_path)
            target_from_config = sdkconfig_dict.get('CONFIG_IDF_TARGET')
            if target_from_config is not None and target_from_config != target:
                logging.debug(
                    'Skipping sdkconfig %s which requires target %s',
                    sdkconfig_path,
                    target_from_config,
                )
                continue

            # Figure out the config name
            config_name = rule.config_name or ''
            if '*' in rule.file_name:
                # convert glob pattern into a regex
                regex_str = r'.*' + rule.file_name.replace('.', r'\.').replace(
                    '*', r'(.*)'
                )
                groups = re.match(regex_str, sdkconfig_path)
                assert groups
                config_name = groups.group(1)

            sdkconfig_path = os.path.relpath(sdkconfig_path, path)
            logging.debug(
                'Found %s app: %s, sdkconfig %s, config name "%s"',
                build_system,
                path,
                sdkconfig_path,
                config_name,
            )
            apps.append(
                app_cls(
                    path,
                    target,
                    sdkconfig_path=sdkconfig_path,
                    config_name=config_name,
                    work_dir=work_dir,
                    build_dir=build_dir,
                    build_log_path=build_log_path,
                    preserve=preserve,
                )
            )

    # no wildcard config rules
    if not apps:
        logging.debug(
            'Found %s app: %s, default sdkconfig, config name "%s"',
            build_system,
            path,
            default_config_name,
        )
        apps = [
            app_cls(
                path,
                target,
                sdkconfig_path=None,
                config_name=default_config_name,
                work_dir=work_dir,
                build_dir=build_dir,
                build_log_path=build_log_path,
                preserve=preserve,
            )
        ]

    return apps


def find_apps(
    path,
    target,
    build_system='cmake',
    recursive=False,
    exclude_list=None,
    work_dir=None,
    build_dir='build',
    build_log_path=None,
    config_rules_str=None,
    preserve=True,
):
    # type: (str, str, str, bool, list[str], str | None, str, str | None, list[str] | None, bool) -> list[App]
    """
    Find app directories in path (possibly recursively), which contain apps for the given build system, compatible
    with the given target.

    :param path: path where to look for apps
    :param target: desired value of IDF_TARGET; apps incompatible with the given target are skipped.
    :param build_system: the build system in use
    :param recursive: whether to recursively descend into nested directories if no app is found
    :param exclude_list: list of paths to be excluded from the recursive search
    :param work_dir: directory where the app should be copied before building. May contain env variables and
        placeholders.
    :param build_dir: directory where the build will be done, relative to the work_dir. May contain placeholders.
    :param build_log_path: path of the build log. May contain placeholders. May be None, in which case the log should
        go into stdout/stderr.
    :param config_rules_str: mapping of sdkconfig file name patterns to configuration names
    :param preserve: determine if the built binary will be uploaded as artifacts.
    :return: list of apps found
    """
    exclude_list = exclude_list or []
    logging.debug(
        'Looking for %s apps in %s%s',
        build_system,
        path,
        ' recursively' if recursive else '',
    )

    config_rules = config_rules_from_str(config_rules_str)

    if not recursive:
        if exclude_list:
            logging.warning('--exclude option is ignored when used without --recursive')

        return _get_apps_from_path(
            path,
            target,
            build_system,
            work_dir,
            build_dir,
            build_log_path,
            config_rules,
            preserve,
        )

    # The remaining part is for recursive == True
    apps = []
    for root, dirs, _ in os.walk(path, topdown=True):
        logging.debug('Entering %s', root)
        if root in exclude_list:
            logging.debug('Skipping %s (excluded)', root)
            del dirs[:]
            continue

        _found_apps = _get_apps_from_path(
            root,
            target,
            build_system,
            work_dir,
            build_dir,
            build_log_path,
            config_rules,
            preserve,
        )
        if _found_apps:  # root has at least one app
            logging.debug('Stop iteration sub dirs of %s since it has apps', root)
            del dirs[:]
            apps.extend(_found_apps)
            continue

    return apps
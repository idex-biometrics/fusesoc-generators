#!/usr/bin/env python3

import os
import shutil
import logging
import subprocess
from pathlib import Path
from fusesoc.capi2.generator import Generator

logger = logging.getLogger(__name__)


class CmakeGenerator(Generator):
    REPLACEMENTS = {
        'CMAKE_REPLACE_BUILD_DIR' : 'attr:build_dir',
        'CMAKE_REPLACE_FILES_ROOT': 'attr:files_root',
    }

    @property
    def build_dir(self):
        return os.path.join(self.files_root, self.config.get('build', 'build'))

    def replace(self, string):
        """Allow the user to specify run time arguments to expand. Useful, for example,
        for specifying an installation directory relative to the core file.
        """
        for var,repl in self.REPLACEMENTS.items():
            if var in string:
                type,value = repl.split(':')
                if type == 'attr':
                    new = getattr(self, value)
                elif type == 'env':
                    new = os.environ.get(value)
                else:
                    raise ValueError(f"unknown replacement type: {type}")
                string = string.replace(var,new)
        return string

    def run(self):
        cmake_args = self.config.get("cmake_args", [])
        make_targets = self.config.get("make_targets", [""])
        files = self.config.get("files", [])

        # Create the build directory
        Path(self.build_dir).mkdir(parents=True, exist_ok=True)

        # Replace any variables in the args
        cmake_args = [
            self.replace(arg) for arg in cmake_args
        ]

        # Call CMake
        try:
            subprocess.check_output(['cmake', '..'] + cmake_args, cwd=self.build_dir)
        except subprocess.CalledProcessError as e:
            logger.error(e.output)
            exit(e.returncode)

        # Get the number of CPUs to use for Make.
        num_cpus = str(os.environ.get('NSLOTS', os.cpu_count() // 4 * 3))

        # Call Make
        for target in make_targets:
            if target == "":
                cmd = ['make', '-j', num_cpus]
            else:
                cmd = ['make', target, '-j', num_cpus]
            
            try:
                subprocess.check_output(cmd, cwd=self.build_dir)
            except subprocess.CalledProcessError as e:
                logger.error(e.output)
                exit(e.returncode)

        # Define the filesets for the generated core file
        self.filesets = {}
        self.filesets['generated_files'] = {'files': []}

        # Define the default target for the generated core file
        self.targets = {}
        self.targets['default'] = {'filesets': ['generated_files']}

        # All output files must be
        for f in files:
            if not isinstance(f, dict):
                raise TypeError("each entry must be a dict conforming to CAPI2 filesets")
            if len(f.keys()) != 1:
                raise ValueError("each filelist entry must be a dict with a single key")

            # The filename must be specified relative to the core file.
            filename = list(f.keys())[0]
            path = Path(self.files_root) / filename

            # Error out early if any files don't exist
            if not path.exists():
                raise RuntimeError(f"{str(path)} does not exist")

            # Append the file and its attributes to the filelist.
            self.filesets['generated_files']['files'].append(
                { path.name: f[filename] }
            )

            # Copy the file to the generator /tmp directory.
            shutil.copy(path, os.getcwd())


g = CmakeGenerator()
g.run()
g.write()

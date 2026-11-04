"""Build a pinned uCsim core and our separate startup target on Linux/WSL."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
COMMIT = '59a14ff99efe7e92474faf4c4ddf57b5e4ff0631'
URL = 'https://github.com/danieldrotos/ucsim.git'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--directory', type=Path, default=ROOT / '.build' / 'ucsim')
    ap.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args()
    if sys.platform == 'win32':
        ap.error('Run this build in WSL or Linux; the launcher also works from Windows with --wsl.')
    directory = args.directory.resolve()
    directory.parent.mkdir(parents=True, exist_ok=True)
    if not directory.exists():
        subprocess.run(['git', '-c', 'core.autocrlf=false', 'clone', '--depth', '1',
                        '--branch', 'ucsim-0.9.12', URL, str(directory)], check=True)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=directory, text=True).strip()
    if head != COMMIT:
        ap.error(f'Expected uCsim {COMMIT}; found {head}. Use a separate build directory.')
    for patch in sorted((ROOT / 'patches').glob('*.patch')):
        applied = subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)],
                                 cwd=directory, capture_output=True).returncode == 0
        if not applied:
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=directory, check=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=directory, check=True)
    with (directory / 'xt660-build.log').open('w') as log:
        def run(*cmd):
            print(' '.join(map(str, cmd)), flush=True)
            subprocess.run(list(map(str, cmd)), cwd=directory, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        if not (directory / 'Makefile').exists():
            run('sh', 'configure', '--enable-m68hc12-sim')
        run('make', 'preps')
        run('make', f'-j{args.jobs}', 'libs')
        target = directory / 'src/sims/m68hc12.src'
        # Generated disassembly metadata is checked in upstream. Recompile its users.
        (target / 'hcwrap.cc').touch()
        (target / 'm68hc12.cc').touch()
        run('make', f'-j{args.jobs}', '-C', target)
        shutil.copyfile(ROOT / 'native/xt660_boot.cc', target / 'xt660_boot.cc')
        includes = [target] + [directory / 'src/core' / name for name in
                    ('utils.src', 'sim.src', 'cmd.src', 'gui.src', 'motorola.src')]
        run('g++', '-std=c++11', '-O2', '-Wall', *[f'-I{p}' for p in includes],
            '-c', target / 'xt660_boot.cc', '-o', target / 'xt660_boot.o')
        objects = ['xt660_boot', 'm68hc12', 'imov', 'ialu', 'ibranch', 'iother',
                   'glob', 'glob12', 'dis', 'hcwrap']
        run('g++', *[target / f'{o}.o' for o in objects], f'-L{directory}',
            '-lmotorola', '-lsim', '-lucsimutil', '-lgui', '-lcmd', '-lsim',
            '-lpanel', '-lcurses', '-ltinfo', '-lm', '-lrt', '-o', target / 'xt660-emu')
    print(f'Built: {target / "xt660-emu"}')


if __name__ == '__main__':
    main()

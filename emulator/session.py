"""Persistent, bounded debugger transport. This never opens a physical COM port."""
import queue
import re
import subprocess
import threading
import time
from runner import RUNS


class Session:
    def __init__(self, executable, wsl=False, log='session.log'):
        RUNS.mkdir(parents=True, exist_ok=True)
        self.log = (RUNS / log).open('w', encoding='utf-8', newline='\n')
        self.process = subprocess.Popen((['wsl', '-e'] if wsl else []) +
            [str(executable), '-q', '-R', '0', '-c', '-'], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.lines = queue.Queue()
        self.sequence = 0
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def command(self, commands, timeout=60):
        self.sequence += 1
        marker = 0x61000000 + self.sequence
        self.process.stdin.write(commands.rstrip() + f'\nexpression /X 0x{marker:08x}\n')
        self.process.stdin.flush()
        result = []
        deadline = time.monotonic() + timeout
        while True:
            try:
                line = self.lines.get(timeout=max(.01, deadline-time.monotonic()))
            except queue.Empty:
                self.close()
                raise RuntimeError('Simulator command timed out; process stopped') from None
            if line is None:
                raise RuntimeError('Simulator exited before completing the command')
            self.log.write(line)
            result.append(line)
            if re.fullmatch(rf'0x{marker:08x}\s*', line):
                break
        self.log.flush()
        text = ''.join(result)
        if any(x in text for x in ('unmodelled', 'Parser error', 'FAULT=1', 'invalid instruction', 'Unknown command')):
            raise RuntimeError('Simulator stopped on an unsupported operation; inspect ' + self.log.name)
        return text

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write('quit\n')
                self.process.stdin.flush()
                self.process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait()
        self.thread.join(timeout=2)
        self.log.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

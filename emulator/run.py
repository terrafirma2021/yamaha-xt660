"""Boot a registered BIN, or open its instruction-level debugger."""
import argparse
import json
import subprocess
from runner import RUNS, boot, prepare, target_path
from sensors import sensor_demo
from runtime import runtime
from crank import crank


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ucsim', required=True, help='Path to the locally built xt660-emu executable')
    ap.add_argument('--wsl', action='store_true', help='Run a Linux executable through WSL from Windows')
    ap.add_argument('--image', default='xt660-2004-2006-companion')
    mode=ap.add_mutually_exclusive_group()
    mode.add_argument('--console', action='store_true', help='Interactive debugger at the reset vector')
    mode.add_argument('--sensors', action='store_true', help='Run an isolated firmware ADC routine and report RAM results')
    mode.add_argument('--runtime', action='store_true', help='Run from reset to repeated main-loop entries with disconnected storage')
    mode.add_argument('--crank', action='store_true', help='Drive synthetic crank edges, record outputs, then test pulse loss')
    ap.add_argument('--pitch', type=int, default=1600, help='Crank pitch in timer ticks, not RPM (400..4000)')
    ap.add_argument('--patterns', type=int, default=12, help='Synthetic crank patterns (4..24)')
    ap.add_argument('--uniform', action='store_true', help='Use a uniform crank stream without a long gap')
    ap.add_argument('--loops', type=int, default=100, help='Main-loop entries for --runtime (default: 100)')
    ap.add_argument('--adc', type=int, nargs=8, metavar='RAW', help='Eight raw 10-bit ADC inputs for sensors/runtime/crank (default: 512 each)')
    ap.add_argument('--steps', type=int, help='Instruction limit (runtime default: 2000000; boot: 200000)')
    args = ap.parse_args()
    if args.steps is None: args.steps=10000000 if args.crank else 2000000 if args.runtime else 200000
    if not 1<=args.loops<=10000: ap.error('--loops must be between 1 and 10000')
    if args.steps < 1 or args.steps > 10000000:
        ap.error('--steps must be between 1 and 10000000')
    if args.adc is not None and not (args.sensors or args.runtime or args.crank):
        ap.error('--adc requires --sensors, --runtime or --crank')
    if args.uniform and not args.crank: ap.error('--uniform requires --crank')
    try:
        if args.crank:
            report,_=crank(args.ucsim,args.image,args.wsl,args.pitch,args.patterns,args.uniform,args.adc,args.steps)
            print(json.dumps(report,indent=2))
            return 0 if report['completed'] else 1
        if args.runtime:
            report=runtime(args.ucsim,args.image,args.wsl,args.loops,args.steps,args.adc)
            print(json.dumps(report,indent=2))
            return 0 if report['completed'] else 1
        if args.sensors:
            print(json.dumps(sensor_demo(args.ucsim,args.image,args.adc or [512]*8,args.wsl),indent=2))
            return 0
        if args.console:
            record, _ = prepare(args.image, args.wsl)
            image = RUNS / f'{args.image}.hex'
            cmd = (['wsl', '-e'] if args.wsl else []) + [args.ucsim, '-q', '-R', '0',
                    '-e', f'break 0x{record["application_entry"]:04x}', '-c', '-',
                    target_path(image, args.wsl)]
            print('Partial MCU model. Use step, run, info registers, adc0=512, or quit.', flush=True)
            return subprocess.call(cmd)
        report, log, _ = boot(args.ucsim, args.image, args.wsl, args.steps)
        print(json.dumps(report, indent=2))
        print(f'Trace: {log}')
        return 0 if report['application_entry_reached'] else 1
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        ap.exit(1, f'{error}\n')


if __name__ == '__main__':
    raise SystemExit(main())

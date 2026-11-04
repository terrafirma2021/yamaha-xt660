"""A meter peer: consumes only checked SCI replies, never reads ECU RAM."""
from collections import deque

FAULT_NAMES = {11:'Cylinder identification',12:'Crank signal',13:'Intake pressure circuit',
               14:'Intake pressure',15:'Throttle circuit',16:'Throttle position',19:'Start interlock',
               20:'Pressure mismatch',21:'Coolant sensor circuit',22:'Intake temperature circuit',
               23:'Atmospheric pressure',24:'Oxygen sensor',30:'Lean-angle shutdown',31:'Oxygen feedback',
               32:'Oxygen feedback',33:'Ignition coil',34:'Ignition coil 2',37:'Idle control',
               41:'Lean-angle circuit',42:'Speed / neutral',43:'Supply monitor',44:'EEPROM',
               46:'System voltage',50:'Internal memory'}

DIAGNOSTICS = {1:('Throttle position','sensor'),3:('Intake pressure','sensor'),
               5:('Intake temperature','sensor'),6:('Coolant temperature','sensor'),
               7:('Vehicle-speed pulses','sensor'),8:('Lean-angle input','sensor'),
               9:('Fuel-system voltage','sensor'),20:('Sidestand switch','sensor'),
               21:('Neutral switch','sensor'),30:('Ignition coil','actuator'),
               36:('Injector','actuator'),37:('Variant actuator 37','actuator'),
               48:('Air-induction solenoid','actuator'),50:('Fuel-injection relay','actuator'),
               51:('Fan relay','actuator'),52:('Headlight relay','actuator'),
               57:('Variant actuator 57','actuator'),60:('EEPROM fault detail','information'),
               61:('Stored fault history','history'),62:('Stored fault count','erase'),
               63:('Active oxygen-sensor faults','history'),
               70:('Program control number','information')}


class MeterPeer:
    def __init__(self, clock=None, wait=None):
        self.frame = None
        self.frames = 0
        self.seen = []
        self.log = deque(maxlen=48)
        self.mode = 'normal'
        self.diag_id = None
        self.diag_value = None
        self.entry_polls = 0
        self.clock, self.wait = clock, wait
        self.last_request = None
        self.hold_started = None
        self.holds = []
        self.speed_sum = self.speed_samples = 0
        self.speed_kmh = None

    def send(self, exchange, byte):
        # Chosen peer cadence: 16 ms under the nominal 16 MHz profile. It
        # gives the manual's >=2 s hold for the ECU's 128-request counter.
        # The actual motorcycle meter's exact transmit cadence is unmeasured.
        if self.clock:
            if self.last_request is not None:
                delay = self.last_request + 256000 - self.clock()
                if delay > 0:self.wait(delay)
            self.last_request = self.clock()
        frame = exchange(byte)
        self.accept(frame,byte)
        return frame

    def accept(self, frame, request=0x01):
        if len(frame) != 5 or any(type(v) is not int or not 0 <= v <= 255 for v in frame):
            raise ValueError('Meter requires five bytes')
        if sum(frame[:4]) & 255 != frame[4]:
            raise ValueError('Meter rejected checksum')
        if self.mode == 'normal' and frame[2] & 64:
            raise ValueError('Expected normal meter mode, received diagnostic/authentication status')
        self.frame = list(frame)
        self.frames += 1
        # Same eight-reply display profile as Yamaha-DataLogger. This does not
        # establish pulses/km or the original dashboard's polling cadence.
        if self.mode == 'normal':
            self.speed_sum += frame[1]
            self.speed_samples += 1
            if self.speed_samples == 8:
                self.speed_kmh = self.speed_sum
                self.speed_sum = self.speed_samples = 0
        else:
            self.speed_sum = self.speed_samples = 0
            self.speed_kmh = None
        fault = (frame[2] & 63) if self.mode == 'normal' else 0
        if fault and fault not in self.seen:
            self.seen.append(fault)
        self.log.append(f'TX {request:02X}  →  RX '+' '.join(f'{v:02X}' for v in frame))
        if self.mode == 'diagnostic':
            if frame[2] & 64:
                if self.diag_id != frame[3]:
                    self.diag_value = None
                self.diag_id = frame[3]
            elif self.diag_id is not None:
                self.diag_value = frame[3]

    def connect(self, exchange, diagnostic=False):
        exchange(0xfe)
        if diagnostic:
            self.mode = 'hold-menu'
            self.hold_started = None
        else:
            self.poll(exchange)

    def poll(self, exchange):
        if self.mode in ('hold-menu','hold-confirm'):
            self.entry_polls += 1
            if self.entry_polls > 1600:
                raise RuntimeError('ECU did not enter dashboard diagnostics within the request budget')
        if self.mode == 'normal':
            self.accept(exchange(0x01))
        elif self.mode == 'hold-menu':
            frame = self.send(exchange,0xcd)
            if self.clock and self.hold_started is None:self.hold_started=self.clock()
            held = not self.clock or self.clock()-self.hold_started >= 128000000
            if frame[2]&64 and frame[3]==0xd0 and held:
                if self.clock:self.holds.append(dict(stage='menu',cycles=self.clock()-self.hold_started))
                self.send(exchange,0xca)
                self.mode = 'hold-confirm'
                self.hold_started = self.clock() if self.clock else None
        elif self.mode == 'hold-confirm':
            frame = self.send(exchange,0xcd)
            if frame[2]&64 and frame[3]==1:
                self.mode = 'diagnostic'
                self.diag_id = 1
                if self.clock:self.holds.append(dict(stage='confirm',cycles=self.clock()-self.hold_started))
                self.send(exchange,0xca)
        else:
            self.send(exchange,0xca)

    def navigate(self, exchange, direction):
        if self.mode != 'diagnostic' or direction not in (-1,1):
            raise ValueError('Wait for diagnostic mode before changing items')
        # A released button followed by increment/decrement advances selection.
        self.send(exchange,0xca)
        self.send(exchange,0xcb if direction==1 else 0xcc)
        self.diag_id = self.diag_value = None
        # Firmware alternates one number frame with seven value frames.
        for _ in range(9):
            self.poll(exchange)

    def state(self):
        fallback = 'Waiting for diagnostic number' if self.diag_id is None else f'Diagnostic {self.diag_id}'
        name,kind = DIAGNOSTICS.get(self.diag_id,(fallback,'information'))
        details = dict(diagnostic_name=name,diagnostic_kind=kind,
                       speed_kmh=self.speed_kmh,
                       speed_mph=self.speed_kmh/1.609344 if self.speed_kmh is not None else None,
                       entry_seconds=round((self.clock()-self.hold_started)/16000000,1)
                       if self.clock and self.hold_started is not None and self.mode!='diagnostic' else 0)
        if self.frame is None:
            return dict(connected=False, frames=0, seen=[], log=[],mode=self.mode,
                        diagnostic_id=self.diag_id,diagnostic_value=self.diag_value,**details)
        speed, pulses, status, coolant, checksum = self.frame
        fault = (status & 63) if self.mode == 'normal' else 0
        return dict(connected=True, frames=self.frames, frame=self.frame,
                    engine_code=speed, speed_pulses=pulses, coolant_code=coolant,
                    warning=bool(status & 128), fault=fault,
                    fault_name=FAULT_NAMES.get(fault,'Unclassified ECU fault') if fault else '',
                    seen=list(self.seen), log=list(self.log),mode=self.mode,
                    diagnostic_id=self.diag_id,diagnostic_value=self.diag_value,**details)

import shlex
import sys

from . import benchmarks
from .engine import AirportSystem, CommandError
from .matrix import DEFAULT_CUTOFF, self_check
from .timeutil import is_clock_token, is_date_token
from .tracing import tracer

HELP_TEXT = """Commands (timestamps: "YYYY-MM-DD HH:MM", quotes optional):
  LOAD <csv_path>
  STATS
  LIST_RUNWAY <runway> [<from> <to>]
  FIND <flight_id>
  ADD <flight_id> <airline> <origin> <destination> <runway> <start> <end> <priority>
  CANCEL <flight_id>
  RESCHEDULE <flight_id> <new_start> [<runway>]
  CHECK_CONFLICT <runway> <start> <end>
  RUNWAY_CLOSURE <runway> <start> <end>
  EMERGENCY_INSERT [<flight_id> <airline> <origin> <destination> <runway> <start> <end> <priority>] [ACCEPT|REJECT]
  MASS_CANCEL <start> <end>
  SORT_PRIORITY [<limit>]
  SORT_ID [EXACT|NUMERIC] [<limit>]
  STABILITY_DEMO
  ANALYZE [ALL|DISRUPTION|ROUTES] [<strassen_cutoff>]
  PERFECT_HASH [<rule_id> ...]
  BENCHMARK [ALL|HASH|BST|SORT|MATRIX] [QUICK|FULL]
  VALIDATE
  TRACE [ON|OFF]
  HELP
  EXIT"""

MENU = (
    ("1", "Load flights CSV", "LOAD", ("CSV path",)),
    ("2", "Show statistics", "STATS", ()),
    ("3", "List a runway", "LIST_RUNWAY", ("runway",)),
    ("4", "Find a flight", "FIND", ("flight_id",)),
    ("5", "Add a flight", "ADD", ("flight_id", "airline", "origin", "destination", "runway", "start (YYYY-MM-DD HH:MM)", "end", "priority")),
    ("6", "Cancel a flight", "CANCEL", ("flight_id",)),
    ("7", "Reschedule a flight", "RESCHEDULE", ("flight_id", "new start (YYYY-MM-DD HH:MM)")),
    ("8", "Check a slot for conflicts", "CHECK_CONFLICT", ("runway", "start", "end")),
    ("9", "Runway closure (scenario A)", "RUNWAY_CLOSURE", ("runway [R1]", "start [2026-11-27 09:00]", "end [2026-11-27 11:00]")),
    ("10", "Emergency insert (scenario B)", "EMERGENCY_INSERT", ()),
    ("11", "Mass cancel (scenario C)", "MASS_CANCEL", ("start [2026-11-27 14:00]", "end [2026-11-27 15:00]")),
    ("12", "Sort by priority (counting sort)", "SORT_PRIORITY", ()),
    ("13", "Sort by flight id (radix sort)", "SORT_ID", ()),
    ("14", "Disruption + route analysis", "ANALYZE", ()),
    ("15", "Perfect hashing demo", "PERFECT_HASH", ()),
    ("16", "Run benchmarks (quick)", "BENCHMARK", ()),
    ("17", "Toggle trace", "TRACE", ()),
    ("18", "Check registry/BST consistency", "VALIDATE", ()),
    ("19", "Type a raw command", None, ()),
    ("0", "Exit", "EXIT", ()),
)

MENU_DEFAULTS = {
    "RUNWAY_CLOSURE": ("R1", "2026-11-27 09:00", "2026-11-27 11:00"),
    "MASS_CANCEL": ("2026-11-27 14:00", "2026-11-27 15:00"),
}


class ExitRequested(Exception):
    pass


def tokenize(line):
    try:
        raw = shlex.split(line)
    except ValueError as exc:
        raise CommandError(f"cannot parse command: {exc}")
    tokens = []
    i = 0
    while i < len(raw):
        if i + 1 < len(raw) and is_date_token(raw[i]) and is_clock_token(raw[i + 1]):
            tokens.append(raw[i] + " " + raw[i + 1])
            i += 2
        else:
            tokens.append(raw[i])
            i += 1
    return tokens


class CommandRunner:
    def __init__(self, system=None, out=print, interactive=False):
        self.system = system if system is not None else AirportSystem()
        self.out = out
        self.interactive = interactive
        tracer.sink = out
        self.handlers = {
            "LOAD": self.cmd_load,
            "STATS": self.cmd_stats,
            "LIST_RUNWAY": self.cmd_list_runway,
            "FIND": self.cmd_find,
            "ADD": self.cmd_add,
            "CANCEL": self.cmd_cancel,
            "RESCHEDULE": self.cmd_reschedule,
            "CHECK_CONFLICT": self.cmd_check_conflict,
            "RUNWAY_CLOSURE": self.cmd_runway_closure,
            "EMERGENCY_INSERT": self.cmd_emergency_insert,
            "MASS_CANCEL": self.cmd_mass_cancel,
            "SORT_PRIORITY": self.cmd_sort_priority,
            "SORT_ID": self.cmd_sort_id,
            "STABILITY_DEMO": self.cmd_stability,
            "ANALYZE": self.cmd_analyze,
            "PERFECT_HASH": self.cmd_perfect_hash,
            "BENCHMARK": self.cmd_benchmark,
            "VALIDATE": self.cmd_validate,
            "TRACE": self.cmd_trace,
            "HELP": self.cmd_help,
            "EXIT": self.cmd_exit,
            "QUIT": self.cmd_exit,
        }

    def execute(self, line):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return True
        try:
            tokens = tokenize(stripped)
            if not tokens:
                return True
            name = tokens[0].upper()
            handler = self.handlers.get(name)
            if handler is None:
                raise CommandError(f"unknown command '{tokens[0]}' (type HELP)")
            handler(tokens[1:])
            return True
        except ExitRequested:
            raise
        except CommandError as exc:
            self.out(f"ERROR: {exc}")
            return False

    def emit(self, report):
        self.out(report.text())
        self.out("")

    @staticmethod
    def _expect(args, low, high, usage):
        if not low <= len(args) <= high:
            raise CommandError(f"usage: {usage}")

    @staticmethod
    def _int(text, label):
        try:
            value = int(text)
        except ValueError:
            raise CommandError(f"{label} must be an integer, got '{text}'")
        if value < 0:
            raise CommandError(f"{label} must be nonnegative")
        return value

    def cmd_load(self, args):
        self._expect(args, 1, 1, "LOAD <csv_path>")
        self.emit(self.system.load(args[0]))

    def cmd_stats(self, args):
        self._expect(args, 0, 0, "STATS")
        self.emit(self.system.stats())

    def cmd_list_runway(self, args):
        if len(args) not in (1, 3):
            raise CommandError("usage: LIST_RUNWAY <runway> [<from> <to>]")
        self.emit(self.system.list_runway(*args))

    def cmd_find(self, args):
        self._expect(args, 1, 1, "FIND <flight_id>")
        self.emit(self.system.find_report(args[0]))

    def cmd_add(self, args):
        self._expect(args, 8, 8, "ADD <flight_id> <airline> <origin> <destination> <runway> <start> <end> <priority>")
        self.emit(self.system.add(*args))

    def cmd_cancel(self, args):
        self._expect(args, 1, 1, "CANCEL <flight_id>")
        self.emit(self.system.cancel(args[0]))

    def cmd_reschedule(self, args):
        self._expect(args, 2, 3, "RESCHEDULE <flight_id> <new_start> [<runway>]")
        self.emit(self.system.reschedule(*args))

    def cmd_check_conflict(self, args):
        self._expect(args, 3, 3, "CHECK_CONFLICT <runway> <start> <end>")
        self.emit(self.system.check_conflict(*args))

    def cmd_runway_closure(self, args):
        self._expect(args, 3, 3, "RUNWAY_CLOSURE <runway> <start> <end>")
        self.emit(self.system.runway_closure(*args))

    def cmd_emergency_insert(self, args):
        accept = None
        if args and args[-1].upper() in ("ACCEPT", "REJECT"):
            accept = args[-1].upper() == "ACCEPT"
            args = args[:-1]
        if len(args) not in (0, 8):
            raise CommandError("usage: EMERGENCY_INSERT [<flight_id> <airline> <origin> <destination> <runway> <start> <end> <priority>] [ACCEPT|REJECT]")
        confirm = self._confirm if self.interactive else None
        self.emit(self.system.emergency_insert(*args, accept=accept, confirm=confirm))

    def _confirm(self, question):
        try:
            answer = input(f"{question} [y/N]: ")
        except EOFError:
            return False
        return answer.strip().lower() in ("y", "yes")

    def cmd_mass_cancel(self, args):
        self._expect(args, 2, 2, "MASS_CANCEL <start> <end>")
        self.emit(self.system.mass_cancel(*args))

    def cmd_sort_priority(self, args):
        self._expect(args, 0, 1, "SORT_PRIORITY [<limit>]")
        limit = self._int(args[0], "limit") if args else 20
        self.emit(self.system.sort_priority(limit))

    def cmd_sort_id(self, args):
        self._expect(args, 0, 2, "SORT_ID [EXACT|NUMERIC] [<limit>]")
        mode = "EXACT"
        limit = 20
        for a in args:
            if a.upper() in ("EXACT", "NUMERIC"):
                mode = a.upper()
            else:
                limit = self._int(a, "limit")
        self.emit(self.system.sort_id(mode, limit))

    def cmd_stability(self, args):
        self._expect(args, 0, 0, "STABILITY_DEMO")
        self.emit(self.system.stability_demo())

    def cmd_analyze(self, args):
        self._expect(args, 0, 2, "ANALYZE [ALL|DISRUPTION|ROUTES] [<strassen_cutoff>]")
        part = "ALL"
        cutoff = DEFAULT_CUTOFF
        for a in args:
            if a.upper() in ("ALL", "DISRUPTION", "ROUTES"):
                part = a.upper()
            else:
                cutoff = self._int(a, "cutoff")
                if cutoff < 1:
                    raise CommandError("cutoff must be at least 1")
        if part in ("ALL", "DISRUPTION"):
            self.emit(self.system.analyze_disruption())
        if part in ("ALL", "ROUTES"):
            self.emit(self.system.analyze_routes(cutoff))
            checks = self_check()
            self.out("Strassen self-check vs classical on random odd/even sizes: " +
                     ", ".join(f"{n}:{'ok' if ok else 'FAIL'}" for n, ok in checks))
            self.out("")

    def cmd_perfect_hash(self, args):
        queries = [self._int(a, "rule id") for a in args]
        self.emit(self.system.perfect_hash_report(queries))

    def cmd_benchmark(self, args):
        self._expect(args, 0, 2, "BENCHMARK [ALL|HASH|BST|SORT|MATRIX] [QUICK|FULL]")
        which = "ALL"
        quick = True
        for a in args:
            if a.upper() in ("QUICK", "FULL"):
                quick = a.upper() == "QUICK"
            else:
                which = a.upper()
        self.out("=== BENCHMARK ===")
        try:
            with tracer.suspend():
                benchmarks.run(which, quick=quick, log=self.out)
        except ValueError as exc:
            raise CommandError(str(exc))
        self.out("")

    def cmd_validate(self, args):
        self._expect(args, 0, 0, "VALIDATE")
        problems = self.system.validate()
        self.out("=== VALIDATE ===")
        if problems:
            for p in problems:
                self.out("  " + p)
        else:
            self.out("registry and runway BSTs are consistent; no overlaps")
        self.out("")

    def cmd_trace(self, args):
        self._expect(args, 0, 1, "TRACE [ON|OFF]")
        if args:
            value = args[0].upper()
            if value not in ("ON", "OFF"):
                raise CommandError("usage: TRACE [ON|OFF]")
            tracer.enabled = value == "ON"
        else:
            tracer.enabled = not tracer.enabled
        self.out(f"trace is {'ON' if tracer.enabled else 'OFF'}")

    def cmd_help(self, args):
        self.out(HELP_TEXT)

    def cmd_exit(self, args):
        raise ExitRequested()


def run_batch(path, runner=None, echo=True):
    runner = runner if runner is not None else CommandRunner()
    try:
        handle = open(path, encoding="utf-8")
    except OSError as exc:
        runner.out(f"ERROR: cannot open command file '{path}': {exc.strerror}")
        return 1
    failures = 0
    with handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if echo:
                runner.out(f">>> {stripped}")
            try:
                if not runner.execute(stripped):
                    failures += 1
                    runner.out(f"(command on line {number} failed)")
            except ExitRequested:
                break
    return 1 if failures else 0


def _prompt(label):
    return input(f"  {label}: ").strip()


def _quote(value):
    return '"' + value.replace('"', "") + '"' if " " in value else value


def run_menu(runner=None):
    runner = runner if runner is not None else CommandRunner(interactive=True)
    runner.interactive = True
    runner.out("AIRPORT CHAOS - flight scheduling and crisis recovery engine")
    while True:
        runner.out("")
        for key, label, _, _ in MENU:
            runner.out(f"  {key:>2}. {label}")
        try:
            choice = input("Select option: ").strip()
        except EOFError:
            return 0
        entry = None
        for item in MENU:
            if item[0] == choice:
                entry = item
        if entry is None:
            runner.out("ERROR: invalid option")
            continue
        _, _, command, prompts = entry
        try:
            if command is None:
                line = input("command> ")
            else:
                values = []
                defaults = MENU_DEFAULTS.get(command, ())
                for i in range(len(prompts)):
                    value = _prompt(prompts[i])
                    if not value and i < len(defaults):
                        value = defaults[i]
                    values.append(_quote(value))
                line = " ".join([command] + values)
            runner.execute(line)
        except ExitRequested:
            runner.out("bye")
            return 0
        except EOFError:
            return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return run_menu()
    if argv[0] in ("-h", "--help"):
        print("usage: python main.py                     interactive menu")
        print("       python main.py --batch <file>      run commands from a file")
        print("       python main.py --cmd \"<command>\"   run one command (repeatable)")
        print()
        print(HELP_TEXT)
        return 0
    runner = CommandRunner()
    status = 0
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag in ("--batch", "-b") and i + 1 < len(argv):
            status |= run_batch(argv[i + 1], runner)
            i += 2
        elif flag in ("--cmd", "-c") and i + 1 < len(argv):
            try:
                if not runner.execute(argv[i + 1]):
                    status = 1
            except ExitRequested:
                break
            i += 2
        else:
            print(f"ERROR: unknown argument '{flag}' (use --help)")
            return 2
    return status

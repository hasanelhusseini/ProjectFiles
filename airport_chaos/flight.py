from .timeutil import fmt_ts

SCHEDULED = "SCHEDULED"
DELAYED = "DELAYED"
CANCELLED = "CANCELLED"
VALID_STATUSES = (SCHEDULED, DELAYED, CANCELLED)


class Flight:
    __slots__ = (
        "flight_id", "airline", "origin", "destination", "runway",
        "start", "end", "priority", "status",
        "original_start", "original_end", "original_runway",
    )

    def __init__(self, flight_id, airline, origin, destination, runway, start, end, priority, status=SCHEDULED):
        self.flight_id = flight_id
        self.airline = airline
        self.origin = origin
        self.destination = destination
        self.runway = runway
        self.start = start
        self.end = end
        self.priority = priority
        self.status = status
        self.original_start = start
        self.original_end = end
        self.original_runway = runway

    @property
    def duration(self):
        return self.end - self.start

    @property
    def is_active(self):
        return self.status != CANCELLED

    @property
    def delay_minutes(self):
        return self.start - self.original_start

    def describe(self):
        return (
            f"{self.flight_id:<10} {self.airline:<4} {self.origin:>4}->{self.destination:<4} "
            f"{self.runway:<4} {fmt_ts(self.start)} - {fmt_ts(self.end)[11:]}  "
            f"P{self.priority}  {self.status}"
        )

    def describe_full(self):
        lines = [
            f"flight_id      : {self.flight_id}",
            f"airline        : {self.airline}",
            f"route          : {self.origin} -> {self.destination}",
            f"runway         : {self.runway}",
            f"current slot   : {fmt_ts(self.start)} - {fmt_ts(self.end)}",
            f"original slot  : {fmt_ts(self.original_start)} - {fmt_ts(self.original_end)} on {self.original_runway}",
            f"duration       : {self.duration} min",
            f"priority       : {self.priority}",
            f"status         : {self.status}",
        ]
        if self.status == DELAYED:
            lines.append(f"delay          : {self.delay_minutes} min")
        return lines

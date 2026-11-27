from .timeutil import fmt_ts
from .tracing import tracer


def path_text(path):
    if not path:
        return "(empty)"
    if len(path) <= 12:
        return " -> ".join(n.label() for n in path)
    head = " -> ".join(n.label() for n in path[:5])
    tail = " -> ".join(n.label() for n in path[-5:])
    return f"{head} -> ... ({len(path) - 10} more) ... -> {tail}"


class BSTNode:
    __slots__ = ("key", "end", "flight", "left", "right", "parent")

    def __init__(self, key, end, flight):
        self.key = key
        self.end = end
        self.flight = flight
        self.left = None
        self.right = None
        self.parent = None

    @property
    def start(self):
        return self.key[0]

    @property
    def flight_id(self):
        return self.key[1]

    def label(self):
        return f"{self.key[1]}@{fmt_ts(self.key[0])[11:]}"


class RunwayBST:
    def __init__(self, name):
        self.name = name
        self.root = None
        self.size = 0

    def __len__(self):
        return self.size

    def insert(self, flight):
        key = (flight.start, flight.flight_id)
        node = BSTNode(key, flight.end, flight)
        parent = None
        current = self.root
        path = []
        track = tracer.active
        while current is not None:
            parent = current
            if track:
                path.append(current)
            if key < current.key:
                current = current.left
            elif key > current.key:
                current = current.right
            else:
                raise KeyError(f"key {key} already in runway {self.name}")
        node.parent = parent
        if parent is None:
            self.root = node
        elif key < parent.key:
            parent.left = node
        else:
            parent.right = node
        self.size += 1
        tracer.log(f"BST {self.name} insert {node.label()} path: {path_text(path) if path else '(root)'}")
        return node

    def search(self, start, flight_id):
        key = (start, flight_id)
        current = self.root
        path = []
        track = tracer.active
        while current is not None:
            if track:
                path.append(current)
            if key == current.key:
                break
            current = current.left if key < current.key else current.right
        tracer.log(f"BST {self.name} search ({fmt_ts(start)}, {flight_id}) path: {path_text(path)}")
        return current

    @staticmethod
    def minimum(node):
        while node is not None and node.left is not None:
            node = node.left
        return node

    @staticmethod
    def maximum(node):
        while node is not None and node.right is not None:
            node = node.right
        return node

    def first(self):
        return self.minimum(self.root)

    def last(self):
        return self.maximum(self.root)

    @classmethod
    def successor(cls, node):
        if node.right is not None:
            return cls.minimum(node.right)
        parent = node.parent
        while parent is not None and node is parent.right:
            node = parent
            parent = parent.parent
        return parent

    @classmethod
    def predecessor(cls, node):
        if node.left is not None:
            return cls.maximum(node.left)
        parent = node.parent
        while parent is not None and node is parent.left:
            node = parent
            parent = parent.parent
        return parent

    def floor_below(self, key):
        current = self.root
        best = None
        path = []
        track = tracer.active
        while current is not None:
            if track:
                path.append(current)
            if current.key < key:
                best = current
                current = current.right
            else:
                current = current.left
        return best, path

    def ceiling(self, key):
        current = self.root
        best = None
        path = []
        track = tracer.active
        while current is not None:
            if track:
                path.append(current)
            if current.key >= key:
                best = current
                current = current.left
            else:
                current = current.right
        return best, path

    def _transplant(self, old, new):
        if old.parent is None:
            self.root = new
        elif old is old.parent.left:
            old.parent.left = new
        else:
            old.parent.right = new
        if new is not None:
            new.parent = old.parent

    def delete_node(self, node):
        if node.left is None:
            self._transplant(node, node.right)
        elif node.right is None:
            self._transplant(node, node.left)
        else:
            heir = self.minimum(node.right)
            tracer.log(f"BST {self.name} delete {node.label()} has two children; successor {heir.label()} takes its place")
            if heir.parent is not node:
                self._transplant(heir, heir.right)
                heir.right = node.right
                heir.right.parent = heir
            self._transplant(node, heir)
            heir.left = node.left
            heir.left.parent = heir
        node.left = node.right = node.parent = None
        self.size -= 1

    def delete(self, start, flight_id):
        node = self.search(start, flight_id)
        if node is None:
            return None
        flight = node.flight
        self.delete_node(node)
        tracer.log(f"BST {self.name} deleted ({fmt_ts(start)}, {flight_id})")
        return flight

    def inorder(self):
        result = []
        stack = []
        current = self.root
        while stack or current is not None:
            while current is not None:
                stack.append(current)
                current = current.left
            current = stack.pop()
            result.append(current)
            current = current.right
        return result

    def range_search(self, low, high):
        result = []
        stack = []
        current = self.root
        while stack or current is not None:
            while current is not None:
                stack.append(current)
                current = current.left if current.key[0] >= low else None
            current = stack.pop()
            if low <= current.key[0] < high:
                result.append(current)
            if current.key[0] < high:
                current = current.right
            else:
                current = None
        return result

    def find_conflicts(self, start, end):
        probe = (start, "")
        before, path_before = self.floor_below(probe)
        after, path_after = self.ceiling(probe)
        conflicts = []
        if before is not None and before.end > start:
            conflicts.append(before)
        node = after
        while node is not None and node.key[0] < end:
            conflicts.append(node)
            node = self.successor(node)
        if tracer.active:
            tracer.log(f"BST {self.name} conflict check [{fmt_ts(start)}, {fmt_ts(end)[11:]})")
            tracer.log(f"  predecessor path: {path_text(path_before)}")
            tracer.log(f"  predecessor: {self._neighbor_text(before)}")
            tracer.log(f"  successor path: {path_text(path_after)} ({len(path_after)} nodes visited)")
            tracer.log(f"  successor: {self._neighbor_text(after)}")
            tracer.log(f"  conflicts: {', '.join(n.flight_id for n in conflicts) if conflicts else 'none'}")
        return conflicts

    @staticmethod
    def _neighbor_text(node):
        if node is None:
            return "none"
        return f"{node.flight_id} [{fmt_ts(node.start)[11:]}, {fmt_ts(node.end)[11:]})"

    def is_free(self, start, end):
        with tracer.suspend():
            return not self.find_conflicts(start, end)

    def height(self):
        if self.root is None:
            return 0
        best = 0
        stack = [(self.root, 1)]
        while stack:
            node, depth = stack.pop()
            if depth > best:
                best = depth
            if node.left is not None:
                stack.append((node.left, depth + 1))
            if node.right is not None:
                stack.append((node.right, depth + 1))
        return best

    def check_invariants(self):
        problems = []
        nodes = self.inorder()
        if len(nodes) != self.size:
            problems.append(f"runway {self.name}: size {self.size} but {len(nodes)} nodes")
        for i in range(len(nodes)):
            node = nodes[i]
            if node.left is not None and node.left.parent is not node:
                problems.append(f"runway {self.name}: broken parent link at {node.label()}")
            if node.right is not None and node.right.parent is not node:
                problems.append(f"runway {self.name}: broken parent link at {node.label()}")
            if node.start >= node.end:
                problems.append(f"runway {self.name}: empty interval at {node.label()}")
            if i > 0:
                prev = nodes[i - 1]
                if not prev.key < node.key:
                    problems.append(f"runway {self.name}: order violated at {node.label()}")
                if prev.end > node.start:
                    problems.append(f"runway {self.name}: overlap {prev.flight_id} / {node.flight_id}")
        return problems

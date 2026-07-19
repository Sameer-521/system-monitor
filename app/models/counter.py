class Counter:
    def __init__(self, initial: int = 0) -> None:
        self.value = initial

    def increment(self, amount: int = 1) -> int:
        self.value += amount
        return self.value

    def decrement(self, amount: int = 1) -> int:
        self.value -= amount
        return self.value

    def reset(self, to: int = 0) -> int:
        self.value = to
        return self.value

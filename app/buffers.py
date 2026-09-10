from app.models.buffer import RingBuffer
from app.models.counter import Counter

# shared buffers!
cpu_buffer = RingBuffer("cpu")
mem_buffer = RingBuffer("memory")

high_cpu_usage_counter = Counter(0)

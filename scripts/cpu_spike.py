import multiprocessing
import time
import sys


def burn_core(duration: float) -> None:
    end = time.monotonic() + duration
    while time.monotonic() < end:
        _ = 2**31 - 1
        _ = _ * _ // 3


def main():
    cores = multiprocessing.cpu_count()
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 30

    print(f"Burning {cores} cores for {duration}s...")
    processes = [multiprocessing.Process(target=burn_core, args=(duration,)) for _ in range(cores)]
    for p in processes:
        p.start()
    for p in processes:
        p.join()
    print("Done.")


if __name__ == "__main__":
    main()

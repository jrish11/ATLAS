"""Offline destination lookup microbenchmark, not an end-to-end latency claim."""
import statistics
import tempfile
import time
import personal_commands

with tempfile.TemporaryDirectory() as root:
    personal_commands.save(root, 'Fixture', 'https://example.org/', ['fixture portal'])
    samples = []
    for _ in range(1000):
        start = time.perf_counter_ns()
        assert personal_commands.resolve(root, 'open fixture portal')
        samples.append((time.perf_counter_ns() - start) / 1e6)
    samples.sort()
    print('fixture local lookup: n=1000 median=%.3f ms p95=%.3f ms; excludes speech, process launch, browser and permissions' % (statistics.median(samples), samples[949]))

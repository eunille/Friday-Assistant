"""Turn audio chunks into frequency bands for the voice visualiser."""
import numpy as np

from friday.core.events import bus

BANDS = 16


def bands(samples, sample_rate, n=BANDS):
    """Return n values in 0..1: loudness per log-spaced frequency band (80 Hz - 8 kHz)."""
    x = np.asarray(samples)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if x.size < 32:
        return [0.0] * n
    scale = 32768.0 if np.issubdtype(x.dtype, np.integer) else 1.0
    x = x.astype(np.float32) / scale
    spectrum = np.abs(np.fft.rfft(x * np.hanning(x.size))) / (x.size / 4)
    freqs = np.fft.rfftfreq(x.size, 1.0 / sample_rate)
    edges = np.geomspace(80.0, min(8000.0, sample_rate / 2), n + 1)
    out = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (freqs >= low) & (freqs < high)
        level = float(spectrum[mask].max()) if mask.any() else 0.0
        out.append(round(min(1.0, level ** 0.5 * 2.2), 3))  # sqrt lifts quiet speech into view
    return out


def report(source, samples, sample_rate):
    """Publish a 'level' event. source is 'mic' or 'voice'. Free when nobody listens."""
    if not bus.has_subscribers:
        return
    try:
        bus.publish("level", source=source, bands=bands(samples, sample_rate))
    except Exception:
        pass
